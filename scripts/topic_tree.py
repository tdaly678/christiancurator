"""topic_tree.py: the "tree" type for build_topic_timeline.py (a family tree of movements).

  "type": "tree",
  "span": [1500, 2030],                       # years on the axis
  "families": [{"id", "name", "short", "color",
                "parent": "<family id>" | null, "parent_text": "grew out of ... (phone and table)",
                "influence": [{"from": "<family id>", "text": "..."}],   # dashed links, optional
                "nodes": [{"year": 1517, "label": "Luther's 95 Theses", "short": "95 Theses",
                           "source": "<source id>", "table_only": false}],  # first node = origin
                "proponent": {...}}]          # the source shown in the voices list

Wide image: one row per family on a shared year axis, a filled dot at the origin, hollow dots
for later milestones, and a connector from the parent row (solid) or an influence (dashed) at
the origin year. Rows are drawn in data order, so put each child next to its parent
(a connector may run up or down).
Phone image: one card per family, in the same order, with its "grew out of" line and dated
milestones. Every node cites a source.
"""
from __future__ import annotations


def bt():
    import build_topic_timeline as m  # late import: build_topic_timeline imports this module
    return m


def validate_tree(d: dict) -> list[str]:
    errs: list[str] = []
    span = d.get("span") or []
    if len(span) != 2 or not all(isinstance(x, int) for x in span) or span[0] >= span[1]:
        return ["span must be [first year, last year]"]
    fams = d["families"]
    if not 2 <= len(fams) <= 10:
        errs.append("tree takes 2 to 10 families")
    ids = [f.get("id") for f in fams]
    if len(set(ids)) != len(ids) or not all(ids):
        errs.append("family ids must be unique and present")
    srcs = {s.get("id") for s in d.get("sources") or []}
    for f in fams:
        fid = f.get("id", "?")
        for link in [f.get("parent")] + [i.get("from") for i in f.get("influence") or []]:
            if link and (link not in ids or link == fid):
                errs.append(f"family {fid}: {link!r} is not another family")
        nodes = f.get("nodes") or []
        if not nodes:
            errs.append(f"family {fid}: needs nodes")
        years = [n.get("year") for n in nodes]
        if any(not isinstance(y, int) or not span[0] <= y <= span[1] for y in years):
            errs.append(f"family {fid}: node years must sit inside the span")
        elif years != sorted(years):
            errs.append(f"family {fid}: nodes must be in year order")
        for n in nodes:
            if not n.get("label"):
                errs.append(f"family {fid}: a node needs a label")
            if n.get("source") not in srcs:
                errs.append(f"family {fid}: node {n.get('label')!r} cites unknown source {n.get('source')!r}")
        if f.get("parent") and not f.get("parent_text"):
            errs.append(f"family {fid}: parent_text says what it grew out of")
    return errs


def describe_tree(d: dict) -> str:
    names = {f["id"]: f["name"] for f in d["families"]}
    out = []
    for f in d["families"]:
        nodes = "; ".join(f"{n['year']} {n['label']}" for n in f["nodes"])
        grew = f" {f['parent_text']}." if f.get("parent_text") else ""
        infl = "".join(f" Influence from {names[i['from']]}: {i['text']}." for i in f.get("influence") or [])
        out.append(f"{f['name']}:{grew}{infl} {nodes}.")
    return " ".join(out)


def _label(m, x: float, y: float, text: str, size: float, fill: str, weight, right: float) -> str:
    w = m.text_w(text, size, weight == "600")
    out = m.tx(x, y, text, size, fill, weight, "end" if x + w > right else None)
    # a white halo keeps connector lines that cross a label from cutting through it
    return out.replace("<text ", '<text stroke="#fff" stroke-width="3" paint-order="stroke" ', 1)


def render_tree(d: dict, narrow: bool) -> str:
    m = bt()
    w = m.W_NARROW if narrow else m.W_WIDE
    sub = (d.get("image_subtitle_narrow") if narrow else None) or d.get("image_subtitle", "")
    parts, y = m.header(d, w, sub)
    fams = d["families"]
    names = {f["id"]: f for f in fams}
    if narrow:
        for f in fams:
            col = m.color(f.get("color"))
            lines = []
            if f.get("parent_text"):
                lines.append(("grew", f["parent_text"]))
            for i in f.get("influence") or []:
                lines.append(("grew", i["text"]))
            body_w = w - 2 * m.PAD - 16
            wrapped = []
            for kind, text in lines:
                wrapped += [(kind, ln) for ln in m.wrap(text, body_w, 11.5)]
            for n in f["nodes"]:
                wrapped += [("node", ln) for ln in m.wrap(f"{n['year']}  {n.get('short') or n['label']}", body_w, 12)]
            h = 24 + len(wrapped) * 15 + 6
            parts.append(f'<rect x="{m.PAD}" y="{y:.1f}" width="{w - 2 * m.PAD}" height="{h:.1f}" rx="5" '
                         f'fill="{col}" fill-opacity="0.07"/>')
            parts.append(f'<rect x="{m.PAD}" y="{y:.1f}" width="4" height="{h:.1f}" rx="2" fill="{col}"/>')
            parts.append(m.tx(m.PAD + 12, y + 17, f["name"], 13.5, col, "700"))
            yy = y + 24
            for kind, ln in wrapped:
                yy += 15
                fill, weight = (m.GREY, None) if kind == "grew" else (m.INK, None)
                parts.append(m.tx(m.PAD + 12, yy - 3, ln, 11.5 if kind == "grew" else 12, fill, weight))
            y += h + 6
        foot, y = m.footer(d, y + 8, w, 11)
        return m.svg_open(d, w, y, True) + "".join(parts) + foot + "</svg>"

    label_w, row_h = 112, 36
    x0, x1 = m.PAD + label_w, w - m.PAD - 4
    a, b = d["span"]

    def X(year: float) -> float:
        return x0 + (year - a) / (b - a) * (x1 - x0)

    # year axis
    tick0 = (a // 100 + (1 if a % 100 else 0)) * 100
    for yr in range(tick0, b + 1, 100):
        parts.append(f'<line x1="{X(yr):.1f}" x2="{X(yr):.1f}" y1="{y + 14:.1f}" '
                     f'y2="{y + 18 + len(fams) * row_h:.1f}" stroke="{m.GRID}"/>')
        parts.append(m.tx(X(yr), y + 10, str(yr), 11, m.GREY, "600", "middle"))
    y += 22
    mids = {f["id"]: y + i * row_h + row_h / 2 + 4 for i, f in enumerate(fams)}
    # connectors first, so dots sit on top
    for f in fams:
        col = m.color(f.get("color"))
        start = f["nodes"][0]["year"]
        links = ([(f["parent"], False)] if f.get("parent") else []) + [(i["from"], True) for i in f.get("influence") or []]
        for k, (src, dashed) in enumerate(links):
            xx = X(start) - (7 * k if dashed else 0)
            dash = ' stroke-dasharray="3 3"' if dashed else ""
            pc = m.color(names[src].get("color"))
            parts.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{mids[src]:.1f}" y2="{mids[f["id"]]:.1f}" '
                         f'stroke="{pc if dashed else col}" stroke-width="1.6"{dash}/>')
    for f in fams:
        col = m.color(f.get("color"))
        mid = mids[f["id"]]
        name_lines, ns = m.fit(f.get("short") or f["name"], label_w - 8, 12.5, True, max_lines=1)
        parts.append(m.tx(m.PAD, mid + 4, name_lines[0], ns, col, "700"))
        drawn = [n for n in f["nodes"] if not n.get("table_only")]
        start = drawn[0]["year"]
        parts.append(f'<line x1="{X(start):.1f}" x2="{x1:.1f}" y1="{mid:.1f}" y2="{mid:.1f}" stroke="{col}" '
                     f'stroke-width="3" stroke-linecap="round"/>')
        for k, n in enumerate(drawn):
            x = X(n["year"])
            if k == 0:
                parts.append(f'<circle cx="{x:.1f}" cy="{mid:.1f}" r="5.5" fill="{col}"/>')
                parts.append(_label(m, x - 4, mid - 8, f"{n['year']} {n.get('short') or n['label']}", 11, m.INK, "600", x1))
            else:
                parts.append(f'<circle cx="{x:.1f}" cy="{mid:.1f}" r="4.5" fill="#fff" stroke="{col}" stroke-width="2"/>')
                parts.append(_label(m, x + 7, mid + 15, f"{n['year']} {n.get('short') or n['label']}", 10.5, m.GREY, None, x1))
    y += len(fams) * row_h + 4
    key = [(f'<line x1="{m.PAD}" x2="{m.PAD + 22}" y1="{y + 6:.1f}" y2="{y + 6:.1f}" stroke="{m.INK}" stroke-width="1.6"/>'),
           m.tx(m.PAD + 28, y + 10, "grew out of", 11, m.GREY),
           (f'<line x1="{m.PAD + 100}" x2="{m.PAD + 122}" y1="{y + 6:.1f}" y2="{y + 6:.1f}" stroke="{m.INK}" '
            f'stroke-width="1.6" stroke-dasharray="3 3"/>'),
           m.tx(m.PAD + 128, y + 10, "influence, debated", 11, m.GREY),
           f'<circle cx="{m.PAD + 252}" cy="{y + 6:.1f}" r="5" fill="{m.INK}"/>',
           m.tx(m.PAD + 261, y + 10, "origin", 11, m.GREY),
           f'<circle cx="{m.PAD + 312}" cy="{y + 6:.1f}" r="4" fill="#fff" stroke="{m.INK}" stroke-width="2"/>',
           m.tx(m.PAD + 321, y + 10, "later milestone", 11, m.GREY)]
    parts += key
    foot, y = m.footer(d, y + 24, w, 11)
    return m.svg_open(d, w, y, False) + "".join(parts) + foot + "</svg>"


def table_tree(d: dict) -> tuple[str, list[str]]:
    m = bt()
    head = ('<th scope="col">Stream</th><th scope="col">Grew out of</th>'
            '<th scope="col">Began</th><th scope="col">Later milestones</th>')
    rows = []
    for f in d["families"]:
        first, rest = f["nodes"][0], f["nodes"][1:]
        grew = "; ".join([f.get("parent_text") or "The Reformation"] + [i["text"] for i in f.get("influence") or []])
        later = "; ".join(f"{n['year']} {n['label']}" for n in rest)
        rows.append(f'<tr><th scope="row">{m.esc(f["name"])}</th><td data-label="Grew out of">{m.esc(grew)}</td>'
                    f'<td data-label="Began">{first["year"]} {m.esc(first["label"])}</td>'
                    f'<td data-label="Later milestones">{m.esc(later)}</td></tr>')
    return head, rows
