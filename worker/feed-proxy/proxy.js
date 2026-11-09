// Substack feed proxy for the daily GitHub Actions run.
//
// Substack's Cloudflare refuses GitHub/Azure runner IPs (HTTP 403), so the
// fetcher asks this Worker for *.substack.com/feed URLs instead. It is not an
// open proxy: every request needs the shared secret header, only GET, and only
// https://<publication>.substack.com/feed with no query string.
//
//   GET https://cc-feed-proxy.<account>.workers.dev/?url=https://x.substack.com/feed
//   X-CC-Proxy-Key: <FEED_PROXY_KEY>
//
// Secret (never in this repo): npx wrangler secret put FEED_PROXY_KEY
// The same value is the CC_FEED_PROXY_KEY GitHub Actions secret.

export const CACHE_SECONDS = 600;
export const MAX_REDIRECTS = 3;
const KEY_HEADER = "X-CC-Proxy-Key";
const UPSTREAM_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 ChristianCurator/1.0 " +
  "(+https://www.christiancurator.com/)";
const ACCEPT =
  "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8";
const HOST_RE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.substack\.com$/;

// Returns the normalized feed URL string, or null when the URL is not allowed.
export function allowedFeedUrl(raw) {
  if (typeof raw !== "string" || raw.length > 200) return null;
  let u;
  try {
    u = new URL(raw);
  } catch {
    return null;
  }
  if (u.protocol !== "https:") return null;
  if (u.username || u.password || u.port) return null;
  if (!HOST_RE.test(u.hostname)) return null;
  if (u.pathname !== "/feed") return null;
  if (u.search || u.hash) return null;
  return `https://${u.hostname}/feed`;
}

// Constant-time comparison so the key cannot be guessed byte by byte.
export function keyMatches(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string") return false;
  if (!expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  let diff = a.length ^ b.length;
  for (let i = 0; i < b.length; i++) diff |= (a[i] ?? 0) ^ b[i];
  return diff === 0;
}

function text(status, body) {
  return new Response(body + "\n", {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
  });
}

// Follows redirects by hand so every hop must pass the allowlist too.
export async function fetchFeed(feedUrl, fetchImpl = fetch) {
  let url = feedUrl;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const resp = await fetchImpl(url, {
      redirect: "manual",
      headers: { "User-Agent": UPSTREAM_UA, Accept: ACCEPT },
      cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true },
    });
    if (resp.status < 300 || resp.status >= 400) return resp;
    const next = allowedFeedUrl(new URL(resp.headers.get("Location") || "", url).toString());
    if (!next) return text(502, `redirect outside allowlist from ${url}`);
    url = next;
  }
  return text(502, "too many redirects");
}

export async function handle(request, env, fetchImpl = fetch) {
  if (request.method !== "GET") return text(405, "method not allowed");
  if (!keyMatches(request.headers.get(KEY_HEADER), env.FEED_PROXY_KEY)) {
    return text(401, "unauthorized");
  }
  const feedUrl = allowedFeedUrl(new URL(request.url).searchParams.get("url"));
  if (!feedUrl) return text(400, "url must be https://<name>.substack.com/feed");

  let upstream;
  try {
    upstream = await fetchFeed(feedUrl, fetchImpl);
  } catch (err) {
    return text(502, `upstream fetch failed: ${err}`);
  }
  const headers = new Headers({
    "Content-Type": upstream.headers.get("Content-Type") || "application/xml",
    "Cache-Control": upstream.ok ? `private, max-age=${CACHE_SECONDS}` : "no-store",
    "X-CC-Upstream-Status": String(upstream.status),
  });
  return new Response(upstream.body, { status: upstream.status, headers });
}

export default {
  fetch: (request, env) => handle(request, env),
};
