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
  - `docs/topics/[slug]/index.html` — 46 topic pages
  - `docs/daily/[date]/index.html` — daily editorial pulse pages
  - `docs/sitemap.xml` — SEO sitemap (auto-generated daily)
- `frontend/` — Jinja2 templates + rendering code
  - `frontend/template.html` — homepage template
  - `frontend/digest_template.html` — Daily Digest template (mirrors homepage layout)
  - `frontend/archive_template.html` — per-day archive template
  - `frontend/topics_data.py` — canonical 46-topic taxonomy (slug, name, category, hook, summary, keywords)
  - `frontend/__init__.py` — render functions: render_html(), render_digest_page(), render_archive_page(), render_archive_index()
- `curator/` — scoring, classification, email
  - `curator/topic_classifier.py` — keyword classifier mapping articles → topic slugs
  - `curator/email_sender.py` — Brevo email builder
- `fetcher/` — RSS/web fetching
- `main.py` — main pipeline entry point
- `regenerate_daily.py` — re-render pages from cached articles (requires Claude API for daily summary)
- `/tmp/rerender_only.py` — minimal re-render script (no Claude API needed; recreate each session from session notes)

## Git Push Workaround
The mounted filesystem has a persistent `index.lock` that blocks git operations. **Always push via a temp clone:**

```bash
git clone https://tdaly678:[TOKEN]@github.com/tdaly678/christiancurator.git /tmp/check_repo
cd /tmp/check_repo
git config user.email "tdaly@brookstoneind.com"
git config user.name "Christian Curator"
# copy files, then:
git add [files]
git commit -m "..."
git push origin main
```

GitHub token is stored in `.env` as `GITHUB_TOKEN`. Username is `tdaly678`.

The `/tmp/` directory is cleared between sessions, so re-clone if `/tmp/check_repo` doesn't exist.

## Daily Pipeline (GitHub Actions)
Runs automatically at **6:00 AM UTC** via `.github/workflows/daily_run.yml`.

What it commits: `docs/index.html`, `docs/digest/`, `docs/yesterday.json`, `docs/email_draft.html`, `docs/article_history.json`, `docs/research_articles.json`, `docs/sitemap.xml`, `docs/archive/`, `docs/daily/`, `docs/_pagefind/`

## Navigation Structure (3-item nav, all pages)
```
Home  |  Daily Digest  |  Archive
```
- Homepage: Home is `.active`
- Digest page: Daily Digest is `.active`
- Archive pages: Archive is `.active`

CSS class: `.cc-nav`. All archive day pages were patched to include this nav in April 2026.

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

## Email Design (Updated April 2026)
Daily email via Brevo API. Structure:
1. Forwarded banner
2. Masthead + byline: *"For curious Christians seeking clarity on the questions that matter most"*
3. **"In the Conversation Today"** — top featured topic card (name, summary, article list)
4. **"In Case You Missed It — Yesterday"** — yesterday's top topic card (never the same slug as today's)
5. CTA to homepage
6. Forward nudge + footer

Topic deduplication uses `output/featured_topic_log.json` (today) and `output/sent_topic_log.json` (what was emailed before).

## Topic Pages — Structure (46 topics as of April 2026)

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

## The 46 Topic Pages

### Core Theology (12)
| Slug | Title |
|------|-------|
| apologetics | On Defending the Faith |
| atonement | On the Atonement |
| baptism | On Baptism |
| biblical-inerrancy | On the Authority of Scripture |
| creation-evolution | On Creation & Science |
| gender-and-biblical-anthropology | On Gender & Biblical Anthropology |
| heaven-hell-eternity | On Heaven, Hell & Eternity |
| holy-spirit-spiritual-gifts | On the Holy Spirit & Spiritual Gifts |
| justification-by-faith | On Justification by Faith |
| lords-supper | On the Lord's Supper |
| predestination-free-will | On Predestination & Free Will |
| suffering-and-providence | On Suffering & Providence |
| the-trinity | On the Trinity |

### Church Life (11)
| Slug | Title |
|------|-------|
| church-accountability | On Pastoral Accountability |
| church-discipline | On Church Discipline |
| church-history | On Church History |
| church-planting | On Church Planting |
| complementarianism-egalitarianism | On Men, Women & the Church |
| discipleship | On Making Disciples |
| local-church | On the Local Church |
| membership | On Church Membership |
| missions-and-evangelism | On Missions & Evangelism |
| politics-and-the-church | On the Church & Political Life |
| preaching | On Preaching |
| worship-and-liturgy | On Worship & Liturgy |

### Spiritual Formation (9)
| Slug | Title |
|------|-------|
| anxiety-and-fear | On Anxiety & Fear |
| contemplative-prayer | On Contemplative Prayer |
| faith-deconstruction | On Deconstruction & Faith |
| fasting | On Fasting |
| mental-health | On Mental Health & the Church |
| prayer | On Prayer |
| sanctification | On Sanctification |
| spiritual-disciplines | On the Spiritual Disciplines |
| spiritual-warfare | On Spiritual Warfare |

### Culture & Society (10)
| Slug | Title |
|------|-------|
| ai-and-the-church | On Artificial Intelligence & the Church |
| biblical-justice | On Biblical Justice & the Social Gospel |
| biblical-sexuality | On Biblical Sexuality |
| christian-ethics | On Christian Ethics |
| christian-nationalism | On Christian Nationalism |
| christian-parenting | On Raising Children in the Faith |
| evangelicalism | On the Future of Evangelicalism |
| marriage-and-family | On Marriage & Family |
| racial-reconciliation | On Racial Reconciliation |
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
