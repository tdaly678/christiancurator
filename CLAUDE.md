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

**Always pull before pushing.** GitHub Actions commits to `main` every morning at 6:00 AM UTC, so a local run
that skips the pull will be rejected as non fast forward:

```bash
cd ~/Projects/christiancurator
git pull --no-rebase origin main
# ... make changes ...
git add <files> && git commit -m "..." && git push origin main
```


## Daily Pipeline (GitHub Actions)
Runs automatically at **6:00 AM UTC** via `.github/workflows/daily_run.yml`.

What it commits: `docs/index.html`, `docs/topics/`, `docs/digest/`, `docs/yesterday.json`, `docs/email_draft.html`,
`docs/article_history.json`, `docs/research_articles.json`, all five sitemaps (`sitemap.xml`, `sitemap-core.xml`,
`sitemap-topics.xml`, `sitemap-voices.xml`, `sitemap-archive.xml`, `sitemap-daily.xml`), `docs/archive/`, `docs/daily/`,
`docs/_pagefind/`, `docs/voices/`, `docs/voices_data.json`, `docs/spotlight_topic_log.json`, `docs/feed_health.json`.

### Feed health and source roles (added 2026-10-30)
`fetcher/rss_fetcher.py` fetches feeds with `requests` (15s timeout, browser UA with a feed-reader UA retry, 8 threads)
and writes `docs/feed_health.json` every run: per-source `http_status`, `n_entries`, `newest_date`, `bozo`, `stale`,
`error`, plus `zero_streaks` (consecutive run days with 0 items). `scripts/check_feed_health.py` runs after the commit
and fails the workflow once any configured source hits 7 days at 0 items. Fix the URL in `fetcher/sources.py` or remove
the source.

Sources can set `role: "discovery"` (fetched and health-logged, never ranked: The Aquila Report) or a
`discovery_title_pattern` (Tim Challies' A La Carte / Kindle deals / book roundups). `score_articles()` drops discovery
items before Claude scoring.

`docs/article_history.json` rows carry `base_score` (Claude's editorial score before boosts), `boosts` (actual delta per
mechanism), and `scored_by` (`claude` / `fallback`). Rows from 2026-09-06 to 2026-10-25 (Anthropic credit outage) are
marked `scored_by: "fallback"`, `scored_by_backfilled: true` by `scripts/backfill_scored_by.py`; exclude them when tuning.

Steps after the pipeline itself: backfill orphan voice pages, rebuild the `/topics/` hub index, rebuild the `/voices/`
category hubs, refresh recent-articles sections, inject the Featured deep dives block, regenerate the sitemaps,
build the Pagefind index, commit, then ping IndexNow.

### Sitemaps — there are six files, not one
`docs/sitemap.xml` is an **index** that points at three children: `sitemap-core.xml` (6 URLs), `sitemap-topics.xml` (70),
`sitemap-voices.xml` (1,158). `sitemap-daily.xml` and `sitemap-archive.xml` are still written by `regenerate_sitemap()` but,
since 2026-10-26, are deliberately **not listed** in the index (crawl budget goes to topics and voices). Anything that
suppresses a page must also remove it from the relevant child sitemap, or the signals conflict.

Voice pages listed in `frontend/voices_noindex.json` are skipped by the sitemap generator. Merged duplicate voices are
recorded in `frontend/voices_redirects.json` (loser → survivor); the loser's page is a noindex meta-refresh stub, and
`scripts/merge_duplicate_voices.py` holds the pair list.

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

### Idempotent injection markers
Cross-cutting scripts inject content-additive blocks using HTML-comment markers so re-runs replace the block in place instead of duplicating it. When extending any of these, update between the markers rather than editing around them:

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
Structure:
1. Date line + "Forwarded to you? Subscribe Free" banner
2. Masthead + byline: *"For curious Christians seeking clarity on the questions that matter most"*
3. **Today's Top Stories**: first 5 of the homepage's diversified front-page cards
4. **The Daily Pulse**: `daily_summary["paragraphs_html"]` plus a link to `/daily/YYYY-MM-DD/`; omitted when the summary is missing or empty
5. **More Headlines**: the other front-page cards + "Other Headlines", then up to 3 World News items
6. CTA to the homepage, then the **Go Deeper** spotlight topic (rotation logged in `docs/spotlight_topic_log.json`, no repeats for 70 days)
7. Forward nudge + footer

Every headline links **directly to the article URL**. (Homepage anchors `/#a<hash>` were dropped in October 2026 because
the next day's re-render removes them; if an article has no URL the link falls back to `/archive/YYYY-MM-DD/`.)
Subject line: `{lead headline} · + N more stories`, lead truncated at 70 characters (`build_subject()`).

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
