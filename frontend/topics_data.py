"""
topics_data.py — canonical data for all 36 debate topics.

Each entry:
  slug       — matches the URL path: /topics/{slug}/
  name       — display name
  category   — one of: "Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"
  hook       — one punchy sentence capturing the central debate question
  keywords   — list of strings used by the topic classifier to match articles
"""

TOPICS = [
    # ── Core Theology ─────────────────────────────────────────────────────────
    {
        "slug": "salvation-grace",
        "name": "Salvation & Grace",
        "category": "Core Theology",
        "hook": "Is salvation entirely God's work, or does human faith play a decisive role?",
        "keywords": [
            "salvation", "grace", "atonement", "justification", "saved", "soteriology",
            "regeneration", "redemption", "faith alone", "sola fide", "penal substitution",
            "substitutionary", "imputed", "reconciliation",
        ],
    },
    {
        "slug": "predestination",
        "name": "Predestination & Election",
        "category": "Core Theology",
        "hook": "Does God choose who is saved, or does he foresee who will choose him?",
        "keywords": [
            "predestination", "election", "calvinism", "calvinist", "arminian", "arminianism",
            "reformed theology", "tulip", "total depravity", "unconditional election",
            "limited atonement", "irresistible grace", "perseverance of the saints",
            "foreknowledge", "divine sovereignty", "free will", "chosen",
        ],
    },
    {
        "slug": "biblical-authority",
        "name": "Biblical Authority & Inerrancy",
        "category": "Core Theology",
        "hook": "Is the Bible without error in everything it affirms, or only in matters of faith?",
        "keywords": [
            "inerrancy", "infallibility", "biblical authority", "scripture", "sola scriptura",
            "biblical inspiration", "chicago statement", "hermeneutics", "biblical criticism",
            "higher criticism", "canon", "word of god", "bible trustworthy",
        ],
    },
    {
        "slug": "baptism",
        "name": "Baptism",
        "category": "Core Theology",
        "hook": "Should we baptize infants, or only those who profess faith?",
        "keywords": [
            "baptism", "infant baptism", "paedobaptism", "credobaptism", "believer's baptism",
            "baptismal regeneration", "mode of baptism", "immersion", "sprinkling",
            "baptize", "christening",
        ],
    },
    {
        "slug": "lords-supper",
        "name": "The Lord's Supper",
        "category": "Core Theology",
        "hook": "Is Christ truly present in the bread and cup, and if so, how?",
        "keywords": [
            "lord's supper", "communion", "eucharist", "real presence", "transubstantiation",
            "consubstantiation", "memorial", "remembrance", "breaking bread", "table of the lord",
            "sacrament", "ordinance",
        ],
    },
    {
        "slug": "spiritual-gifts",
        "name": "Spiritual Gifts & Charismatic Practice",
        "category": "Core Theology",
        "hook": "Have gifts like tongues and prophecy ceased, or are they for the church today?",
        "keywords": [
            "spiritual gifts", "tongues", "glossolalia", "prophecy", "cessationism",
            "continuationism", "charismatic", "pentecostal", "healing", "miraculous gifts",
            "sign gifts", "holy spirit gifts", "speaking in tongues", "third wave",
        ],
    },
    {
        "slug": "hell-judgment",
        "name": "Hell & Divine Judgment",
        "category": "Core Theology",
        "hook": "Is hell a place of eternal conscious torment, or does God eventually destroy the lost?",
        "keywords": [
            "hell", "eternal punishment", "annihilationism", "conditional immortality",
            "universal reconciliation", "universalism", "gehenna", "lake of fire",
            "eternal torment", "judgment", "wrath of god", "final judgment",
        ],
    },
    {
        "slug": "end-times",
        "name": "End Times & Eschatology",
        "category": "Core Theology",
        "hook": "Will Christ return before or after the millennium — and will believers be raptured?",
        "keywords": [
            "eschatology", "end times", "rapture", "millennium", "millennial",
            "premillennialism", "postmillennialism", "amillennialism", "tribulation",
            "second coming", "return of christ", "revelation", "apocalypse", "dispensationalism",
            "preterism", "new heaven", "new earth",
        ],
    },
    {
        "slug": "creation-origins",
        "name": "Creation & Origins",
        "category": "Core Theology",
        "hook": "Did God create the universe in six literal days, or is the Genesis account compatible with evolution?",
        "keywords": [
            "creation", "creationism", "evolution", "intelligent design", "genesis",
            "young earth", "old earth", "day-age", "framework hypothesis", "theistic evolution",
            "origins", "darwinism", "adam and eve", "historical adam", "biolologos",
        ],
    },
    {
        "slug": "suffering-providence",
        "name": "Suffering & Providence",
        "category": "Core Theology",
        "hook": "Does God ordain suffering for our good, or does he merely permit it?",
        "keywords": [
            "suffering", "providence", "theodicy", "problem of evil", "divine sovereignty",
            "why does god allow", "pain", "grief", "lament", "god's plan", "ordained suffering",
            "open theism", "meticulous providence",
        ],
    },

    # ── Church Life ────────────────────────────────────────────────────────────
    {
        "slug": "gender-roles",
        "name": "Gender Roles in the Church",
        "category": "Church Life",
        "hook": "Should women serve as pastors and elders, or are those roles reserved for men?",
        "keywords": [
            "gender roles", "women in ministry", "women pastor", "complementarian",
            "egalitarian", "female pastor", "ordination of women", "women preaching",
            "women elders", "1 timothy 2", "head of household", "male headship",
            "women in church", "biblical womanhood", "biblical manhood",
        ],
    },
    {
        "slug": "church-discipline",
        "name": "Church Discipline",
        "category": "Church Life",
        "hook": "When and how should a church remove a member, and what does restoration look like?",
        "keywords": [
            "church discipline", "excommunication", "disfellowship", "Matthew 18",
            "church membership", "accountability", "rebuke", "restore",
            "wayward member", "sin in the church", "corrective discipline",
        ],
    },
    {
        "slug": "worship-and-liturgy",
        "name": "Worship & Liturgy",
        "category": "Church Life",
        "hook": "Should evangelical worship be free-form and contemporary, or anchored in historic liturgical forms?",
        "keywords": [
            "worship", "liturgy", "liturgical", "contemporary worship", "hymns",
            "regulative principle", "normative principle", "corporate worship",
            "worship music", "church music", "praise", "song", "contemporary christian music",
            "CCM", "worship wars",
        ],
    },
    {
        "slug": "local-church",
        "name": "The Local Church",
        "category": "Church Life",
        "hook": "Is belonging to a local church optional for Christians, or essential to spiritual health?",
        "keywords": [
            "local church", "church membership", "ecclesiology", "church attendance",
            "church planting", "multisite", "megachurch", "dechurching", "leaving church",
            "church body", "fellowship", "gathered church", "unchurched",
        ],
    },
    {
        "slug": "missions-evangelism",
        "name": "Missions & Evangelism",
        "category": "Church Life",
        "hook": "What is the church's primary mission — social transformation or gospel proclamation?",
        "keywords": [
            "missions", "evangelism", "missionaries", "great commission", "gospel proclamation",
            "social gospel", "holistic mission", "unreached peoples", "church planting",
            "cross-cultural", "missiology", "contextualization", "evangelism method",
        ],
    },
    {
        "slug": "church-history",
        "name": "Church History",
        "category": "Church Life",
        "hook": "How should evangelical churches relate to the wisdom and mistakes of their historical ancestors?",
        "keywords": [
            "church history", "reformation", "reformers", "puritans", "luther", "calvin",
            "augustine", "early church", "church fathers", "protestant", "medieval church",
            "historical theology", "councils", "creeds", "confessions",
        ],
    },

    # ── Spiritual Formation ────────────────────────────────────────────────────
    {
        "slug": "prayer",
        "name": "Prayer",
        "category": "Spiritual Formation",
        "hook": "Does prayer change what God does, or does it change us to align with what he has ordained?",
        "keywords": [
            "prayer", "intercession", "pray", "petition", "contemplative prayer",
            "prayer life", "praying", "unanswered prayer", "persistence in prayer",
            "prayer and sovereignty",
        ],
    },
    {
        "slug": "discipleship",
        "name": "Discipleship & Sanctification",
        "category": "Spiritual Formation",
        "hook": "Is spiritual growth primarily God's work in us, or does it require rigorous human effort?",
        "keywords": [
            "discipleship", "sanctification", "spiritual growth", "spiritual disciplines",
            "holiness", "Christian formation", "mortification", "means of grace",
            "spiritual maturity", "growing in faith", "transformation",
        ],
    },
    {
        "slug": "bible-study",
        "name": "Bible Study & Hermeneutics",
        "category": "Spiritual Formation",
        "hook": "Should we read the Bible primarily through a narrative lens, or a doctrinal one?",
        "keywords": [
            "bible study", "hermeneutics", "exegesis", "inductive bible study",
            "devotional reading", "lectio divina", "expository preaching",
            "narrative theology", "biblical theology", "systematic theology",
            "how to read the bible", "scripture reading plan", "bible interpretation",
        ],
    },
    {
        "slug": "spiritual-warfare",
        "name": "Spiritual Warfare",
        "category": "Spiritual Formation",
        "hook": "How active is demonic activity in the everyday lives of Christians?",
        "keywords": [
            "spiritual warfare", "spiritual battle", "satan", "demonic", "demons",
            "devil", "spiritual forces", "armor of god", "deliverance",
            "principalities", "powers", "evil one", "spiritual attack",
        ],
    },
    {
        "slug": "fasting",
        "name": "Fasting",
        "category": "Spiritual Formation",
        "hook": "Is fasting a neglected discipline the church must recover, or a practice easily misunderstood?",
        "keywords": [
            "fasting", "fast", "abstinence", "spiritual fast", "biblical fasting",
            "intermittent fasting", "lent", "abstain",
        ],
    },
    {
        "slug": "anxiety-and-fear",
        "name": "Anxiety & Fear",
        "category": "Spiritual Formation",
        "hook": "Is anxiety primarily a spiritual failure, a medical condition, or both — and how should Christians respond?",
        "keywords": [
            "anxiety", "fear", "worry", "mental health", "depression", "anxious",
            "panic", "cast your anxiety", "do not be afraid", "christian counseling",
            "psychology", "therapy", "christian mental health",
        ],
    },

    # ── Culture & Society ──────────────────────────────────────────────────────
    {
        "slug": "politics-christianity",
        "name": "Politics & Christianity",
        "category": "Culture & Society",
        "hook": "Should evangelical Christians seek political power, or hold it at arm's length?",
        "keywords": [
            "christian nationalism", "politics", "political", "government", "election",
            "voting", "conservative politics", "liberal politics", "church and state",
            "two kingdoms", "common good", "public square", "political theology",
            "civic engagement", "democracy", "republican", "democrat",
        ],
    },
    {
        "slug": "race-justice",
        "name": "Race & Justice",
        "category": "Culture & Society",
        "hook": "Is racial reconciliation best pursued through structural change, individual repentance, or gospel proclamation?",
        "keywords": [
            "race", "racial reconciliation", "racism", "diversity", "justice",
            "social justice", "critical race theory", "CRT", "reparations",
            "racial justice", "multiethnic church", "ethnic diversity", "discrimination",
            "systemic racism", "equity",
        ],
    },
    {
        "slug": "technology-ai",
        "name": "Technology & AI",
        "category": "Culture & Society",
        "hook": "How should Christians think about artificial intelligence and digital life?",
        "keywords": [
            "technology", "artificial intelligence", "AI", "social media", "digital",
            "internet", "smartphone", "tech", "algorithm", "machine learning",
            "chatbot", "ChatGPT", "automation", "digital discipleship",
        ],
    },
    {
        "slug": "marriage-family",
        "name": "Marriage & Family",
        "category": "Culture & Society",
        "hook": "What does a distinctively Christian vision of marriage and family look like in a post-Christian culture?",
        "keywords": [
            "marriage", "family", "parenting", "children", "husband", "wife",
            "divorce", "remarriage", "singleness", "celibacy", "same-sex marriage",
            "cohabitation", "fertility", "adoption", "family formation",
        ],
    },
    {
        "slug": "christian-ethics",
        "name": "Christian Ethics",
        "category": "Culture & Society",
        "hook": "How do Christians navigate complex moral questions that the Bible does not directly address?",
        "keywords": [
            "ethics", "bioethics", "moral", "abortion", "euthanasia", "end of life",
            "IVF", "surrogacy", "sexuality", "LGBTQ", "gender identity", "transgender",
            "natural law", "moral theology", "christian ethics",
        ],
    },
    {
        "slug": "money-generosity",
        "name": "Money & Generosity",
        "category": "Culture & Society",
        "hook": "Is wealth a sign of blessing, a spiritual danger, or simply a tool — and what does the Bible say about how much to give?",
        "keywords": [
            "money", "generosity", "stewardship", "giving", "tithing", "tithe",
            "wealth", "prosperity gospel", "poverty", "financial", "treasure",
            "mammon", "materialism", "contentment",
        ],
    },
    {
        "slug": "vocation-work",
        "name": "Vocation & Work",
        "category": "Culture & Society",
        "hook": "Is all honest work sacred, or does ministry and church work hold a higher calling?",
        "keywords": [
            "vocation", "work", "calling", "career", "workplace", "labor",
            "ordinary work", "sacred and secular", "faith and work",
            "monday morning", "marketplace", "profession",
        ],
    },
    {
        "slug": "evangelicalism",
        "name": "The Future of Evangelicalism",
        "category": "Culture & Society",
        "hook": "Is the evangelical movement fracturing, and if so, what should come next?",
        "keywords": [
            "evangelicalism", "evangelical", "post-evangelical", "evangelical identity",
            "evangelical decline", "evangelical movement", "SBC", "southern baptist",
            "NAE", "evangelical coalition", "evangelical crisis",
        ],
    },
]

# Index by slug for fast lookups
TOPICS_BY_SLUG = {t["slug"]: t for t in TOPICS}

# Group by category
CATEGORIES = ["Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"]
TOPICS_BY_CATEGORY = {cat: [t for t in TOPICS if t["category"] == cat] for cat in CATEGORIES}
