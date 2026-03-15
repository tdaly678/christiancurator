# ChristianCurator

An automated pipeline that fetches, scores, and curates Christian news articles using Claude AI.

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/christiancurator.git
cd christiancurator
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## Usage

```bash
python main.py
```

## Project Structure

```
christiancurator/
├── .github/workflows/   # GitHub Actions cron job
├── fetcher/             # RSS feed fetching
├── curator/             # Claude-powered scoring, tagging, rewriting
├── output/              # JSON output + HTML generation
├── frontend/            # HTML template
├── main.py              # Pipeline orchestrator
└── requirements.txt
```

## Layers

1. **Fetcher** — pulls articles from RSS feeds defined in `fetcher/sources.py`
2. **Curator** — uses Claude to score relevance, rewrite titles, and match point/counterpoint pairs
3. **Output** — writes `articles.json` and regenerates `index.html`
