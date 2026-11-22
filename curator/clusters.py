"""
clusters.py: homepage story clustering (P2.2, 2026-10-30; story identity, S2 Nov 22 2026).

When several outlets cover one story, the homepage shows the story once, at
its best-ranked article, with an "also:" line linking the other outlets
(RealClearPolitics / Memeorandum style).

A story is an event, study or statement, not a theme. Until Nov 22 2026 the
grouping key was the scorer's `topic_cluster`, which names themes
("christian_nationalism_debate"), so a First Things essay carried "also:"
links to a Carey Nieuwhof episode on fear and a Stephen McAlpine essay, while
one Pew 2035/2070 projection showed five times because each copy got its own
cluster string. Grouping now uses story identity (`same_story()`):

  * distinctive names shared by the two articles: capitalised words in the
    headline (feed, rewritten and publisher versions) and the snippet, minus
    common headline and faith vocabulary (`STOP`) and minus any word the
    day's pool also writes in lower case (rewritten headlines are Title
    Case, so "Argues" or "Parents" is not a name), lightly stemmed
    ("Projected" / "Projections" -> "project"). A name in both headlines
    weighs 1, a name found only in a snippet 0.5.
  * distinctive numbers shared: 3+ digit figures and percentages, not the
    current year (weight 1.5, or 0.75 when only in a snippet). "2035" and
    "2070" tie the Pew copies together.
  * the publisher's own name counts as a name of the article (Pew's release
    and "Pew projects..." elsewhere), at most 1 in total; one of the day's
    publishers named in both headlines of two other outlets adds 1 more.
  * a shared `story_id` (when a caller sets one) decides on its own; a shared
    non-generic `topic_cluster` adds only 0.5.

Two articles are the same story at weight >= STORY_MIN_WEIGHT (2): a number
plus a name, or two names. Stories are the connected groups of that relation.

Outlets for a story also count copies that curator/dedup.py collapsed into
the survivor (`also_from` / `also_links`). A story qualifies when it has at
least MIN_OUTLETS distinct sources, or MIN_OUTLETS articles from two or more. The representative is the first member in
the ranked list passed in (callers pass importance order). Other members
become siblings: at most one per source, up to MAX_SIBLINGS, and they are
suppressed elsewhere on the page. No API clients here, so render-only scripts
can import it.
"""

import re
from datetime import date

MIN_OUTLETS = 3
MAX_SIBLINGS = 4
NO_CLUSTER = {"", "unique", "none", "other"}
STORY_MIN_WEIGHT = 2.0
SNIPPET_CHARS = 300

# Capitalised words that say nothing about which story a headline covers:
# function words (Title Case headlines capitalise them), headline verbs, and
# the everyday vocabulary of Christian publishing.
STOP = set("""
a an the and or nor but yet so of in on at by for to from with without within into onto over under
about above after before against among around as between beyond during through toward towards until
up down out off upon via per than then there here now today tonight week weeks year years day days
month months time times is are was were be been being am do does did done has have had having will
would shall should can could may might must not no yes it its it's this that these those he she they
we you i me my mine our ours your yours his her hers their theirs them us him who whom whose what which
when where why how all any each every both either neither some many much more most less least few
other another such same own only just still also even very too again ever never always often new old
one two three four five six seven eight nine ten first second third last next says say said tells
told show shows showed make makes made take takes took get gets got keep keeps kept need needs want
wants find finds found help helps become becomes became come comes came give gives gave go goes going
see sees seen know knows look looks call calls calling way ways part life lives people world thing
things case report reports study studies new news opinion podcast video episode ep review data
analysis update interview q&a q a vs live watch listen read why
god god's jesus christ christ's lord holy spirit christian christians christianity church churches
bible biblical gospel gospels faith faithful evangelical evangelicals evangelicalism pastor pastors
believers believer religion religions religious theology theological scripture scriptures prayer
pray worship ministry ministries mission missions catholic catholics protestant protestants baptist
baptists america american americans us u.s. united states nation national however meanwhile many
editor editors author authors writer writers press magazine journal service post times daily
weekly monthly center centre institute
argue argues argued arguing scholar scholars historian historians expert experts critic critics
leader leaders warn warns warned explain explains explained urge urges urged offer offers offered
reveal reveals revealed face faces faced calls called argue's why's book books new-york
""".split())

# A capitalised word that also appears in lower case anywhere in the day's
# pool ("Argues", "Parents", "Project" in Title Case headlines) is ordinary
# vocabulary, not a name. Only words capitalised everywhere they appear
# (Pew, Muslims, Islam, Dannenfelser) count. Built per run in
# build_story_clusters(); same_story() on its own uses STOP alone.
_LOWER_RE = re.compile(r"(?<![\w'’-])[a-z][\w'’-]*")
POOL_TEXT_CHARS = 3000

_NAME_RE = re.compile(r"[A-Z][\w'’&.-]*")
_NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")
_SUFFIXES = ("ions", "ion", "ings", "ing", "ed", "es", "s")


def _plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"https?://\S+", " ", text)
    return " ".join(text.split())


def _stem(word: str) -> str:
    w = word.lower().strip(".'’-&")
    w = re.sub(r"['’]s$", "", w)
    if w in STOP:
        return ""
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[: -len(suf)]
            break
    return "" if len(w) < 3 or w in STOP else w


def _names(text: str, generic: frozenset = frozenset()) -> set:
    return {s for s in (_stem(w) for w in _NAME_RE.findall(text)) if s and s not in generic}


def _pool_text(a: dict) -> str:
    body = " ".join(_plain(a.get(key) or "")[:POOL_TEXT_CHARS]
                    for key in ("description", "summary", "excerpt", "full_content"))
    titles = " ".join(t for t in (a.get("title"), a.get("rewritten_title"),
                                  a.get("original_title")) if t)
    return f"{titles} {body[:POOL_TEXT_CHARS]}"


def generic_vocabulary(pool: list[dict]) -> frozenset:
    """Stems of every word the pool also writes in lower case."""
    out = set()
    for a in pool:
        for w in _LOWER_RE.findall(_pool_text(a)):
            st = _stem(w)
            if st:
                out.add(st)
    return frozenset(out)


def _numbers(text: str) -> set:
    this_year = date.today().year
    out = set()
    for raw in _NUM_RE.findall(text):
        n = raw.replace(",", "")
        if n.endswith("%"):
            out.add(n)
            continue
        try:
            value = float(n)
        except ValueError:
            continue
        if value >= 100 and int(value) not in (this_year - 1, this_year, this_year + 1):
            out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def _snippet(a: dict) -> str:
    for key in ("description", "summary", "excerpt"):
        s = _plain(a.get(key) or "")
        if len(s) >= 40:
            return s[:SNIPPET_CHARS]
    return ""


def story_tokens(a: dict, generic: frozenset = frozenset()) -> dict:
    """Names and numbers that identify the story an article covers.
    `generic` is the pool's lower-case vocabulary (generic_vocabulary())."""
    titles = " | ".join(t for t in {a.get("title"), a.get("rewritten_title"),
                                    a.get("original_title")} if t)
    snippet = _snippet(a)
    return {
        "title_names": _names(titles, generic),
        "body_names": _names(snippet, generic),
        "title_nums": _numbers(titles),
        "body_nums": _numbers(snippet),
        "source": _names(a.get("source_name") or ""),
    }


def story_weight(a: dict, b: dict, ta: dict | None = None, tb: dict | None = None,
                 publishers: tuple = ()) -> float:
    """Evidence that `a` and `b` report the same story (see module doc).
    `publishers` holds each of the day's sources as its set of distinctive
    name tokens ({"pew"} for Pew Research)."""
    ta = ta or story_tokens(a)
    tb = tb or story_tokens(b)
    weight = 0.0
    names_a = ta["title_names"] | ta["body_names"]
    names_b = tb["title_names"] | tb["body_names"]
    for n in names_a & names_b:
        weight += 1.0 if n in ta["title_names"] and n in tb["title_names"] else 0.5
    nums_a = ta["title_nums"] | ta["body_nums"]
    nums_b = tb["title_nums"] | tb["body_nums"]
    for n in nums_a & nums_b:
        weight += 1.5 if n in ta["title_nums"] and n in tb["title_nums"] else 0.75
    # The publisher named in the other article's headline or snippet: one
    # point at most, so two unrelated releases from one outlet never match.
    if (ta["source"] & (names_b - names_a)) or (tb["source"] & (names_a - names_b)):
        weight += 1.0
    # Two other outlets naming one publisher in their headlines ("Pew
    # projects...", "Pew Research moves up...") are covering its release.
    both = ta["title_names"] & tb["title_names"]
    if any(p <= both and not p <= ta["source"] and not p <= tb["source"] for p in publishers):
        weight += 1.0
    ca = (a.get("topic_cluster") or "").strip().lower()
    if ca not in NO_CLUSTER and ca == (b.get("topic_cluster") or "").strip().lower():
        weight += 0.5
    return weight


def same_story(a: dict, b: dict, ta: dict | None = None, tb: dict | None = None,
               publishers: tuple = ()) -> bool:
    sa, sb = a.get("story_id"), b.get("story_id")
    if sa and sb:
        return sa == sb
    return story_weight(a, b, ta, tb, publishers) >= STORY_MIN_WEIGHT


def story_groups(ranked: list[dict], generic: frozenset | None = None) -> list[list[dict]]:
    """Connected groups of same-story articles, in ranked order of their
    first member; each group's members keep ranked order. `generic` defaults
    to the pool's own lower-case vocabulary."""
    items = [a for a in ranked if a.get("url")]
    if generic is None:
        generic = generic_vocabulary(items)
    tokens = [story_tokens(a, generic) for a in items]
    publishers = tuple({frozenset(p) for t in tokens if (p := t["source"] - generic)})
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if find(i) != find(j) and same_story(items[i], items[j], tokens[i], tokens[j], publishers):
                parent[max(find(i), find(j))] = min(find(i), find(j))
    groups: dict[int, list[dict]] = {}
    for i, a in enumerate(items):
        groups.setdefault(find(i), []).append(a)
    return [groups[k] for k in sorted(groups)]


def _sibling(a: dict) -> dict:
    return {"source_name": a.get("source_name", ""), "url": a.get("url", ""),
            "title": a.get("rewritten_title") or a.get("title", "")}


def build_story_clusters(ranked: list[dict], min_outlets: int = MIN_OUTLETS,
                         max_siblings: int = MAX_SIBLINGS,
                         generic: frozenset | None = None) -> tuple[dict, set]:
    """Group ranked articles into multi-outlet stories.

    Returns (siblings_by_url, suppressed_urls):
      siblings_by_url  representative URL -> [{source_name, url, title}]
      suppressed_urls  URLs of cluster members other than the representative

    Articles that pair with nothing still get siblings when dedup folded in
    enough copies from other outlets. Empty results are normal on most days.
    """
    siblings_by_url: dict[str, list[dict]] = {}
    suppressed: set = set()
    for members in story_groups(ranked, generic):
        rep = members[0]
        rep_src = rep.get("source_name", "")
        outlets = {rep_src}
        sibs: list[dict] = []
        seen = {rep_src}
        for m in members[1:]:
            outlets.add(m.get("source_name", ""))
            if m.get("source_name", "") not in seen:
                sibs.append(_sibling(m))
                seen.add(m.get("source_name", ""))
        for m in members:
            outlets |= set(m.get("also_from") or [])
            for link in m.get("also_links") or []:
                outlets.add(link.get("source_name", ""))
                if link.get("url") and link.get("source_name") not in seen:
                    sibs.append(dict(link))
                    seen.add(link.get("source_name"))
        outlets.discard("")
        # Three copies of one story collapse even from two outlets (Pew's
        # own two releases plus CT's write-up, Nov 21 2026).
        if sibs and (len(outlets) >= min_outlets or len(members) >= min_outlets):
            siblings_by_url[rep["url"]] = sibs[:max_siblings]
            suppressed |= {m["url"] for m in members[1:]}
        # Under threshold: members stay separate headlines.
    return siblings_by_url, suppressed
