"""
topics_data.py — canonical data for all 36 debate topics.

Slugs match the actual folder names under docs/topics/.
Each entry:
  slug       — matches /topics/{slug}/ URL path exactly
  name       — display name
  category   — one of: "Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"
  hook       — one punchy sentence capturing the central debate question
  keywords   — list of strings used by the topic classifier to match articles
"""

TOPICS = [
    # ── Core Theology ─────────────────────────────────────────────────────────
    {
        "slug": "atonement",
        "name": "The Atonement",
        "category": "Core Theology",
        "hook": "What exactly did Jesus' death accomplish — and how does it actually save us?",
        "keywords": [
            "atonement", "penal substitution", "substitutionary atonement", "cross of christ",
            "propitiation", "expiation", "reconciliation", "blood of christ",
            "christus victor", "moral influence", "ransom theory", "why jesus died",
        ],
    },
    {
        "slug": "justification-by-faith",
        "name": "Justification by Faith",
        "category": "Core Theology",
        "hook": "Is justification a declaration of righteousness, a process of becoming righteous, or something else?",
        "keywords": [
            "justification", "sola fide", "faith alone", "imputed righteousness",
            "new perspective on paul", "wright", "forensic justification",
            "works of the law", "righteousness of god", "saved by faith",
        ],
    },
    {
        "slug": "biblical-inerrancy",
        "name": "Biblical Inerrancy",
        "category": "Core Theology",
        "hook": "Is the Bible without error in everything it affirms, or only in matters of faith and practice?",
        "keywords": [
            "inerrancy", "infallibility", "biblical inerrancy", "scripture",
            "sola scriptura", "chicago statement", "biblical authority",
            "biblical inspiration", "word of god", "errancy",
            "hermeneutics", "biblical criticism", "canon",
        ],
    },
    {
        "slug": "baptism",
        "name": "Baptism",
        "category": "Core Theology",
        "hook": "Should we baptize infants or only those who profess faith — and does it matter?",
        "keywords": [
            "baptism", "infant baptism", "paedobaptism", "credobaptism",
            "believer's baptism", "baptismal regeneration", "mode of baptism",
            "immersion", "sprinkling", "baptize", "christening",
        ],
    },
    {
        "slug": "lords-supper",
        "name": "The Lord's Supper",
        "category": "Core Theology",
        "hook": "Is Christ truly present in the bread and cup, and if so, how?",
        "keywords": [
            "lord's supper", "communion", "eucharist", "real presence",
            "transubstantiation", "consubstantiation", "memorial",
            "breaking bread", "table of the lord", "sacrament", "ordinance",
        ],
    },
    {
        "slug": "heaven-hell-eternity",
        "name": "Heaven, Hell & Eternity",
        "category": "Core Theology",
        "hook": "Is hell a place of eternal conscious torment, or does God eventually destroy the lost?",
        "keywords": [
            "hell", "heaven", "eternal punishment", "annihilationism",
            "conditional immortality", "universalism", "purgatory",
            "gehenna", "lake of fire", "eternal life", "new creation",
            "resurrection", "final judgment", "eternity",
        ],
    },
    {
        "slug": "creation-evolution",
        "name": "Creation & Evolution",
        "category": "Core Theology",
        "hook": "Did God create the universe in six literal days, or is Genesis compatible with modern science?",
        "keywords": [
            "creation", "evolution", "creationism", "intelligent design", "genesis",
            "young earth", "old earth", "day-age", "theistic evolution",
            "origins", "darwinism", "adam and eve", "historical adam",
            "biologos", "framework hypothesis",
        ],
    },
    {
        "slug": "suffering-and-providence",
        "name": "Suffering & Providence",
        "category": "Core Theology",
        "hook": "Does God ordain suffering for our good, or does he merely permit it?",
        "keywords": [
            "suffering", "providence", "theodicy", "problem of evil",
            "why does god allow", "pain", "grief", "lament",
            "god's plan", "ordained suffering", "open theism",
            "meticulous providence", "sovereignty of god",
        ],
    },
    {
        "slug": "gender-and-biblical-anthropology",
        "name": "Gender & Biblical Anthropology",
        "category": "Core Theology",
        "hook": "What does Scripture teach about what it means to be male and female?",
        "keywords": [
            "gender", "male and female", "biblical anthropology", "human sexuality",
            "transgender", "gender identity", "sex and gender", "image of god",
            "embodiment", "what is a woman", "biological sex", "imago dei",
        ],
    },
    {
        "slug": "apologetics",
        "name": "Apologetics",
        "category": "Core Theology",
        "hook": "Should Christians defend the faith through reason and evidence, or simply proclaim the gospel?",
        "keywords": [
            "apologetics", "defense of the faith", "presuppositional",
            "classical apologetics", "evidentialism", "natural theology",
            "reason and faith", "evidence for christianity", "atheism",
            "skepticism", "doubt", "intellectual defense",
        ],
    },

    # ── Church Life ────────────────────────────────────────────────────────────
    {
        "slug": "complementarianism-egalitarianism",
        "name": "Complementarianism & Egalitarianism",
        "category": "Church Life",
        "hook": "Should women serve as pastors and elders, or are those roles reserved for men?",
        "keywords": [
            "complementarian", "egalitarian", "women in ministry", "women pastor",
            "female pastor", "ordination of women", "women preaching",
            "women elders", "male headship", "1 timothy 2",
            "women in church", "biblical womanhood", "biblical manhood",
        ],
    },
    {
        "slug": "church-discipline",
        "name": "Church Discipline",
        "category": "Church Life",
        "hook": "When and how should a church remove a member — and what does restoration look like?",
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
            "worship music", "church music", "worship wars",
            "contemporary christian music", "CCM",
        ],
    },
    {
        "slug": "local-church",
        "name": "The Local Church",
        "category": "Church Life",
        "hook": "Is belonging to a local church optional for Christians, or essential to spiritual health?",
        "keywords": [
            "local church", "church attendance", "ecclesiology",
            "church planting", "multisite", "megachurch", "dechurching",
            "leaving church", "church body", "fellowship", "gathered church",
            "unchurched", "why church matters",
        ],
    },
    {
        "slug": "missions-and-evangelism",
        "name": "Missions & Evangelism",
        "category": "Church Life",
        "hook": "What is the church's primary mission — gospel proclamation, or social transformation?",
        "keywords": [
            "missions", "evangelism", "missionaries", "great commission",
            "gospel proclamation", "social gospel", "holistic mission",
            "unreached peoples", "cross-cultural", "missiology",
            "contextualization", "evangelism method",
        ],
    },
    {
        "slug": "church-history",
        "name": "Church History",
        "category": "Church Life",
        "hook": "How should evangelical churches relate to the wisdom — and failures — of their historical ancestors?",
        "keywords": [
            "church history", "reformation", "reformers", "puritans",
            "luther", "calvin", "augustine", "early church", "church fathers",
            "protestant", "medieval church", "historical theology",
            "councils", "creeds", "confessions",
        ],
    },
    {
        "slug": "membership",
        "name": "Church Membership",
        "category": "Church Life",
        "hook": "Is formal church membership a biblical requirement or an optional formality?",
        "keywords": [
            "church membership", "formal membership", "covenant membership",
            "joining a church", "membership class", "church commitment",
            "membership vows", "member covenant",
        ],
    },
    {
        "slug": "church-planting",
        "name": "Church Planting",
        "category": "Church Life",
        "hook": "Is planting new churches the best strategy for reaching new communities?",
        "keywords": [
            "church planting", "church plant", "church planter",
            "new church", "starting a church", "Acts 29",
            "church multiplication", "replanting", "revitalization",
        ],
    },
    {
        "slug": "preaching",
        "name": "Preaching",
        "category": "Church Life",
        "hook": "What makes preaching faithful — and is expository preaching the only legitimate approach?",
        "keywords": [
            "preaching", "expository preaching", "sermon", "homiletics",
            "topical preaching", "expository", "preach", "pulpit",
            "faithful preaching", "biblical preaching", "narrative preaching",
        ],
    },

    # ── Spiritual Formation ────────────────────────────────────────────────────
    {
        "slug": "prayer",
        "name": "Prayer",
        "category": "Spiritual Formation",
        "hook": "Does prayer change what God does, or does it primarily change us?",
        "keywords": [
            "prayer", "intercession", "pray", "petition", "contemplative prayer",
            "prayer life", "praying", "unanswered prayer",
            "persistence in prayer", "prayer and sovereignty",
        ],
    },
    {
        "slug": "discipleship",
        "name": "Discipleship",
        "category": "Spiritual Formation",
        "hook": "What does it actually mean to make disciples — and are most churches doing it?",
        "keywords": [
            "discipleship", "disciple-making", "spiritual growth",
            "Christian formation", "mentoring", "one-on-one discipleship",
            "discipleship program", "making disciples",
        ],
    },
    {
        "slug": "sanctification",
        "name": "Sanctification",
        "category": "Spiritual Formation",
        "hook": "Is growing in holiness primarily God's work in us, or does it require rigorous human effort?",
        "keywords": [
            "sanctification", "holiness", "mortification", "means of grace",
            "growing in holiness", "put to death", "spiritual maturity",
            "transformation", "progressive sanctification", "definitive sanctification",
        ],
    },
    {
        "slug": "spiritual-disciplines",
        "name": "Spiritual Disciplines",
        "category": "Spiritual Formation",
        "hook": "Are the spiritual disciplines a path to growth — or a path to legalism?",
        "keywords": [
            "spiritual disciplines", "disciplines", "solitude", "silence",
            "scripture memorization", "journaling", "sabbath keeping",
            "richard foster", "dallas willard", "means of grace",
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
            "fasting", "fast", "biblical fasting", "spiritual fast",
            "abstinence", "lent", "abstain from food",
        ],
    },
    {
        "slug": "anxiety-and-fear",
        "name": "Anxiety & Fear",
        "category": "Spiritual Formation",
        "hook": "Is anxiety primarily a spiritual failure, a medical condition, or both?",
        "keywords": [
            "anxiety", "fear", "worry", "anxious", "panic",
            "cast your anxiety", "do not be afraid", "mental health",
            "christian counseling", "psychology", "therapy",
        ],
    },
    {
        "slug": "mental-health",
        "name": "Mental Health & Faith",
        "category": "Spiritual Formation",
        "hook": "How should Christians think about depression and mental illness — as primarily spiritual, medical, or both?",
        "keywords": [
            "mental health", "depression", "mental illness", "christian mental health",
            "psychiatry", "antidepressants", "counseling", "suicide",
            "bipolar", "trauma", "emotional health", "psychology and faith",
        ],
    },

    # ── Culture & Society ──────────────────────────────────────────────────────
    {
        "slug": "politics-and-the-church",
        "name": "Politics & the Church",
        "category": "Culture & Society",
        "hook": "Should evangelical Christians seek political power, or hold it at arm's length?",
        "keywords": [
            "christian nationalism", "politics", "political", "government",
            "election", "voting", "church and state", "two kingdoms",
            "common good", "public square", "political theology",
            "civic engagement", "democracy",
        ],
    },
    {
        "slug": "racial-reconciliation",
        "name": "Racial Reconciliation",
        "category": "Culture & Society",
        "hook": "Is racial reconciliation best pursued through structural change, individual repentance, or gospel proclamation?",
        "keywords": [
            "racial reconciliation", "race", "racism", "diversity",
            "justice", "social justice", "critical race theory", "CRT",
            "reparations", "racial justice", "multiethnic church",
            "ethnic diversity", "systemic racism",
        ],
    },
    {
        "slug": "technology",
        "name": "Technology & the Christian Life",
        "category": "Culture & Society",
        "hook": "How should Christians navigate a world increasingly shaped by technology and social media?",
        "keywords": [
            "technology", "social media", "smartphone", "digital",
            "internet", "tech", "algorithm", "screen time",
            "digital age", "online life", "phone", "media",
        ],
    },
    {
        "slug": "technology-and-discipleship",
        "name": "Technology & Discipleship",
        "category": "Culture & Society",
        "hook": "How do smartphones and social media form us spiritually — and what should Christians do about it?",
        "keywords": [
            "artificial intelligence", "AI", "machine learning", "chatbot",
            "ChatGPT", "automation", "digital discipleship",
            "technology and discipleship", "tech and faith",
        ],
    },
    {
        "slug": "marriage-and-family",
        "name": "Marriage & Family",
        "category": "Culture & Society",
        "hook": "What does a distinctively Christian vision of marriage and family look like in a post-Christian culture?",
        "keywords": [
            "marriage", "family", "husband", "wife",
            "divorce", "remarriage", "singleness", "celibacy",
            "same-sex marriage", "cohabitation", "family formation",
            "definition of marriage",
        ],
    },
    {
        "slug": "christian-parenting",
        "name": "Christian Parenting",
        "category": "Culture & Society",
        "hook": "How do Christian parents faithfully pass on faith to the next generation?",
        "keywords": [
            "parenting", "christian parenting", "raising children",
            "children and faith", "family worship", "catechism",
            "passing on faith", "prodigal children", "parenting teenagers",
        ],
    },
    {
        "slug": "christian-ethics",
        "name": "Christian Ethics",
        "category": "Culture & Society",
        "hook": "How do Christians navigate complex moral questions the Bible does not directly address?",
        "keywords": [
            "ethics", "bioethics", "moral", "abortion", "euthanasia",
            "end of life", "IVF", "surrogacy", "sexuality",
            "LGBTQ", "natural law", "moral theology", "christian ethics",
        ],
    },
    {
        "slug": "vocation-and-work",
        "name": "Vocation & Work",
        "category": "Culture & Society",
        "hook": "Is all honest work sacred, or does ministry hold a higher calling?",
        "keywords": [
            "vocation", "work", "calling", "career", "workplace",
            "labor", "ordinary work", "sacred and secular",
            "faith and work", "monday morning", "marketplace", "profession",
        ],
    },
    {
        "slug": "evangelicalism",
        "name": "The Future of Evangelicalism",
        "category": "Culture & Society",
        "hook": "Is the evangelical movement fracturing — and if so, what should come next?",
        "keywords": [
            "evangelicalism", "evangelical", "post-evangelical",
            "evangelical identity", "evangelical decline", "evangelical movement",
            "SBC", "southern baptist", "NAE", "evangelical crisis",
        ],
    },
]

# Index by slug for fast lookups
TOPICS_BY_SLUG = {t["slug"]: t for t in TOPICS}

# Group by category
CATEGORIES = ["Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"]
TOPICS_BY_CATEGORY = {cat: [t for t in TOPICS if t["category"] == cat] for cat in CATEGORIES}
