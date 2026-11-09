import assert from "node:assert/strict";
import test from "node:test";

import { allowedFeedUrl, handle, keyMatches } from "./proxy.js";

const env = { FEED_PROXY_KEY: "s3cret" };

function req(url, { key = "s3cret", method = "GET" } = {}) {
  const headers = key === null ? {} : { "X-CC-Proxy-Key": key };
  return new Request(
    "https://cc-feed-proxy.example.workers.dev/?url=" + encodeURIComponent(url),
    { method, headers },
  );
}

function fakeFetch(responses) {
  const calls = [];
  const impl = async (url) => {
    calls.push(url);
    const r = responses[url];
    if (!r) throw new Error("unexpected fetch " + url);
    return new Response(r.body ?? "", { status: r.status ?? 200, headers: r.headers ?? {} });
  };
  impl.calls = calls;
  return impl;
}

test("allowlist accepts only https://<name>.substack.com/feed", () => {
  assert.equal(allowedFeedUrl("https://scotmcknight.substack.com/feed"),
    "https://scotmcknight.substack.com/feed");
  assert.equal(allowedFeedUrl("https://Scot-McKnight.substack.com/feed"),
    "https://scot-mcknight.substack.com/feed");
  for (const bad of [
    "http://scotmcknight.substack.com/feed",
    "https://substack.com/feed",
    "https://a.b.substack.com/feed",
    "https://scotmcknight.substack.com.evil.com/feed",
    "https://evil.com/scotmcknight.substack.com/feed",
    "https://scotmcknight.substack.com/p/some-post",
    "https://scotmcknight.substack.com/feed?x=1",
    "https://scotmcknight.substack.com:8443/feed",
    "https://user:pw@scotmcknight.substack.com/feed",
    "https://scotmcknight.substack.com/feed/../api",
    "not a url",
    "",
    null,
  ]) {
    assert.equal(allowedFeedUrl(bad), null, String(bad));
  }
});

test("key comparison", () => {
  assert.equal(keyMatches("s3cret", "s3cret"), true);
  assert.equal(keyMatches("s3cre", "s3cret"), false);
  assert.equal(keyMatches("s3cretX", "s3cret"), false);
  assert.equal(keyMatches(null, "s3cret"), false);
  assert.equal(keyMatches("", ""), false);
});

test("missing or wrong key is 401 and never fetches", async () => {
  const f = fakeFetch({});
  assert.equal((await handle(req("https://a.substack.com/feed", { key: null }), env, f)).status, 401);
  assert.equal((await handle(req("https://a.substack.com/feed", { key: "nope" }), env, f)).status, 401);
  assert.equal((await handle(req("https://a.substack.com/feed"), {}, f)).status, 401);
  assert.equal(f.calls.length, 0);
});

test("non-GET is 405", async () => {
  const r = await handle(req("https://a.substack.com/feed", { method: "POST" }), env, fakeFetch({}));
  assert.equal(r.status, 405);
});

test("disallowed URL is 400 and never fetches", async () => {
  const f = fakeFetch({});
  const r = await handle(req("https://example.com/feed"), env, f);
  assert.equal(r.status, 400);
  assert.equal(f.calls.length, 0);
});

test("passes the feed through with upstream status", async () => {
  const f = fakeFetch({
    "https://a.substack.com/feed": {
      body: "<rss></rss>", headers: { "Content-Type": "application/xml; charset=utf-8" },
    },
  });
  const r = await handle(req("https://a.substack.com/feed"), env, f);
  assert.equal(r.status, 200);
  assert.equal(await r.text(), "<rss></rss>");
  assert.equal(r.headers.get("Content-Type"), "application/xml; charset=utf-8");
  assert.equal(r.headers.get("X-CC-Upstream-Status"), "200");
});

test("follows redirects only inside the allowlist", async () => {
  const ok = fakeFetch({
    "https://old.substack.com/feed": { status: 301, headers: { Location: "https://new.substack.com/feed" } },
    "https://new.substack.com/feed": { body: "<rss/>" },
  });
  assert.equal((await handle(req("https://old.substack.com/feed"), env, ok)).status, 200);

  const out = fakeFetch({
    "https://old.substack.com/feed": { status: 301, headers: { Location: "https://evil.com/feed" } },
  });
  const r = await handle(req("https://old.substack.com/feed"), env, out);
  assert.equal(r.status, 502);
  assert.deepEqual(out.calls, ["https://old.substack.com/feed"]);
});
