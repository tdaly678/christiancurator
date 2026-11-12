# Christian Curator — Project Reference

## Purpose
Curate evangelical Christian content from across the web and become the #1 authority on the internet for the best Christian articles, information, books, etc. Rank globally, built for strong SEO, and eventually generate revenue.

## Site
- **URL:** https://www.christiancurator.com
- **GitHub repo:** https://github.com/tdaly678/christiancurator
- **Stack:** Static GitHub Pages site with a Python pipeline
- **Hosting:** GitHub Pages, served from `docs/` directory

## Architecture
- `docs/` — all static HTML served by GitHub Pages
  - `docs/index.html` — homepage (featured topic cards + curated headlines + browse grid)
  - `docs/digest/index.html` — Daily Digest page (featured topic cards + today's top 10 + yesterday's top 10, re-rendered daily)
  - `docs/archive/index.html` — Archive index listing all past days
  - `docs/archive/YYYY-MM-DD/index.html` — per-day archive snapshots
  - `docs/topics/[slug]/index.html` — 70 topic pages
  - `docs/daily/[date]/index.html` — daily editorial pulse pages
  - `docs/sitemap.xml` — SEO sitemap (auto-generated daily)
- `frontend/` — Jinja2 templates + rendering code
  - `frontend/template.html` — homepage template
  - `frontend/digest_template.html` — Daily Digest template (mirrors homepage layout)
  - `frontend/archive_template.html` — per-day archive template
  - `frontend/topics_data.py` — canonical 70-topic taxonomy (slug, name, category, hook, summary, keywords)
  - `frontend/__init__.py` — render functions: render_html(), render_digest_page(), render_archive_page(), render_archive_index()
- `curator/` — scoring, classification, email
  - `curator/topic_classifier.py` — keyword classifier mapping articles → topic slugs
  - `curator/email_sender.py` — Brevo email builder
- `fetcher/` — RSS/web fetching
- `main.py` — main pipeline entry point
- `regenerate_daily.py` — re-render pages from cached articles (requires Claude API for daily summary)
- `/tmp/rerender_only.py` — minimal re-render script (no Claude API needed; recreate each session from session notes)

## Working copy and pushing

**Never keep this repo inside OneDrive, iCloud Drive, or any other syncing folder.** A copy previously lived under
`~/Library/CloudStorage/OneDrive-Personal/Personal/Claude/Projects/Christian Curator/christiancurator`
(reached through a symlink at `~/Documents/Claude/Projects/Christian Curator`). OneDrive renamed git's temporary
object files mid write, which left hundreds of `.git/objects/xx/moved_tmp_obj_*` entries, broke `git fetch`
with `pack has 4720 unresolved deltas`, and stranded HEAD two months behind origin. That copy is an archive only.

**The working copy is `~/Projects/christiancurator`** (created 2026-09-25 by a fresh clone). It is a normal local
path, `git fsck` is clean, and it is the folder connected to Cowork.

Push credentials are stored in the macOS keychain, not in the remote URL and not in any file:

```bash
git config credential.helper osxkeychain
printf 'protocol=https\nhost=github.com\nusername=tdaly678\npassword=<TOKEN>\n\n' | git credential approve
```

`git remote -v` must show a clean `https://github.com/tdaly678/christiancurator.git` with no credentials in it.

**Always pull before pushing.** GitHub Actions commits to `main` on the Eastern morning run (target 5:00 AM America/New_York; see `.github/morning-trigger.md`), so a local run
that skips the pull will be rejected as non fast forward:

```bash
cd ~/Projects/christiancurator
git pull --no-rebase origin main
# ... make changes ...
git add <files> && git commit -m "..." && git push origin main
```


## Daily Pipeline (GitHub Actions)
Runs automatically around **5:00 AM America/New_York** all year (the workflow `timezone` field follows DST; catch-up slots and a same-morning no-op guard are in `.github/workflows/daily_run.yml`). A punctual 5:00 AM Cloudflare ping lives in `worker/morning/` and is not live until it is deployed. Operator notes: `.github/morning-trigger.md`.

What it commits: `docs/index.html`, `docs/topics/`, `docs/digest/`, `docs/yesterday.json`, `docs/email_draft.html`,
`docs/article_history.json`, `docs/research_articles.json`, all five sitemaps (`sitemap.xml`, `sitemap-core.xml`,
`sitemap-topics.xml`, `sitemap-voices.xml`, `sitemap-archive.xml`, `sitemap-daily.xml`), `docs/archive/`, `docs/daily/`,
`docs/_pagefind/`, `docs/voices/`, `docs/voices_data.json`, `docs/spotlight_topic_log.json`, `docs/feed_health.json`,
`docs/data_watch.json`, `data/` (topic data files updated by the data watch).

### Feed health and source roles (added 2026-10-30)
`fetcher/rss_fetcher.py` fetches feeds with `requests` (15s timeout, browser UA with a feed-reader UA retry, 8 threads)
and writes `docs/feed_health.json` every run: per-source `http_status`, `n_entries`, `newest_date`, `bozo`, `stale`,
`error`, plus `zero_streaks` (consecutive run days with 0 items). `scripts/check_feed_health.py` runs after the commit
and, since 2026-11-09, only warns: any source at 7+ days with 0 items becomes a `::warning` annotation and is listed in
the job summary's Feed health section, split into "Blocked on runner" (HTTP 401/403/429) and "Empty". It exits 1 only
when `docs/feed_health.json` is missing, or with `--strict`. Fix the URL in `fetcher/sources.py`; removing a source is
Tom's call. Tests: `tests/test_feed_health_check.py`.

Known runner block (2026-11-09): all 30 `*.substack.com` author feeds return HTTP 403 on GitHub Actions every day since
the first runner run on 2026-10-31, while the same URL and headers return 200 from a home connection and from other
datacenters. Headers are not the cause; Substack's Cloudflare refuses GitHub/Azure IP ranges. None of these authors
uses a custom domain. Pew Research (`/religion/feed/`) 403s from any datacenter IP and is still unfixed.

Substack fix (2026-11-09): the `cc-feed-proxy` Worker (`worker/feed-proxy/`, https://cc-feed-proxy.tdaly678.workers.dev)
fetches only `https://<name>.substack.com/feed` (allowlist, redirects checked per hop), requires the `X-CC-Proxy-Key`
header (Worker secret `FEED_PROXY_KEY`), and caches 10 minutes. `fetch_feed()` routes Substack feeds through it when the
`CC_FEED_PROXY_URL` and `CC_FEED_PROXY_KEY` env vars are set (GitHub secrets, wired into the Run pipeline step), else
fetches directly; a Worker refusal or outage also falls back to direct. Health rows show `via: "proxy"` or
`proxy_error`. Runner proof on 2026-11-09: direct 0 of 30, through the Worker 30 of 30. The fetch-only check workflow
`substack_proxy_check.yml` is disabled; re-enable it to debug. To rotate the key: generate a new value, then
`npx wrangler secret put FEED_PROXY_KEY` in `worker/feed-proxy/` and `gh secret set CC_FEED_PROXY_KEY` with the same
value. Tests: `tests/test_feed_proxy.py`, `node --test` in `worker/feed-proxy/`.

Sources can set `role: "discovery"` (fetched and health-logged, never ranked: The Aquila Report) or a
`discovery_title_pattern` (Tim Challies' A La Carte / Kindle deals / book roundups). `score_articles()` drops discovery
items before Claude scoring.

Sources can also set `role: "media"` (video and podcast feeds for the Watch and Listen lane, below). Media items are
health-logged like any feed but never scored, never deduped against articles, and never placed on the board.

`docs/article_history.json` rows carry `base_score` (Claude's editorial score before boosts), `boosts` (actual delta per
mechanism), and `scored_by` (`claude` / `fallback`). Rows from 2026-09-06 to 2026-10-25 (Anthropic credit outage) are
marked `scored_by: "fallback"`, `scored_by_backfilled: true` by `scripts/backfill_scored_by.py`; exclude them when tuning.

Steps after the pipeline itself: backfill orphan voice pages, rebuild the `/topics/` hub index, rebuild the `/voices/`
category hubs, run the topic data watch, refresh recent-articles sections, inject the Featured deep dives block, regenerate the sitemaps,
build the Pagefind index, commit, then ping IndexNow.

### Editorial scoring: two axes (P1 Wave 1, 2026-10-30)
Product thesis: RealClearPolitics for evangelicals. The front page ranks by importance; formative depth goes
to a separate Worth Your Time lane.

- `curator/scorer.py` asks Claude for `importance` (news value, evangelical significance, debate heat) and
  `depth` (theological and formative quality), each 1 to 10. News and data are no longer capped below devotionals.
- `final_score` = importance after boosts and penalties, so every existing sort by `final_score` ranks by importance.
  `importance` mirrors it. `depth` gets penalties only (half the age penalty, previously shown, Catholic cap), no boosts.
  `base_importance`, `base_depth` are Claude's raw values; `score` and `base_score` equal base importance for old callers.
- Boost cap: the combined upward movement from mechanical boosts (`BOOST_KEYS`: tier, recency, frequency, response,
  trending, stale_source, opposing_views, independent_floor) is capped at `MAX_TOTAL_BOOST = 2.0` per article.
  Penalties are uncapped. `INDEPENDENT_FLOOR_BOOST` dropped from 2.0 to 1.0. The used budget is `boost_total`.
- `curator/lanes.py` `select_worth_your_time()` returns the top 5 by depth (min depth 6, one per source), excluding
  URLs already placed in the importance lane. Rendered on the homepage and email since Wave 2, and the picks are
  written to `article_history.json` so the depth lane does not repeat.

### Evangelical focus: mainline polity cap (Tom, 2026-10-31)
Baptist and Presbyterian news is core coverage; mainline internal polity (UMC bishops and appointments, annual
conference process, routine TEC / ELCA / PC(USA) / UCC business) is not. The scorer prompt scores it 3 or below unless
it clearly matters to evangelicals (disaffiliation waves, Asbury/seminary doctrine fights, religious liberty).
`is_mainline_polity()` in `curator/scorer.py` is the title backstop: mainline body AND polity term, minus exemptions
(Asbury, Global/Free Methodist, seminary, religious liberty, court, "N churches"). Matches are capped at 3.0, flagged
`mainline_capped`, and kept out of the lead, board, Worth Your Time and The Debate. Never drop RNS, Christian Post or
WORLD to fix this. Tests: `tests/test_mainline_focus.py`. Notes: `.christian-orchestrator/evangelical-focus-and-schedule-2026-10-31.md`.

### Evangelical focus: world-news mission gate (Tom, 2026-10-31)
BBC, NYT and WSJ world feeds (`source_type: "world_news"`) carried wars, disasters, foreign politics and markets onto
the News board (Iran bases, Spain rail, Tigray, a Russian newspaper). Cause: the Haiku world-news filter had to keep one
"top story" per batch of 10 regardless of faith angle, and it kept every item when the API call failed. Both are gone.
`curator/mission.py` `has_faith_hook()` is a keyword gate (Christianity, church, clergy, religion, persecution,
religious liberty, abortion and life issues) on title + summary. In `filter_world_news_batch()` an item must pass the
gate AND be marked relevant by Claude; on an API error the gate alone decides. `build_homepage_layout()` drops any
world_news item failing the gate (`is_off_mission()`) from every lane, so cached re-renders are covered too. Christian
outlets are never gated. Tests: `tests/test_world_news_mission.py`.

### Headline voice: hard rejects (2026-10-31)
RealClear headlines (1,423 sampled, 2012 to 2026) never carry emoji, issue numbers or launch promos.
`curator/headline_voice.py` `hard_reject(title)` returns `HARD_REJECT_EMOJI`, `HARD_REJECT_ISSUE_NUMBER` (#432, Issue 12,
Vol. 3, Ep. 7, No. 45), `HARD_REJECT_PROMO` (promo collocates such as `"X" is HERE`, out now, now available, pre-order,
giveaway, book launch; never bare "launch" or "sale") or `HARD_REJECT_ROUNDUP` (Quick Things, Weekly Roundup, Things I'm
Reading, Friday Five, Open Thread, a leading "Links"), else None. `score_articles()` drops matches right after the age
cutoff, before Claude scoring, and logs each title plus a count by reason. Curly quotes are normalized first. The
patterns are documented at the top of the module. Tests: `tests/test_headline_voice.py`. Spec:
`.christian-orchestrator/realclear-headline-voice-2026-10-31.md`.

Slice 2 (2026-10-31), same module:
- `voice_score(title)` returns a net int: caps shout -30 (acronym allow-list `ACRONYMS`, quoted text ignored), `!` outside
  quotes -25, newsletter meta voice -20 ("My Week", "What I'm Reading"; not "Why I Left the PCA"), under 3 or over 14
  words -10, subject + news verb +10 (`NEWS_VERBS`), issue question opener +5. `score_articles()` adds `voice_score / 10`
  to `final_score` under the `voice` key (in `BOOST_KEYS`, so lifts share the 2.0 cap; demotions are uncapped) and stores
  `voice_score` and `voice_rules` on the article.
- `display_title(title, source)` is conservative cleanup, never new words: strips emoji, em/en dashes (comma for clause
  breaks, hyphen for ranges), ` | Outlet` tails, ` - Outlet` when it matches the source, and service tails ("here's why",
  "what you need to know", "read more"); Title Cases only an ALL CAPS shout. `apply_display_title()` runs on every
  article that passes the hard rejects (and on media items in `main.py`); when it changes something it sets
  `display_title` and fills `rewritten_title`, which every display path already reads. Claude rewriting stays off.
- `display_byline(author, source)` returns "Author, Outlet".
- Pulse: no em dashes. The `curator/daily_summary.py` prompt bans them and `sanitize_pulse()` (via `strip_dashes()`)
  cleans every generated paragraph. Tests: `tests/test_pulse_sanitizer.py`.
- Site-only republish: run the Daily Curator Run workflow with `no_email: true` (runs `main.py --no-email`, overrides
  `force_email`).

Slice 3 (Nov 1, Jarvis-greenlit), same module:
- `hard_reject(title, source)` also returns `HARD_REJECT_DATED_COLUMN` (title ends in a date set off by `(`, `:`, a dash
  or comma, or is only a weekday date: Works & Wonders, A La Carte, WORLD "morning news", Pew weekly updates) and
  `HARD_REJECT_REVIEW_META` ("lives up to its title / the hype / ..."). Allow-list `DATED_ALLOW`: World Magazine
  `^The World and Everything in It: ` and Albert Mohler weekday-date Briefing titles. `is_dated_briefing()` lets those
  sit on the board or in Watch and Listen but never the lead.
- `voice_adjustments()` adds `REVIEW_SOFT` -20 (`^review:`, "a review of", "new and notable") and
  `DEMOTE_CLAIMLESS_SHORT` -15 (`is_claimless_short()`: 2 to 5 words, no `:`/`?`, no verb, no `CLAIM_NOUNS`, starts
  with "The" or "Noun of Noun"; "tyranny" is deliberately not a claim noun). Claimless titles are board/lane fill only:
  never lead, sublead or any email slot. Title rewriting stays off.

### Cross-day repeats (Nov 1)
- `output.load_yesterday_shown()` returns the latest `date_shown` before today and its URLs (url + canonical_url).
  `score_articles(..., yesterday_urls, yesterday_date)` flags matches `shown_yesterday`; every earlier-shown match
  gets the soft `PREVIOUSLY_SHOWN_PENALTY` (-4.0). Both are logged as "Cross-day exclude: ..." and
  "Previously-shown penalty ... applied to M older articles."
- `build_homepage_layout()` no longer drops `previously_shown` from the pool. `shown_yesterday` items are barred from
  the lead, subleads and debate; `email_sender._email_layout()` filters every email slot with `email_eligible()`.
  They may still appear on the page board. Worth Your Time and Watch and Listen still skip all previously shown items.
- `save_article_history(outbound_articles(layout))` in `main.py` replaces the old top-20 + lane-picks saves.
- `scripts/backfill_history.py` (dry run by default, `--write`) appends rows (`scored_by: "backfill"`) for editions
  read from git (`EDITIONS`); Oct 31 and Nov 1 were backfilled on 2026-11-01. Exclude those rows when tuning.
  Tests: `tests/test_cross_day_and_voice.py`.

### Homepage v2 (P1 Wave 2, 2026-10-30)
`frontend/layout.py` `build_homepage_layout()` decides every homepage placement; `render_html()` renders it, returns
it, and `main.py` passes it to `send_email()` so page and email agree. Each URL appears once. Order on the page:
1. Masthead strip: date, `Updated H:MM AM ET` (actual render time), one-line Pulse (first sentence, max 20 words)
2. Lead + 3 subleads: 4 picks, one per source, not previously shown, ordered by the Pulse and content kind
   (see Ideas over scandal, below)
3. Board: three columns (Church & Theology / Commentary & Debate / News, in that order since 2026-11-12), 22 each,
   max 3 per source per column; a non-dominant scandal story sinks to the bottom of its column.
   `board_column()` routes by world_news source, perspective `news`, or tags news/data/politics, then
   theology/church life/missions/devotional/prayer/apologetics tags or a theology/devotional source; else commentary
4. The Debate: Claude point/counterpoint pairings, else scorer `opposing_pair` supportive vs. critical; omitted when none
   (`curator/point_counterpoint.py`, tightened 2026-10-30). Claude sees title, source, perspective, cluster/tags and a
   snippet, must state thesis A and thesis B, and every pair (Claude, cached or fallback) must pass `validate_pair()`:
   different sources, not both news/neutral, not the same stance, not the same story (shared distinctive proper nouns
   unless one is supportive and the other critical). Empty is the expected result on most days. Tests: `tests/test_point_counterpoint.py`
5. Worth Your Time (depth lane), 6. Watch and Listen (media lane, below), 7. Research & Data
   (`docs/research_articles.json`), then signup, then the 70-topic grid
Headline clicks are tracked by one delegated gtag listener reading `data-pos` / `data-src`. Sample render: ~78 outbound
article links. Since 2026-11-01 every rendered article (`outbound_articles(layout)`: lead, subleads, board, debate,
lanes, research) is logged to history with url + canonical_url, one row per article per day (see Cross-day repeats).
- Audio/video cap: at most `MAIN_LANE_MAX_AUDIO_VIDEO = 2` podcast or video items (`is_audio_video()`: a `/podcast`
  URL path, a YouTube/Vimeo host, a "Podcast:"/"Video:" title prefix) in the lead block plus board combined.
- Tags and personas are validated against `curator/vocab.py` allowlists (with an alias map); unknowns are dropped
  and logged once per run.
- `curator/dedup.py` collapses cross-feed duplicates before ranking: canonical URL (https, no www, no tracking params,
  no trailing slash), then normalized title (25+ chars). Survivor preference: primary over discovery, the source whose
  domain matches the link, christian over world_news, then sources.py order. Losers are listed in `also_from`.
- Headlines: original publisher titles everywhere. `curator/title_rewriter.py` is off unless `CC_REWRITE_TITLES=1`.
- `article_history.json` rows now also carry `importance`, `depth`, `base_importance`, `base_depth`, `canonical_url`.
  Rows before 2026-10-31 are single-axis; do not mix them with two-axis rows when tuning.

### Ideas over scandal: the lead block follows the Pulse (Tom, 2026-11-12)
Thinking, philosophy, theology and praxis lead; news is second; scandal is last. `curator/editorial.py`
(no API client) decides the lead block order and `build_homepage_layout(..., daily_summary=...)` applies it, so page
and email agree.
- `content_kind(a)`: `scandal` (any `SCANDAL_RE` word in the title; "crisis" / "investigation" alone only on a news
  report; plagiarism was added to `SCANDAL_RE`), `news` (`is_news_report()`), `ideas` (a theology, apologetics, church
  life, missions, devotional, prayer, family, suffering or work tag), else `commentary`.
- Tiers, one per source: 0 Pulse-cited (any kind but scandal, `final_score >= 3`, in the Pulse's mention order);
  1 ideas on a Pulse theme; 2 other ideas; 3 commentary (tiers 1 to 3 need `final_score >= 5`); 4 news, filler only.
  Scandal never fills. Tiers 1 to 4 sort by 0.5 importance + 0.5 depth.
- Pulse-cited (`pulse_cited_urls()`): the Pulse's own `sources` list (Claude returns it; stored as `source_urls`,
  validated against `candidate_urls`), then links and named writers / outlets by position. A named author beats an
  outlet of the same name; outlet names inside a link's anchor text belong to that link.
- Dominant story (the high bar): news or scandal with `final_score >= 8.5` carried by 4+ distinct outlets (cluster
  plus dedup `also_from`). It gets one reserved slot, the first sublead, and takes the Lead only when nothing else
  qualifies.
- Replay: `.venv/bin/python scripts/replay_lead_block.py 2026-11-12 2026-11-11` prints before/after Lead and email top
  8 from `article_history.json` rows (writes nothing). Tests: `tests/test_ideas_over_scandal.py`. Report:
  `.christian-orchestrator/ideas-over-scandal-report.md`.

### Watch and Listen media lane (P1 Wave 3, 2026-10-30)
A compact homepage and email section of 3 to 5 videos and podcast episodes from trusted evangelical voices.
- Sources: the `MEDIA SOURCES` block at the end of `SOURCES` in `fetcher/sources.py`, each with `role: "media"` and
  `media_format` (`video` / `podcast`). Their order is editorial priority. Current list: Truth Unites (Gavin Ortlund,
  YouTube), The Gospel Coalition (Video) (YouTube), Mere Fidelity, The Russell Moore Show, BibleProject Podcast,
  Gospelbound, The Holy Post, Ask Pastor John. Rejected candidates and the reason are listed under the watchlist at the
  bottom of `sources.py`. Before adding one, confirm the feed returns items with a post in the last 60 days.
- Fetching (`fetcher/rss_fetcher.py`): YouTube Shorts (`/shorts/` links) are dropped. Podcast items carry
  `duration_seconds` from `itunes:duration`. Feeds whose episodes have no page of their own (no link, or every item
  links the show homepage) set `apple_podcast_id`; the fetcher maps each episode guid to its Apple Podcasts episode URL
  with one lookup call. Items that still have no episode URL are never shown.
- `main.py` splits media items off right after the fetch (they skip scoring, the title rewriter, pairings and voices),
  marks `previously_shown` from `article_history.json`, stores them under `"media"` in `output/articles.json` (so
  `regenerate_daily.py` keeps the lane) and passes them to `render_html(media_items=...)`. `score_articles()` also drops
  `role: "media"` as a backstop.
- Selection: `curator/lanes.py` `select_watch_and_listen()`: published in the last 7 days, not previously shown, not
  placed elsewhere on the page (canonical URL), newest item per source, one per source. Items from the last 2 days
  first, then source priority, then recency. Keeps at least one video and one podcast when both qualify. Returns []
  (section omitted on page and in email) when fewer than 3 qualify. No Claude call.
- `build_homepage_layout()` picks the lane after Worth Your Time and before the board, adds it to the placed set and
  `outbound_urls()`. The page shows format, duration when known, original title and source; links open in a new tab.
- Picks shown are written to `article_history.json` with `scored_by: "media"`, so the lane rotates. Exclude those rows
  when tuning the scorer.

### Sitemaps — there are six files, not one
`docs/sitemap.xml` is an **index** that points at three children: `sitemap-core.xml` (6 URLs), `sitemap-topics.xml` (70),
`sitemap-voices.xml` (1,158). `sitemap-daily.xml` and `sitemap-archive.xml` are still written by `regenerate_sitemap()` but,
since 2026-10-26, are deliberately **not listed** in the index (crawl budget goes to topics and voices). Anything that
suppresses a page must also remove it from the relevant child sitemap, or the signals conflict.

Voice pages listed in `frontend/voices_noindex.json` are skipped by the sitemap generator. Merged duplicate voices are
recorded in `frontend/voices_redirects.json` (loser → survivor); the loser's page is a noindex meta-refresh stub, and
`scripts/merge_duplicate_voices.py` holds the pair list.

## P2: engagement and sourcing (2026-10-30)

### P2.1 Click tracking (GA4, no second analytics stack)
- Recording: homepage headlines (`data-pos` / `data-src`) fire one delegated GA4 `article_click` event with
  `link_url` = the publisher URL (beacon transport). Digest and archive pages send the same event inline. GA4
  enhanced measurement also logs every outbound link as `click` with the same built-in Link URL dimension.
- Storing: `scripts/fetch_click_counts.py` (daily step after the pipeline, `continue-on-error`) asks the GA4 Data API
  for eventCount by date, eventName and linkUrl over the last 7 days, takes the larger of `article_click` and `click`
  per day and URL (same physical click, never summed), keys by `canonical_url`, and writes `docs/click_counts.json`
  (`urls[canonical] = {url, total, by_day}`, every clicked outbound link including board items) plus the `clicks`
  field on matching `article_history.json` rows. Backfill with `--days 90`.
- Reading: `python scripts/fetch_click_counts.py --top 20` prints the most clicked URLs from the stored file.
  Clicks are stored only; they do not feed scoring yet.
- Needs Tom: GitHub secrets `GA4_PROPERTY_ID` and `GA4_SERVICE_ACCOUNT_JSON` (a Google Cloud service account key with
  the Analytics Data API enabled, added as Viewer on the GA4 property). Without them the step prints a skip notice.
- Email clicks are not included; Brevo's own click stats cover the email.

### P2.2 Story clustering
- `curator/clusters.py` `build_story_clusters()` groups the ranked fresh pool by `topic_cluster` (never `unique` or
  empty) and folds in dedup copies (`also_from`, plus `also_links` = [{source_name, url, title}], which
  `curator/dedup.py` now records for each collapsed copy). A story with 3+ distinct outlets (`MIN_OUTLETS`) shows
  once, at its best-ranked article, with an `also: World · RNS` line (max 4 links, one per source). The other copies
  are removed from the lead pool, board and Worth Your Time. Under threshold nothing changes.
- `build_homepage_layout()` returns `siblings` (representative URL -> links); `also_line()` in `frontend/template.html`
  renders it under the lead, subleads and board items with `data-pos="also"` so the clicks are tracked. The email
  ignores `siblings`, so the CTR trims are unchanged. Tests: `tests/test_clusters.py`.

### P2.3 Discovery queue
- `fetcher/discovery.py` `run_discovery_queue()` runs in `main.py` right after the fetch (wrapped in try/except).
  Discovery items from sources that opt in (`harvest_links: True`, or a `discovery_harvest_pattern` title regex; Tim
  Challies sets `r"A La Carte"`) have their outbound links harvested from the feed HTML. Dropped: the roundup's own
  domain, stores, social and video hosts, `store.`/`shop.`/`grow.`/`gift.` subdomains, images, bare homepages,
  sponsor links (`utm_source=challies`), anchors under 3 words, roundups older than 3 days.
- Queue: `docs/discovery_queue.json` (`entries[canonical_url] = {url, anchor, found_via, found_in, found_on, status,
  attempts}`), committed daily. Already-shown URLs are skipped; entries expire after 7 days.
- Graduation: up to 25 pending entries per run are fetched; og:title, description, site name, author and published
  time become a normal article (`role: "primary"`, `discovered_via`, `creates_voices: False` unless the domain belongs
  to a configured source, whose name and category it then takes). They go through `score_articles()` like any feed
  item, and dedup collapses them against feed copies. Status becomes `graduated`; two failed fetches mark `failed`.
- The Aquila Report does not harvest: its feed has no original link and its pages are behind a Cloudflare challenge.

### P2.4 Quarterly prune of quiet independents
- `scripts/prune_sources.py` checks every `independent: True` primary source. It moves when it has 0 placements in 90
  days (article_history rows plus `docs/archive/` day pages) AND under 2 posts a month (live feed, items in the last
  90 days / 3). Sources first added under 90 days ago (per `git log -S`) are exempt.
- Default is a dry run that prints a table; `--report PATH` also writes it as markdown. `--apply` removes each mover's
  dict from `SOURCES` and appends a dated line to the "Voices watchlist (NOT fetched)" comment block at the bottom of
  `fetcher/sources.py`, which is for topic-page curation only. Review the diff and commit by hand.
- Run early Jan / Apr / Jul / Oct. First dry run (2026-10-30, not applied): Hannah Anderson, Katelyn Beaty, Aimee Byrd,
  Kate Shellnutt, Thomas Kidd. Report: `.christian-orchestrator/prune-dry-run-2026-10-30.md` (untracked).
  Tests: `tests/test_prune_sources.py`.

## Hand-curated content — do NOT bulk regenerate
The topic pages at `docs/topics/<slug>/index.html` are **hand-curated**. They are edited directly (often by AI assistants at Tom's request) and are **not** regenerated from a template by any script. **This changed:** the daily pipeline now DOES `git add docs/topics/`, because `build_recent_articles.py` refreshes the recent-articles block on topic pages each day. It only edits between the injection markers below, so hand-written editorial survives, but topic pages are no longer outside the pipeline's reach.

**Safe operations on topic pages:**
- Targeted edits to a specific slug (fix a typo, update an article card, tweak copy)
- Cross-cutting transformations that **preserve content** — e.g. the semantic-HTML upgrade that renamed `<div class="cc-*">` to `<header>`/`<main>`/`<section>`/`<article>`/`<footer>`/`<nav>` while keeping every class and every word of body copy
- Scripted changes that are idempotent and reviewed via diff before committing

**Unsafe without explicit confirmation from Tom:**
- Wiping and re-emitting topic pages from `topics_data.py` or any other source
- "Regenerating all topic pages" — the pages contain unique editorial content (editorial paragraphs, 5 key questions, 3-position debate card, synthesis, 10 curated articles with annotations) that is not stored anywhere else
- Bulk find/replace that changes wording rather than structure

If a request sounds like it implies bulk regeneration, stop and confirm scope before doing anything destructive.

### Curated-list quality gate — `scripts/check_topic_quality.py`
Blocks placeholder entries in the "Evangelical Conversation, Curated" lists: `href="#"`/missing URLs, "Article on…" titles,
template titles that paste the topic name in ("The Biblical Basis for On X", "Rethinking On X for a New Generation"), and
boilerplate annotations ("A pastoral reflection on how X connects…"). It runs in `daily_run.yml` **before** the commit
step and in `topic_quality.yml` on every push to `docs/topics/`. It is ratcheted against `scripts/topic_quality_baseline.json`.
As of 2026-10-29 the baseline is empty: every topic page is clean, so any new filler fails the check. A page may not get worse, and a page not in the baseline
must stay clean. After cleaning a page, run `python scripts/check_topic_quality.py --update-baseline`. Every new curated
entry needs a real, verified URL, the real author/outlet, and a summary specific to that piece. Never invent a URL or
byline.

### Biblical literacy survey visuals (2026-11-09)
`docs/topics/biblical-literacy/` carries three data pieces (reverence gap chart, "By the Numbers" quiz, survey tracker)
rendered by `scripts/build_biblical_literacy_viz.py` from `data/biblical-literacy/surveys.json` into the
`CC-BL-VIZ-GAP`, `CC-BL-VIZ-QUIZ` and `CC-BL-VIZ-TRACKER` marker blocks (styles in `CC-BL-VIZ-CSS` in the head). Run it
by hand after editing the data; the daily data watch (below) also reruns it after adding a `watch` row. It bumps "Last updated" and `dateModified` only when
the data hash changes, fails on any row without a URL or license status, and refuses to chart rows that are not
`reuse` / `permission-granted` (Barna and ABS are `ask-first`, cited as text). Add a `changelog` entry with each data
change. Spec: `.christian-orchestrator/biblical-literacy-page-visuals.md`. Tests: `tests/test_biblical_literacy_viz.py`.

### Topic data watch (2026-11-09)
`scripts/run_data_watch.py` (logic in `curator/data_watch.py`) is a daily workflow step after the pipeline and before
`build_recent_articles.py`, with `continue-on-error` and exit 0 on any error. It is deterministic (no Claude call) and
fails closed: anything it cannot verify is linked, not written as a number, and nothing it writes is ever charted.
- Input: today's scored pool (`output/articles.json`) plus digest rows from the last 3 days (`article_history.json`).
  Off-mission world news (`is_off_mission()`) is skipped. State lives in `docs/data_watch.json` (`seen`, `fresh`,
  `figures`, `last_run`), committed daily.
- Detection (`detect_signals()`): a named research publisher (`PUBLISHERS`: Lifeway, Pew, Gallup, Barna, ABS / State of
  the Bible, Ryan Burge / Graphs About Religion, YouVersion, Wycliffe, Publishers Weekly, ECPA, Circana, PRRI), a figure
  ("62%", "2 in 3"), or a strong data word (survey, poll, quiz, statistics). Weak words (study, report, data) need the
  scorer's `data` tag; "Bible study" never counts. Trend = `final_score` + 1.5 per extra outlet (dedup `also_from`, shared
  `topic_cluster`) + 1 when on the digest. Digest stories get the fetch budget first (`MAX_FETCH = 8`).
- Topic matching (`match_topic_slugs()`, max 3, only slugs with a page): `WATCH_TOPICS` keywords, `topic_classifier`,
  plural-tolerant title hits on every `topics_data` keyword, and `topic_matcher` curated keywords. `NARROW_TOPICS` keeps the
  `evangelicalism` catch-all to titles that say evangelical / SBC / NAE.
- Figures (`find_figures()`, `verify_figure()`): only for stories on the digest or with `final_score >= 6`. The story page
  is fetched once (a 403 or timeout is a `::warning` and "link only"; one retry next run). A figure is a whole sentence
  found verbatim on the fetched page, 40 to 320 characters, with a number, a topic keyword, a named population (adults,
  churchgoers, pastors...), no first person, no promo words, no dashes, not opening with a connective or pointing back
  ("that 42%"), tied to exactly one known publisher, and the story or sentence must pass `has_faith_hook()`. License
  status comes from `PUBLISHERS`: Pew, Lifeway, Gallup `reuse`; Barna, ABS, Burge `ask-first`; the rest `cite-only`.
- Writes, in order:
  1. Digest stories matched to a topic go to `fresh[slug]`; `build_recent_articles.py` merges them into that page's
     Fresh From the Digest block (any topic page, not only the `topic_matcher` list; `biblical-literacy` was added to it).
  2. Topics with a `data_file` in `WATCH_TOPICS` (today: biblical-literacy) get a row in the file's `watch` list plus a
     changelog line, then their builder reruns. The builder shows `watch` rows as a cited text table ("New figures from
     the data watch") and never charts them. If the builder fails, the data file and page are restored.
  3. Every other topic page gets a `<!-- CC-LATEST-FIGURES:START --> ... END -->` block (quoted sentence, publisher,
     source link, max 5, kept 365 days; Pew adds its disclaimer). It is inserted once before `AEO-RELATED-TOPICS:START`
     (after the synthesis, never inside the curated list) and refreshed in place. "Last updated" and the Article
     `dateModified` move only when the block's content changes.
- Job summary: "Topic data to review" lists every data story with source, signals, topics, trend and the action taken
  (Fresh link, figure verified, fetch failed, no verifiable figure, watching only, already cited). No email is sent.
- Promoting a `watch` row into a chart is a hand step: confirm question wording, sample, field dates and license, then add
  it to the data file's `studies` / `rows`.
- Add a topic to the watch: every topic page is already eligible for Fresh links and Latest Figures. Add a
  `WATCH_TOPICS[slug]` entry for extra `keywords` (story matching) or `sentence_keywords` (sentence relevance). For charts,
  create `data/<slug>/...json` and a builder in `scripts/` with `PAGE_PATH`, `main(argv) -> int` (accepting `--date`)
  and support for a `watch` list, then set `data_file` and `builder` on the entry. Add a publisher to `PUBLISHERS` with
  its license status before its figures can be quoted.
- Local dry run (writes nothing): `python scripts/run_data_watch.py --dry-run`. Tests: `tests/test_data_watch.py`.

### Idempotent injection markers
Cross-cutting scripts inject content-additive blocks using HTML-comment markers so re-runs replace the block in place instead of duplicating it. When extending any of these, update between the markers rather than editing around them:

- `<!-- CC-LATEST-FIGURES:START --> ... END -->`: "Latest Figures" block on topic pages, written by the data watch (above)
- `<!-- AEO-RELATED-TOPICS:START --> ... END -->` — "Related Deep-Dive Topics" block on each topic page (inserted by `scripts/add_related_topics.py`, positioned between the synthesis `</section>` and the curated article list)
- `<!-- AEO-TOPIC-BACKLINKS:START --> ... END -->` — "Featured in Deep-Dive Topics" block on voice pages (inserted by `scripts/update_voice_backlinks.py`, which is also invoked by `main.py` after `render_html` each day)
- `/* AEO-FAQPAGE-SCHEMA */` — marker comment inside the FAQ JSON-LD script block; `verify_aeo.py` strips this before parsing

All three scripts are safe to re-run standalone. The breadcrumb insert (`scripts/add_breadcrumbs.py`) uses a `.cc-breadcrumb` class presence check and a `"@type": "BreadcrumbList"` substring check for idempotency rather than markers.

## Navigation Structure — canonical 3-item nav

Every site page has **exactly three** top-level items in its `<nav class="cc-nav">`, in this order:

1. **Home** — `<a href="/">Home</a>`
2. **Topics** — dropdown button with 4 submenus (Core Theology, Church Life, Spiritual Formation, Culture & Society)
3. **Resources** — dropdown containing About, Voices, Archive

No "Daily Digest" link in the top nav — users reach the digest via the Home link (home = today's digest) or the "Get the Daily Digest" subscribe button. The footer nav does still include a Daily Digest link; that's intentional.

CSS class: `.cc-nav`. The canonical HTML pattern lives in `frontend/archive_template.html` — use this when creating new standalone pages. The Topics dropdown block is bracketed by `<!-- CC-TOPICS-DROPDOWN:START -->` / `<!-- CC-TOPICS-DROPDOWN:END -->` markers in every template; keep the marker pair so sync scripts can re-inject the list.

### Guardrail — `scripts/check_nav_consistency.py`

Run after any change that touches the nav or when adding new standalone pages:

```
python scripts/check_nav_consistency.py                   # full site
python scripts/check_nav_consistency.py --only-standalone # just hand-written pages
```

Exits non-zero if any page's `cc-nav` block is missing Home, Topics, or Resources. This catches drift like the April 2026 About-page launch (published without the Topics dropdown because it was hand-written rather than rendered from a Jinja template).

> **Known pre-existing drift:** 16 archive day pages dated 2026-03-22 through 2026-04-06 plus `docs/archive/index.html` pre-date the Topics dropdown and will fail the full-site check. Backfilling them is a separate task.

## Topic Cards — hook vs. summary
Each topic in `topics_data.py` has two description fields:
- **`hook`** — punchy debate question ("Is hell eternal torment or annihilation?"). Used on **individual topic pages** for SEO/AEO.
- **`summary`** — plain description ("Evangelical views on the afterlife, eternal punishment..."). Used on **homepage cards, digest cards, and email cards** — does not imply today's articles directly answer the question.

Templates use `{{ topic.summary or topic.hook }}`. The `compute_featured_topics()` function in `topic_classifier.py` must include `"summary": topic.get("summary", topic["hook"])` in its output dict.

## Topic Classifier — How It Works
`curator/topic_classifier.py` maps each article to 0–2 topic slugs:

1. **HTML/URL stripping** — removes `<tags>` and `https://...` URLs before matching (prevents CDN image URLs from triggering false keyword matches)
2. **Scoring** — title keyword hits × 3 + body keyword hits
3. **Threshold: score ≥ 2** — requires either 1 title hit OR 2+ body hits (single-keyword noise eliminated)
4. `compute_featured_topics()` — aggregates article counts per topic, returns top 3 for homepage/digest

Keywords removed from topics in April 2026 for being too generic: `media`, `tech` (technology), `race`, `justice` (racial-reconciliation), `justice` (biblical-justice), `fear` (anxiety), `work`, `labor` (vocation), `silence` (spiritual-disciplines + contemplative-prayer), `pain` (suffering), bare `sovereignty` (predestination).

## Daily Digest — Yesterday Section (Added April 6 2026)
The digest page shows "Yesterday's top reads" below today's headlines. `save_yesterday()` in `output/__init__.py` saves the top 10 scored articles daily to `docs/yesterday.json`. `render_digest_page()` in `frontend/__init__.py` accepts `yesterday_articles` and sorts to top 10 before passing to the template. The browse grid ("Explore all topics") was removed from the digest page — it lives on the homepage only.

## Email Design (Updated October 2026)
Daily email via Brevo API, built in `curator/email_sender.py` after `render_html()` (which assigns `debate_topics`).
Structure mirrors homepage v2 (same `layout` dict):
1. Date line + "Forwarded to you? Subscribe Free" banner
2. Masthead + byline: *"For curious Christians seeking clarity on the questions that matter most"*
3. **The Lead**: lead + 3 subleads
4. **The Daily Pulse**: `daily_summary["paragraphs_html"]` plus a link to `/daily/YYYY-MM-DD/`; omitted when the summary is missing or empty
5. **Board**: Church & Theology, Commentary & Debate, News, 3 headlines each
6. **The Debate** (when pairs exist), **Worth Your Time**, **Watch and Listen** (when it has picks)
7. CTA to the homepage, then the **Go Deeper** spotlight topic (rotation logged in `docs/spotlight_topic_log.json`, no repeats for 70 days)
8. Forward nudge + footer

Every headline links **directly to the article URL**. (Homepage anchors `/#a<hash>` were dropped in October 2026 because
the next day's re-render removes them; if an article has no URL the link falls back to `/archive/YYYY-MM-DD/`.)
Subject line (Tom, 2026-11-09): follows the Daily Pulse, never the lead headline. `build_subject(daily_summary)` tries,
in order: the Pulse's own `subject` (Claude returns it with the paragraphs), the Pulse's first sentence shortened by whole
clauses with fillers ("today", "this week", "actually") and then the "writers are arguing about" lead-in dropped
(`subject_candidates()`), "Today's conversation: {first theme}", and with no Pulse "Christian Curator · November 9, 2026".
Each line must pass `_subject_ok()`: 25 to 80 characters, never cut with an ellipsis, no emoji/promo (`hard_reject`), no
`!` or dashes, no scandal or crime word (`headline_voice.SCANDAL_RE` plus `_SUBJECT_AVOID_RE`). The preheader is the next
non-scandal Pulse sentence, else `Leading: {lead} | {sublead}` when there is no Pulse. Tests: `tests/test_email_sender.py`.
One-day editor's note: `_render_editor_note()` shows "A note" under the masthead only when `edition_date()` (America/New_York)
equals `EDITOR_NOTE_DATE` (2026-11-11); that day the preheader is the note's first sentence and Go Deeper is skipped if it
would feature `EDITOR_NOTE_TOPIC`. Inert on every other date; safe to remove afterward.

## Topic Pages — Structure (70 topics as of September 2026)

All topic pages have this structure:
1. **Head** — `title: "On [Topic] — Christian Curator"`, meta description ≤160 chars, OG/Twitter tags, Schema.org JSON-LD
2. **Header nav** — back link + site name
3. **Hero** — series label (category), h1 title, deck (italic), meta line
4. **Editorial** — 2 paragraphs framing the conversation
5. **Key Questions** — `.cc-key-questions` box, 5 questions (SEO + AEO)
6. **The Evangelical Debate** — `.cc-controversy` section with `.cc-debate-grid.three-way` containing 3 `.cc-debate-side` cards (side-a/b/c), each with position label, name, thinkers, argument, and key reads
7. **What the Conversation Adds Up To** — `.cc-synthesis` section, 2 paragraphs
8. **The Evangelical Conversation, Curated** — 10 articles, ≥6 unique sources, 3–4 sentence annotations each
9. **Topics nav strip** — all topics in 4 categories
10. **Footer** — Explore all topics | Archive

### CSS Classes (key)
- `.cc-controversy` — debate section wrapper
- `.cc-controversy-label` — red uppercase label "The Evangelical Debate"
- `.cc-debate-grid.three-way` — 3-column grid
- `.cc-debate-side.side-a/b/c` — colored top border (green/brown/blue)
- `.cc-key-questions` — green left-border box
- `.cc-synthesis` — synthesis section
- `.cc-article-entry` — numbered article with annotation

## The 70 Topic Pages

Generated from `frontend/topics_data.py` on 2026-09-25. Page titles are the live `<title>` values (minus the ` — Christian Curator` suffix). The seven `On On` double prefixes and six `| Christian Curator` suffixes were fixed on 2026-10-25; On 2026-10-26 five topics (apologetics, biblical-inerrancy, biblical-literacy, discipleship, faith-deconstruction) moved to search-intent titles; their canonical `seo_title`/`seo_description` live in `topics_data.py` and `scripts/apply_aeo_upgrades.py` honours them.

### Core Theology (17)

| Slug | Page title |
|------|------------|
| apologetics | What Is Christian Apologetics? |
| atonement | On the Atonement |
| baptism | On Baptism |
| biblical-inerrancy | What Is Biblical Inerrancy? |
| christology | On Christology |
| covenant-theology | On Covenant Theology |
| creation-evolution | On Creation & Science |
| eschatology | On Eschatology & the End Times |
| gender-and-biblical-anthropology | On Gender & Biblical Anthropology |
| heaven-hell-eternity | On Heaven, Hell & Eternity |
| holy-spirit-spiritual-gifts | On the Holy Spirit & Spiritual Gifts |
| israel-and-prophecy | On Israel & Prophecy |
| justification-by-faith | On Justification by Faith |
| lords-supper | On the Lord's Supper |
| predestination-free-will | On Predestination & Free Will |
| suffering-and-providence | On Suffering & Providence |
| the-trinity | On the Trinity |

### Church Life (14)

| Slug | Page title |
|------|------------|
| church-accountability | On Pastoral Accountability |
| church-discipline | On Church Discipline |
| church-governance | On Church Governance |
| church-history | On Church History |
| church-planting | On Church Planting |
| complementarianism-egalitarianism | On Men, Women & the Church |
| local-church | On the Local Church |
| membership | On Church Membership |
| missions-and-evangelism | On Missions & Evangelism |
| pastoral-ministry | On The Pastor's Role |
| preaching | On Preaching |
| small-groups | On Small Groups |
| spiritual-abuse | On Spiritual Abuse |
| worship-and-liturgy | On Worship & Liturgy |

### Spiritual Formation (17)

| Slug | Page title |
|------|------------|
| anxiety-and-fear | On Anxiety & Fear |
| biblical-literacy | Biblical Literacy: How to Read the Bible |
| christian-friendship | On Christian Friendship |
| contemplative-prayer | On Contemplative Prayer |
| death-and-dying | On Death & Dying |
| discipleship | Discipleship: How to Make Disciples |
| faith-deconstruction | What Is Faith Deconstruction? |
| fasting | On Fasting |
| forgiveness | On Forgiveness |
| grief-and-lament | On Grief & Lament |
| mental-health | On Mental Health & the Church |
| pornography | On Pornography & Sexual Purity |
| prayer | On Prayer |
| sanctification | On Sanctification |
| singleness | On Singleness |
| spiritual-disciplines | On the Spiritual Disciplines |
| spiritual-warfare | On Spiritual Warfare |

### Culture & Society (22)

| Slug | Page title |
|------|------------|
| abortion | On Abortion & the Pro-Life Movement |
| addiction-and-recovery | On Addiction & Recovery |
| ai-and-the-church | On Artificial Intelligence & the Church |
| biblical-justice | On Biblical Justice & the Social Gospel |
| biblical-sexuality | On Biblical Sexuality |
| christian-education | On Christian Education |
| christian-ethics | On Christian Ethics |
| christian-masculinity | On Christian Masculinity |
| christian-nationalism | On Christian Nationalism |
| christian-parenting | On Raising Children in the Faith |
| creation-care | On Creation Care |
| evangelicalism | On Evangelicalism |
| marriage-and-family | On Marriage & Family |
| politics-and-the-church | On the Church & Political Life |
| progressive-christianity | On Progressive Christianity |
| prosperity-gospel | On the Prosperity Gospel |
| racial-reconciliation | On Racial Reconciliation |
| religious-liberty | On Religious Liberty |
| stewardship-and-generosity | On Stewardship & Generosity |
| technology | On Technology & the Christian Life |
| technology-and-discipleship | On Technology & Discipleship |
| vocation-and-work | On Vocation & Work |


## SEO Fixes Applied (April 2026)
- Removed `/topics/` index page from sitemap.xml (was a soft 404 signal)
- Unified meta description and og:description across `frontend/template.html`
- Removed "debate" language from topic page meta descriptions (22 pages patched)
- All topic page meta descriptions kept ≤160 characters

## Article Source Pool
Standard evangelical publishers used for curated article lists:
- The Gospel Coalition (thegospelcoalition.org)
- Desiring God (desiringgod.org)
- Crossway (crossway.org)
- Ligonier (ligonier.org)
- 9Marks (9marks.org)
- Christianity Today (christianitytoday.com)
- Tabletalk / Ligonier
- ERLC (erlc.com)
- Mere Orthodoxy (mereorthodoxy.com)
- First Things (firstthings.com)
- Acts 29 (acts29.com)
- CCEF (ccef.org)
- BioLogos (biologos.org)

## Design Tokens
- Primary green: `#2C4A2E`
- Debate red: `#8B1A1A`
- Side-b brown: `#8B4513`
- Side-c blue: `#4A4A8B`
- Background: `#faf9f7`
- Body text: `#1a1a1a`
- Fonts: Lora (serif, headings), Source Sans 3 (sans, body)
