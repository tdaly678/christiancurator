"""
clusters.py: homepage story clustering (P2.2, 2026-10-30).

When several outlets cover one story, the homepage shows the story once, at
its best-ranked article, with an "also:" line linking the other outlets
(RealClearPolitics / Memeorandum style).

Outlets for a story come from two fields the pipeline already sets:
  * topic_cluster: the scorer's snake_case story key. "unique" and "" never
    cluster.
  * also_links / also_from: copies that curator/dedup.py collapsed into the
    survivor (same canonical URL or same title from another feed).

A story qualifies when it has at least MIN_OUTLETS distinct sources. The
representative is the first member in the ranked list passed in (callers pass
importance order). Other members become siblings: at most one per source, up
to MAX_SIBLINGS, and they are suppressed elsewhere on the page. No API
clients here, so render-only scripts can import it.
"""

MIN_OUTLETS = 3
MAX_SIBLINGS = 4
NO_CLUSTER = {"", "unique", "none", "other"}


def _sibling(a: dict) -> dict:
    return {"source_name": a.get("source_name", ""), "url": a.get("url", ""),
            "title": a.get("rewritten_title") or a.get("title", "")}


def build_story_clusters(ranked: list[dict], min_outlets: int = MIN_OUTLETS,
                         max_siblings: int = MAX_SIBLINGS) -> tuple[dict, set]:
    """Group ranked articles into multi-outlet stories.

    Returns (siblings_by_url, suppressed_urls):
      siblings_by_url  representative URL -> [{source_name, url, title}]
      suppressed_urls  URLs of cluster members other than the representative

    Articles with no cluster still get siblings when dedup folded in enough
    copies from other outlets. Empty results are normal on most days.
    """
    groups: dict[str, list[dict]] = {}
    order: list = []
    for a in ranked:
        if not a.get("url"):
            continue
        key = (a.get("topic_cluster") or "").strip().lower()
        if key in NO_CLUSTER:
            order.append(a)
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(a)

    siblings_by_url: dict[str, list[dict]] = {}
    suppressed: set = set()
    for item in order:
        members = [item] if isinstance(item, dict) else groups[item]
        rep = members[0]
        rep_src = rep.get("source_name", "")
        outlets = {rep_src} | set(rep.get("also_from") or [])
        sibs: list[dict] = []
        seen = {rep_src}
        for m in members[1:]:
            outlets.add(m.get("source_name", ""))
            outlets |= set(m.get("also_from") or [])
            suppressed.add(m["url"])
            if m.get("source_name", "") not in seen:
                sibs.append(_sibling(m))
                seen.add(m.get("source_name", ""))
        for m in members:
            for link in m.get("also_links") or []:
                outlets.add(link.get("source_name", ""))
                if link.get("url") and link.get("source_name") not in seen:
                    sibs.append(dict(link))
                    seen.add(link.get("source_name"))
        outlets.discard("")
        if len(outlets) >= min_outlets and sibs:
            siblings_by_url[rep["url"]] = sibs[:max_siblings]
        elif not isinstance(item, dict):
            # Under threshold: members stay separate headlines.
            suppressed -= {m["url"] for m in members[1:]}
    return siblings_by_url, suppressed
