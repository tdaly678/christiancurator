"""Substack feeds go through the cc-feed-proxy Worker when it is configured."""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetcher import rss_fetcher  # noqa: E402
from fetcher.sources import SOURCES  # noqa: E402

FEED = "https://scotmcknight.substack.com/feed"
PROXY = "https://cc-feed-proxy.example.workers.dev"
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>A post</title><link>https://scotmcknight.substack.com/p/a</link>
<pubDate>Mon, 09 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


class FakeResp:
    def __init__(self, status=200, content=RSS, headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


@pytest.fixture
def calls(monkeypatch):
    log = []
    script = {}

    def fake_get(url, timeout=None, headers=None, params=None):
        log.append({"url": url, "headers": headers or {}, "params": params})
        r = script.get(url)
        if isinstance(r, Exception):
            raise r
        return r or FakeResp()

    monkeypatch.setattr(rss_fetcher.requests, "get", fake_get)
    return log, script


@pytest.fixture
def proxy_env(monkeypatch):
    monkeypatch.setenv("CC_FEED_PROXY_URL", PROXY)
    monkeypatch.setenv("CC_FEED_PROXY_KEY", "k")


def _source(url=FEED):
    return {"name": "Scot McKnight", "url": url, "category": "theology"}


def test_uses_proxy_only_for_substack_feeds():
    assert rss_fetcher.uses_proxy(FEED)
    assert not rss_fetcher.uses_proxy("https://thecommon.place/feed")
    assert not rss_fetcher.uses_proxy("https://substack.com/feed")
    assert not rss_fetcher.uses_proxy("https://x.substack.com/p/post")
    assert not rss_fetcher.uses_proxy("http://x.substack.com/feed")


def test_every_substack_source_is_proxy_eligible():
    substack = [s["url"] for s in SOURCES if "substack.com" in s["url"]]
    assert len(substack) == 30
    assert all(rss_fetcher.uses_proxy(u) for u in substack)


def test_direct_fetch_without_env(monkeypatch, calls):
    monkeypatch.delenv("CC_FEED_PROXY_URL", raising=False)
    monkeypatch.delenv("CC_FEED_PROXY_KEY", raising=False)
    log, _ = calls
    articles, health = rss_fetcher.fetch_feed(_source())
    assert [c["url"] for c in log] == [FEED]
    assert len(articles) == 1 and "via" not in health


def test_substack_goes_through_proxy(proxy_env, calls):
    log, script = calls
    script[PROXY] = FakeResp(headers={"X-CC-Upstream-Status": "200"})
    articles, health = rss_fetcher.fetch_feed(_source())
    assert len(log) == 1
    assert log[0]["url"] == PROXY
    assert log[0]["params"] == {"url": FEED}
    assert log[0]["headers"]["X-CC-Proxy-Key"] == "k"
    assert health["via"] == "proxy" and health["http_status"] == 200
    assert articles[0]["url"] == "https://scotmcknight.substack.com/p/a"


def test_non_substack_never_uses_proxy(proxy_env, calls):
    log, _ = calls
    rss_fetcher.fetch_feed(_source("https://thecommon.place/feed"))
    assert [c["url"] for c in log] == ["https://thecommon.place/feed"]
    assert all("X-CC-Proxy-Key" not in c["headers"] for c in log)


def test_upstream_403_through_proxy_is_reported_not_retried_direct(proxy_env, calls):
    log, script = calls
    script[PROXY] = FakeResp(status=403, content=b"", headers={"X-CC-Upstream-Status": "403"})
    articles, health = rss_fetcher.fetch_feed(_source())
    assert articles == [] and health["http_status"] == 403
    assert all(c["url"] == PROXY for c in log)


def test_proxy_refusal_falls_back_to_direct(proxy_env, calls):
    log, script = calls
    script[PROXY] = FakeResp(status=401, content=b"unauthorized")
    articles, health = rss_fetcher.fetch_feed(_source())
    assert [c["url"] for c in log] == [PROXY, FEED]
    assert len(articles) == 1
    assert health["proxy_error"] == "HTTP 401" and "via" not in health


def test_proxy_exception_falls_back_to_direct(proxy_env, calls):
    log, script = calls
    script[PROXY] = requests.ConnectionError("down")
    articles, health = rss_fetcher.fetch_feed(_source())
    assert [c["url"] for c in log] == [PROXY, FEED]
    assert len(articles) == 1
    assert health["proxy_error"].startswith("ConnectionError")


@pytest.fixture
def sleeps(monkeypatch):
    waited = []
    monkeypatch.setattr(rss_fetcher.time, "sleep", waited.append)
    return waited


def test_proxy_429_is_retried_after_a_pause(monkeypatch, proxy_env, sleeps):
    # Nov 10 to 14 2026: one to four Substack feeds a day came back 429 through
    # the Worker and the run kept nothing from them.
    log = []
    answers = iter([FakeResp(429, b"", {"X-CC-Upstream-Status": "429"}),
                    FakeResp(headers={"X-CC-Upstream-Status": "200"})])

    def fake_get(url, timeout=None, headers=None, params=None):
        log.append(url)
        return next(answers)

    monkeypatch.setattr(rss_fetcher.requests, "get", fake_get)
    articles, health = rss_fetcher.fetch_feed(_source())
    assert len(articles) == 1
    assert health["http_status"] == 200 and health["retries"] == 1
    assert sleeps == [rss_fetcher.RETRY_DELAYS[0]]
    assert len(log) == 2


def test_retry_after_header_is_honored_and_capped(proxy_env, calls, sleeps):
    _, script = calls
    script[PROXY] = FakeResp(429, b"", {"X-CC-Upstream-Status": "429", "Retry-After": "600"})
    articles, health = rss_fetcher.fetch_feed(_source())
    assert articles == []
    assert health["http_status"] == 429
    # Two retries for each user agent, every wait capped.
    assert sleeps == [rss_fetcher.RETRY_AFTER_MAX] * 4


def test_403_is_not_retried(monkeypatch, calls, sleeps):
    monkeypatch.delenv("CC_FEED_PROXY_URL", raising=False)
    monkeypatch.delenv("CC_FEED_PROXY_KEY", raising=False)
    log, script = calls
    script[FEED] = FakeResp(403, b"")
    articles, health = rss_fetcher.fetch_feed(_source())
    assert articles == [] and sleeps == [] and "retries" not in health
    assert len(log) == 2  # browser UA, then the feed-reader UA
