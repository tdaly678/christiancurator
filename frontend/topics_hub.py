"""The /topics/ hub: six reader-facing categories, one line per topic, search
synonyms and short names.

This is the single source for:
  * scripts/build_topics_index.py  -> docs/topics/index.html (daily workflow)
  * scripts/add_breadcrumbs.py     -> Home > Topics > Category on every topic page

The six hub categories are a reading aid for the hub page only. The older
four-way `category` field in topics_data.py is left alone (the series label
on each topic page, the classifier and the email still use it).

Every live topic must sit in exactly one hub category, with a line. Contested
questions sit under their subject (baptism under Doctrine, women in ministry
under Church and Practice); there is no Debates or Other bucket.
Tests: tests/test_topics_hub.py
"""
from __future__ import annotations

import re
from pathlib import Path

from frontend.topic_redirects import live_topic_dirs
from frontend.topics_data import TOPICS_BY_SLUG

REPO_ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = REPO_ROOT / "docs" / "topics"
SITE = "https://www.christiancurator.com"

# (anchor id, display name), in page order.
HUB_CATEGORIES: list[tuple[str, str]] = [
    ("scripture-and-interpretation", "Scripture and Interpretation"),
    ("doctrine", "Doctrine"),
    ("church-and-practice", "Church and Practice"),
    ("christian-living", "Christian Living"),
    ("culture-and-ethics", "Culture and Ethics"),
    ("faith-and-doubt", "Faith and Doubt"),
]
HUB_CATEGORY_NAMES = dict(HUB_CATEGORIES)

# slug -> (hub category id, neutral 6 to 10 word line on what the conversation covers)
HUB_TOPICS: dict[str, tuple[str, str]] = {
    # Scripture and Interpretation
    "biblical-inerrancy": ("scripture-and-interpretation", "Whether Scripture is without error, and what that claim means"),
    "biblical-literacy": ("scripture-and-interpretation", "Bible reading habits, survey findings, and ways to read well"),
    "covenant-theology": ("scripture-and-interpretation", "How the covenants connect the Old and New Testaments"),
    "israel-and-prophecy": ("scripture-and-interpretation", "Israel's place in prophecy, from dispensational to covenant readings"),
    "creation-evolution": ("scripture-and-interpretation", "Reading Genesis alongside science: young earth, old earth, evolution"),
    # Doctrine
    "atonement": ("doctrine", "What Christ's death accomplished and the models that explain it"),
    "justification-by-faith": ("doctrine", "How sinners are declared righteous, and the debates over Paul"),
    "baptism": ("doctrine", "Who should be baptized, how, and what baptism signifies"),
    "lords-supper": ("doctrine", "What happens at communion and how Christ is present"),
    "heaven-hell-eternity": ("doctrine", "Heaven, final judgment, and competing views of hell"),
    "suffering-and-providence": ("doctrine", "God's sovereignty and goodness in a world of pain"),
    "predestination-free-will": ("doctrine", "Election, human freedom, and the Calvinist and Arminian positions"),
    "holy-spirit-spiritual-gifts": ("doctrine", "The Spirit's work and whether miraculous gifts continue today"),
    "the-trinity": ("doctrine", "The doctrine of one God in three persons"),
    "eschatology": ("doctrine", "The millennium, the rapture, and how history ends"),
    "christology": ("doctrine", "Christ's divine and human natures and why they matter"),
    "gender-and-biblical-anthropology": ("doctrine", "Being human, male and female, and questions of embodiment"),
    "sanctification": ("doctrine", "How believers grow in holiness and whose work it is"),
    "prosperity-gospel": ("doctrine", "Health and wealth teaching weighed against Scripture on money"),
    # Church and Practice
    "church-accountability": ("church-and-practice", "How churches hold pastors and leaders accountable"),
    "church-discipline": ("church-and-practice", "Correcting members' sin, removal from membership, and restoration"),
    "church-governance": ("church-and-practice", "Elders, congregations, and bishops: who holds authority in a church"),
    "church-history": ("church-and-practice", "Reformers, councils, creeds, and what the church's past teaches"),
    "church-planting": ("church-and-practice", "Starting new churches: theology, strategy, and what it costs"),
    "complementarianism-egalitarianism": ("church-and-practice", "Women in ministry, male headship, and gender roles at home"),
    "local-church": ("church-and-practice", "Attendance, belonging, and why the gathered local church matters"),
    "membership": ("church-and-practice", "Formal church membership and what it asks of believers"),
    "missions-and-evangelism": ("church-and-practice", "The Great Commission, gospel witness, and the church's global mission"),
    "pastoral-ministry": ("church-and-practice", "The pastor's calling: shepherding, preaching, leading, and bivocational work"),
    "preaching": ("church-and-practice", "Expository, topical, and other approaches to the sermon"),
    "small-groups": ("church-and-practice", "Home groups and small groups as settings for discipleship"),
    "spiritual-abuse": ("church-and-practice", "Recognizing spiritual abuse in churches and how communities respond"),
    "worship-and-liturgy": ("church-and-practice", "How churches gather, sing, and order their services"),
    "evangelicalism": ("church-and-practice", "The evangelical movement's identity, divisions, and direction"),
    # Christian Living
    "prayer": ("christian-living", "How Christians pray and what prayer does"),
    "discipleship": ("christian-living", "How believers grow and help others follow Jesus"),
    "spiritual-disciplines": ("christian-living", "Scripture, solitude, silence, and other practices that shape faith"),
    "spiritual-warfare": ("christian-living", "Demonic activity, deliverance, and the armor of God"),
    "fasting": ("christian-living", "Biblical teaching on fasting and how Christians practice it"),
    "contemplative-prayer": ("christian-living", "Centering prayer, lectio divina, and contemplative practice among evangelicals"),
    "anxiety-and-fear": ("christian-living", "Worry and fear seen spiritually, psychologically, and practically"),
    "mental-health": ("christian-living", "Depression, mental illness, counseling, and the church's care"),
    "grief-and-lament": ("christian-living", "Grief, the biblical practice of lament, and honest prayer"),
    "forgiveness": ("christian-living", "What forgiveness requires and how it relates to reconciliation"),
    "christian-friendship": ("christian-living", "Friendship, loneliness, and community within the church"),
    "singleness": ("christian-living", "Singleness as a calling and its place in church life"),
    "marriage-and-family": ("christian-living", "Marriage, divorce, and family formation in Christian perspective"),
    "christian-parenting": ("christian-living", "Passing on the faith to children at home and church"),
    "pornography": ("christian-living", "Pornography, sexual purity, accountability, and paths to freedom"),
    "addiction-and-recovery": ("christian-living", "Addiction, faith-based recovery, and how churches walk alongside"),
    "death-and-dying": ("christian-living", "Dying well, end of life care, and Christian hope"),
    "vocation-and-work": ("christian-living", "Calling, ordinary work, and faith in the workplace"),
    "stewardship-and-generosity": ("christian-living", "Money, tithing, giving, and generosity in the Christian life"),
    # Culture and Ethics
    "politics-and-the-church": ("culture-and-ethics", "How Christians engage government, elections, and public life"),
    "christian-nationalism": ("culture-and-ethics", "Faith, national identity, and the debate over Christian nationalism"),
    "religious-liberty": ("culture-and-ethics", "Conscience rights, religious exemptions, and the reach of the state"),
    "racial-reconciliation": ("culture-and-ethics", "Race, repentance, and unity across ethnic lines in the church"),
    "biblical-justice": ("culture-and-ethics", "Poverty, oppression, and the debate over social justice"),
    "christian-ethics": ("culture-and-ethics", "Bioethics and other moral questions approached from Scripture"),
    "abortion": ("culture-and-ethics", "The sanctity of life and the pro-life movement after Dobbs"),
    "biblical-sexuality": ("culture-and-ethics", "Sexual ethics, same-sex attraction, and LGBTQ questions"),
    "christian-masculinity": ("culture-and-ethics", "Biblical manhood and men's place in church and society"),
    "christian-education": ("culture-and-ethics", "Christian schools, classical education, homeschooling, and public schools"),
    "creation-care": ("culture-and-ethics", "Environmental stewardship, climate, and caring for creation"),
    "artificial-intelligence": ("culture-and-ethics", "AI, the image of God, and how churches respond"),
    "technology": ("culture-and-ethics", "Phones, social media, and formation in a digital age"),
    "technology-and-discipleship": ("culture-and-ethics", "How digital tools are changing ministry and discipleship"),
    # Faith and Doubt
    "apologetics": ("faith-and-doubt", "Making the case for Christianity through reason and evidence"),
    "faith-deconstruction": ("faith-and-doubt", "Why believers question their faith and what rebuilding looks like"),
    "progressive-christianity": ("faith-and-doubt", "Progressive Christian beliefs and evangelical responses to them"),
}

# Extra words a reader might type, on top of each topic's classifier keywords
# in topics_data.py. Matching is by word prefix, so "deconstruct" also finds
# "deconstructing".
SYNONYMS: dict[str, list[str]] = {
    "eschatology": ["rapture", "millennium", "millennial", "premillennialism", "amillennialism",
                    "postmillennialism", "tribulation", "second coming", "end times", "revelation",
                    "antichrist", "last days"],
    "faith-deconstruction": ["deconversion", "deconvert", "deconstruct", "deconstruction",
                             "exvangelical", "doubt", "leaving the faith", "lost faith"],
    "lords-supper": ["communion", "eucharist", "sacrament", "lord's table", "mass"],
    "baptism": ["immersion", "infant baptism", "christening", "sprinkling", "dedication"],
    "complementarianism-egalitarianism": ["women pastors", "women preachers", "women in ministry",
                                          "gender roles", "headship", "women elders"],
    "predestination-free-will": ["calvinism", "arminianism", "election", "tulip", "reformed",
                                 "sovereignty", "molinism"],
    "holy-spirit-spiritual-gifts": ["tongues", "cessationism", "continuationism", "charismatic",
                                    "pentecostal", "prophecy", "healing", "miracles"],
    "heaven-hell-eternity": ["afterlife", "annihilation", "universalism", "judgment", "purgatory"],
    "creation-evolution": ["evolution", "genesis", "young earth", "old earth", "age of the earth",
                           "adam and eve", "science", "intelligent design"],
    "biblical-sexuality": ["homosexuality", "gay", "lgbt", "same-sex marriage", "sexual ethics"],
    "gender-and-biblical-anthropology": ["transgender", "gender identity", "image of god", "body",
                                         "male and female"],
    "abortion": ["pro-life", "pro life", "roe", "dobbs", "unborn", "ivf"],
    "artificial-intelligence": ["ai", "chatgpt", "chatbot", "machine learning", "robots"],
    "technology": ["smartphone", "phones", "social media", "screens", "internet"],
    "technology-and-discipleship": ["online church", "digital ministry", "apps"],
    "church-governance": ["elders", "deacons", "polity", "congregationalism", "presbyterian",
                          "episcopal", "bishops"],
    "worship-and-liturgy": ["music", "hymns", "songs", "liturgy", "service"],
    "atonement": ["cross", "penal substitution", "christus victor", "crucifixion"],
    "justification-by-faith": ["sola fide", "new perspective", "salvation", "grace"],
    "biblical-inerrancy": ["inspiration", "authority of scripture", "chicago statement", "errors"],
    "biblical-literacy": ["bible reading", "translations", "bible study", "how to read the bible"],
    "covenant-theology": ["dispensationalism", "old testament", "new covenant", "law and gospel"],
    "israel-and-prophecy": ["dispensationalism", "zionism", "jews", "jerusalem"],
    "mental-health": ["depression", "therapy", "counseling", "suicide", "psychology"],
    "anxiety-and-fear": ["worry", "panic", "stress"],
    "pornography": ["lust", "purity", "porn", "sexual sin"],
    "apologetics": ["evidence", "existence of god", "atheism", "reason", "proof", "skeptics"],
    "progressive-christianity": ["liberal theology", "mainline", "progressive"],
    "christian-nationalism": ["nationalism", "america", "patriotism"],
    "politics-and-the-church": ["voting", "elections", "government", "partisanship"],
    "religious-liberty": ["free speech", "first amendment", "freedom of religion", "persecution"],
    "death-and-dying": ["euthanasia", "assisted suicide", "hospice", "funeral"],
    "grief-and-lament": ["mourning", "loss", "sorrow", "psalms of lament"],
    "suffering-and-providence": ["pain", "evil", "problem of evil", "sovereignty of god"],
    "the-trinity": ["triune", "father son and holy spirit", "eternal subordination"],
    "christology": ["jesus", "incarnation", "deity of christ", "two natures"],
    "church-discipline": ["excommunication", "restoration", "accountability"],
    "church-accountability": ["pastor abuse", "misconduct", "scandal", "safeguarding"],
    "spiritual-abuse": ["abuse", "toxic church", "authoritarian", "cult"],
    "marriage-and-family": ["divorce", "husband", "wife", "family"],
    "christian-parenting": ["parents", "children", "kids", "family worship", "catechism"],
    "christian-education": ["school", "homeschool", "classical", "college", "seminary"],
    "missions-and-evangelism": ["evangelism", "great commission", "witness", "unreached", "missionary"],
    "vocation-and-work": ["job", "career", "workplace", "calling"],
    "stewardship-and-generosity": ["tithe", "tithing", "money", "giving", "wealth"],
    "prosperity-gospel": ["word of faith", "health and wealth", "name it and claim it"],
    "racial-reconciliation": ["race", "racism", "ethnicity", "multiethnic"],
    "biblical-justice": ["social justice", "poverty", "social gospel", "oppression"],
    "creation-care": ["environment", "climate", "ecology", "nature"],
    "christian-masculinity": ["manhood", "men", "masculinity", "fathers"],
    "singleness": ["single", "celibacy", "dating"],
    "local-church": ["church attendance", "going to church", "belonging"],
    "membership": ["church membership", "covenant membership"],
    "small-groups": ["home groups", "life groups", "community groups", "bible study"],
    "pastoral-ministry": ["pastors", "shepherding", "bivocational", "burnout"],
    "preaching": ["sermons", "expository", "homiletics"],
    "church-planting": ["new churches", "church plant", "planter"],
    "church-history": ["reformation", "creeds", "councils", "church fathers", "luther", "calvin"],
    "evangelicalism": ["evangelicals", "evangelical movement", "decline"],
    "spiritual-warfare": ["demons", "satan", "deliverance", "devil", "exorcism"],
    "spiritual-disciplines": ["disciplines", "solitude", "silence", "habits", "rule of life"],
    "contemplative-prayer": ["centering prayer", "lectio divina", "meditation", "mysticism"],
    "prayer": ["praying", "intercession", "lord's prayer"],
    "fasting": ["fast", "lent"],
    "forgiveness": ["reconciliation", "bitterness", "resentment"],
    "christian-friendship": ["friends", "loneliness", "community"],
    "addiction-and-recovery": ["alcohol", "drugs", "recovery", "sobriety", "twelve steps"],
    "discipleship": ["mentoring", "spiritual growth", "making disciples"],
    "sanctification": ["holiness", "growth", "sin", "spiritual growth"],
    "christian-ethics": ["bioethics", "morality", "ethics", "ivf", "euthanasia"],
}

# Short names people also use for these topics; the hub filter matches them.
SHORT_NAMES: dict[str, str] = {
    "eschatology": "Eschatology & End Times",
    "baptism": "Baptism",
    "faith-deconstruction": "Faith Deconstruction",
    "artificial-intelligence": "Artificial Intelligence",
    "complementarianism-egalitarianism": "Men, Women & the Church",
}

FOUR_WAY_RE = re.compile(r'class="[^"]*\bcc-debate-grid\b[^"]*\bfour-way\b')


def live_slugs(topics_dir: Path = TOPICS_DIR) -> list[str]:
    """Slugs with a live page (retired redirect stubs left out)."""
    return [d.name for d in live_topic_dirs(topics_dir)]


def topic_count(topics_dir: Path = TOPICS_DIR) -> int:
    """Number of live topic pages, computed from docs/topics/ at build time."""
    return len(live_slugs(topics_dir))


def hub_category(slug: str) -> tuple[str, str]:
    """(anchor id, display name) of the topic's hub category."""
    cat_id = HUB_TOPICS[slug][0]
    return cat_id, HUB_CATEGORY_NAMES[cat_id]


def topic_name(slug: str) -> str:
    t = TOPICS_BY_SLUG.get(slug)
    return t["name"] if t else slug.replace("-", " ").title()


def short_name(slug: str) -> str:
    return SHORT_NAMES.get(slug) or topic_name(slug)


def has_four_views(slug: str, topics_dir: Path = TOPICS_DIR) -> bool:
    """A full four-views hub: the page's debate grid carries four positions."""
    page = topics_dir / slug / "index.html"
    try:
        return bool(FOUR_WAY_RE.search(page.read_text(encoding="utf-8")))
    except OSError:
        return False


def search_terms(slug: str) -> str:
    """Lower-case words the filter box matches against (name, line, keywords, synonyms)."""
    parts = [topic_name(slug), short_name(slug), HUB_TOPICS[slug][1]]
    t = TOPICS_BY_SLUG.get(slug) or {}
    parts += t.get("keywords", [])
    parts += SYNONYMS.get(slug, [])
    words: list[str] = []
    seen = set()
    for p in parts:
        for w in re.findall(r"[a-z0-9]+", p.lower().replace("'", "")):
            if w not in seen:
                seen.add(w)
                words.append(w)
    return " ".join(words)


def hub_sections(topics_dir: Path = TOPICS_DIR) -> list[dict]:
    """Ordered categories with their live topics, each sorted by name."""
    live = live_slugs(topics_dir)
    missing = [s for s in live if s not in HUB_TOPICS]
    if missing:
        raise KeyError(f"topics with no hub category: {', '.join(missing)}")
    out = []
    for cat_id, cat_name in HUB_CATEGORIES:
        items = []
        for slug in live:
            if HUB_TOPICS[slug][0] != cat_id:
                continue
            items.append({
                "slug": slug,
                "name": topic_name(slug),
                "line": HUB_TOPICS[slug][1],
                "four_views": has_four_views(slug, topics_dir),
                "terms": search_terms(slug),
            })
        items.sort(key=lambda i: re.sub(r"^the ", "", i["name"].lower()))
        out.append({"id": cat_id, "name": cat_name, "topics": items})
    return out

