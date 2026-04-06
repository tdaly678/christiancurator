"""
topics_data.py — canonical data for all 36 debate topics.

Slugs match the actual folder names under docs/topics/.
Each entry:
  slug       — matches /topics/{slug}/ URL path exactly
  name       — display name
  category   — one of: "Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"
  hook       — one punchy sentence capturing the central debate question
               (used on individual topic pages for SEO/AEO)
  summary    — short plain-language description of what the topic covers
               (used on homepage cards, digest cards, and emails — not tied to today's articles)
  keywords   — list of strings used by the topic classifier to match articles
"""

TOPICS = [
    # ── Core Theology ─────────────────────────────────────────────────────────
    {
        "slug": "atonement",
        "name": "The Atonement",
        "category": "Core Theology",
        "hook": "What exactly did Jesus' death accomplish — and how does it actually save us?",
        "summary": "Evangelical perspectives on the cross, penal substitution, and what Christ's death accomplished for sinners.",
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
        "summary": "Evangelical debate over faith alone, imputed righteousness, and what Paul really meant by justification.",
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
        "summary": "How evangelicals understand Scripture's authority, reliability, and relationship to science, history, and theology.",
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
        "summary": "The evangelical debate over infant vs. believer's baptism, mode, and what Scripture teaches about the ordinance.",
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
        "summary": "Evangelical perspectives on what happens at communion — Christ's presence, meaning, and how churches practice it.",
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
        "summary": "Evangelical views on the afterlife, eternal punishment, annihilationism, and the hope of new creation.",
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
        "summary": "How evangelicals navigate Genesis, the origins debate, and young-earth vs. old-earth creationism.",
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
        "summary": "How Christians understand God's sovereignty in the face of pain, grief, and seemingly unanswered prayer.",
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
        "summary": "Evangelical perspectives on male and female identity, embodiment, transgender questions, and the image of God.",
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
        "summary": "How Christians make the case for the faith — through reason, evidence, presupposition, and engagement with doubt.",
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
        "summary": "The ongoing evangelical debate over women in ministry, male headship, and what Scripture teaches about church leadership.",
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
        "summary": "How churches handle member sin, accountability, corrective removal, and the path to restoration.",
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
        "summary": "Evangelical conversation about how churches should gather, sing, and meet with God — contemporary or liturgical.",
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
        "summary": "Why the local church matters — and evangelical conversations about attendance, belonging, and dechurching.",
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
        "summary": "How evangelicals understand the Great Commission, gospel proclamation, and the church's mission in the world.",
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
        "summary": "What the church's past — its reformers, councils, creeds, and failures — means for Christians today.",
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
        "summary": "Evangelical perspectives on formal church membership and what covenant commitment to a local body requires.",
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
        "summary": "The theology and practice of starting new churches as a strategy for reaching unchurched communities.",
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
        "summary": "What makes a sermon faithful — evangelical debate over expository preaching, topical approaches, and pulpit method.",
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
        "summary": "Evangelical perspectives on how Christians pray, whether prayer changes things, and building a consistent prayer life.",
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
        "summary": "How Christians grow in maturity — one-on-one mentoring, church programs, and the meaning of making disciples.",
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
        "summary": "The evangelical debate over how Christians grow in holiness — God's work, human effort, and means of grace.",
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
        "summary": "How practices like solitude, silence, Scripture reading, and fasting shape the Christian life.",
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
        "summary": "Evangelical perspectives on demonic activity, the armor of God, deliverance, and living in spiritual conflict.",
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
        "summary": "What the Bible teaches about fasting — and why many evangelicals consider it a neglected spiritual discipline.",
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
        "summary": "How Christians understand worry, fear, and anxiety — spiritually, psychologically, and practically.",
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
        "summary": "Evangelical perspectives on depression, mental illness, counseling, and integrating faith with psychological care.",
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
        "summary": "How evangelical Christians engage with politics, government, civic life, and the public square.",
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
        "summary": "Evangelical conversation around race, repentance, diversity, and what the church owes to justice.",
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
        "summary": "How Christians think about social media, smartphones, digital life, and the spiritual formation impact of technology.",
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
        "summary": "How AI and digital tools are reshaping discipleship, ministry, and evangelical thinking about what it means to be human.",
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
        "summary": "A Christian vision of marriage, family, divorce, singleness, and family formation in a post-Christian culture.",
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
        "summary": "How Christian parents pass faith to the next generation — from family worship and catechism to raising teenagers.",
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
        "summary": "How Christians navigate bioethics, sexuality, LGBTQ+ questions, and moral issues Scripture doesn't directly address.",
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
        "summary": "Evangelical perspectives on calling, vocation, and how faith shapes ordinary work and the marketplace.",
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
        "summary": "The state of the evangelical movement — its divisions, decline, identity, and what comes next.",
        "keywords": [
            "evangelicalism", "evangelical", "post-evangelical",
            "evangelical identity", "evangelical decline", "evangelical movement",
            "SBC", "southern baptist", "NAE", "evangelical crisis",
        ],
    },
    {
        "slug": "predestination-free-will",
        "name": "Predestination & Free Will",
        "category": "Core Theology",
        "hook": "Is salvation ultimately determined by God's sovereign choice or the human will's free response — and what are the stakes of getting this question right?",
        "summary": "The Calvinist-Arminian debate over divine election, human freedom, and the nature of saving grace.",
        "keywords": [
            "predestination", "election", "calvinism", "arminianism", "free will",
            "sovereignty", "TULIP", "Reformed", "Molinism", "unconditional election",
            "middle knowledge", "libertarian freedom", "divine foreknowledge",
        ],
    },
    {
        "slug": "holy-spirit-spiritual-gifts",
        "name": "The Holy Spirit & Spiritual Gifts",
        "category": "Core Theology",
        "hook": "Do miraculous spiritual gifts like tongues and prophecy continue today, or did they cease with the apostolic age — and how does the answer shape Christian life and worship?",
        "summary": "The debate between cessationists and continuationists over spiritual gifts, tongues, and the Spirit's work today.",
        "keywords": [
            "holy spirit", "spiritual gifts", "tongues", "prophecy", "gifts of the spirit",
            "cessationism", "continuationism", "baptism in the holy spirit",
            "charismatic", "pentecostal", "apostolic gifts", "healing",
        ],
    },
    {
        "slug": "the-trinity",
        "name": "The Trinity",
        "category": "Core Theology",
        "hook": "What does it mean that God is one being in three persons — and why does Trinitarian theology matter for prayer, salvation, and everyday Christian life?",
        "summary": "Evangelical theology of the triune God — Father, Son, and Spirit — and why Trinitarian doctrine matters in practice.",
        "keywords": [
            "trinity", "trinitarian", "three in one", "father son holy spirit",
            "subordinationism", "social trinitarianism", "substance", "persons",
            "perichoresis", "divine nature", "godhead", "triune god",
        ],
    },
    {
        "slug": "christian-nationalism",
        "name": "Christian Nationalism",
        "category": "Culture & Society",
        "hook": "What is Christian nationalism, why is it attracting evangelical support, and how does it differ from faithful Christian political engagement?",
        "summary": "Evangelical debate over Christian nationalism — its appeal, its dangers, and what faithful political engagement looks like.",
        "keywords": [
            "christian nationalism", "nationalism", "christendom", "christian civilization",
            "christian right", "political power", "kingdom of god", "two kingdoms",
            "cultural christianity", "post-christian", "religious liberty",
        ],
    },
    {
        "slug": "faith-deconstruction",
        "name": "Deconstruction & Faith",
        "category": "Spiritual Formation",
        "hook": "When Christians begin questioning their beliefs, what does faithful deconstruction look like — and how should churches and pastors respond?",
        "summary": "Why Christians are deconstructing, what churches can do, and what healthy faith rebuilding looks like.",
        "keywords": [
            "deconstruction", "deconversion", "faith crisis", "questioning faith",
            "leaving evangelicalism", "religious trauma", "faith doubt", "apostasy",
            "doubting believer", "evangelical trauma", "reconstructing faith",
        ],
    },
    {
        "slug": "biblical-sexuality",
        "name": "Biblical Sexuality",
        "category": "Culture & Society",
        "hook": "What does Scripture teach about same-sex attraction, marriage, and sexual identity — and how should evangelical churches care for LGBTQ+ neighbors and members?",
        "summary": "Evangelical perspectives on same-sex attraction, LGBTQ+ identity, sexual ethics, and what Scripture teaches about sexuality.",
        "keywords": [
            "sexuality", "same-sex", "LGBTQ", "homosexuality", "gender identity",
            "sexual ethics", "traditional marriage", "sexual orientation",
            "conversion therapy", "celibacy", "affirming churches",
        ],
    },
    {
        "slug": "church-accountability",
        "name": "Pastoral Accountability",
        "category": "Church Life",
        "hook": "How should evangelical churches build structures that protect the vulnerable, hold leaders accountable, and prevent the abuse of power?",
        "summary": "How churches build structures to prevent pastoral abuse, protect victims, and hold leaders accountable.",
        "keywords": [
            "pastoral abuse", "accountability", "church discipline", "abuse prevention",
            "leadership structure", "elder boards", "abuse", "misconduct",
            "victim protection", "clergy abuse", "spiritual abuse",
        ],
    },
    {
        "slug": "contemplative-prayer",
        "name": "Contemplative Prayer",
        "category": "Spiritual Formation",
        "hook": "Are contemplative practices like centering prayer and lectio divina a rich retrieval of Christian tradition — or a dangerous import of mystical techniques incompatible with evangelical theology?",
        "summary": "Evangelical debate over centering prayer, lectio divina, and the place of contemplative practices in Christian spirituality.",
        "keywords": [
            "contemplative prayer", "centering prayer", "lectio divina", "mysticism",
            "contemplation", "meditation", "listening to god", "silence",
            "prayer of examen", "contemplative spirituality", "mystical theology",
        ],
    },
    {
        "slug": "ai-and-the-church",
        "name": "Artificial Intelligence & the Church",
        "category": "Culture & Society",
        "hook": "How should Christians think about AI's impact on ministry, human dignity, creative work, and what it means to be made in the image of God?",
        "summary": "How AI is reshaping ministry, creative work, and evangelical thinking about human dignity and the image of God.",
        "keywords": [
            "artificial intelligence", "AI", "chatGPT", "machine learning",
            "technology", "automation", "human dignity", "image of god",
            "algorithmic", "digital ministry", "technology and faith",
        ],
    },
    {
        "slug": "biblical-justice",
        "name": "Biblical Justice & the Social Gospel",
        "category": "Culture & Society",
        "hook": "What is the evangelical responsibility toward the poor and oppressed — and how do we distinguish biblical justice from a social gospel that eclipses the gospel itself?",
        "summary": "Evangelical debate over poverty, oppression, and the distinction between biblical justice and the social gospel.",
        "keywords": [
            "justice", "social justice", "poverty", "poor", "oppressed",
            "social gospel", "systemic injustice", "prophetic", "inequality",
            "racial justice", "economic justice", "biblical justice",
        ],
    },
]

# Index by slug for fast lookups
TOPICS_BY_SLUG = {t["slug"]: t for t in TOPICS}

# Group by category
CATEGORIES = ["Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"]
TOPICS_BY_CATEGORY = {cat: [t for t in TOPICS if t["category"] == cat] for cat in CATEGORIES}
