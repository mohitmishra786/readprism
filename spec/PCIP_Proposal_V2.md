**PRODUCT PROPOSAL -- VERSION 2**

**Personalized Content Intelligence Platform**

**With a full architecture for the Personalized Ranking Engine**

_A unified system for tracking websites and creators -- with an AI ranking algorithm that learns from how you actually read, what you act on, and what you skip -- delivering the exact right content in the exact right order for each specific person._

February 2026

# **Executive Summary**

The modern information problem has two layers. The first layer is aggregation: content is scattered across too many surfaces, and no single tool pulls it together with real intelligence. The second layer -- and the harder one -- is ranking: even once you have a unified feed, you may be looking at 100 or 200 items from a given day across all the sources and people you follow. Without a genuinely personalized ranking engine, you are still left triaging by hand.

This proposal describes the Personalized Content Intelligence Platform, referred to throughout as PCIP. It addresses both layers. The first layer -- aggregating websites you follow and creators you follow into a single unified feed with AI summarization -- was covered in the initial proposal. This version goes significantly deeper on the second layer: the ranking engine that ensures what appears at the top of your digest is not merely the most popular or most recent content from your sources, but the content that is most relevant to you specifically, on this day, given your evolving interests, your reading behavior, and what you have been paying attention to lately.

The ranking engine is not a filter. It is a continuously learning model of a single person's intellectual appetite, built from every signal that person generates as they use the product. It is what makes PCIP compellingly different from every existing tool, and it is what makes the product more valuable the longer someone uses it.

# **Why Ranking Is the Central Problem**

Imagine a user who follows 80 sources and 20 creators. On a given day, those sources and creators collectively produce somewhere between 150 and 400 new pieces of content. A chronological feed of 400 items is not useful -- it is just a different kind of noise. Even filtering by topic reduces this to perhaps 60 items, which is still too many for a working person to triage in a reasonable amount of time.

What the user actually needs is not a filtered list of content they might care about. They need a ranked list ordered by the probability that this specific item is worth their specific attention right now. The difference between those two things is the difference between a useful product and an overwhelming one.

Ranking this well is a hard problem for one fundamental reason: relevance is personal, temporal, and contextual, not universal. An article about interest rate policy is highly relevant to someone who manages a fixed-income portfolio and irrelevant to someone who does not, even if they both follow the same financial news source. An article about Rust programming is relevant to the developer who has been actively learning it this month and only mildly interesting to the developer who learned it two years ago and moved on. Relevance is not a property of content alone -- it is a relationship between content and a particular person at a particular moment.

_The core thesis of PCIP's ranking engine: relevance is a function of content, person, and time. All three variables must be modeled simultaneously and updated continuously._

No existing consumer tool does this. Feedly's Leo AI uses keyword filters and topic categories, which are static and user-maintained. Algorithmic social media feeds optimize for engagement, not for the user's genuine interests. Newsletters arrive in chronological order regardless of importance. The opportunity is to build a ranking system that treats each user as an individual with a unique, evolving intellectual profile -- and to make that system more accurate the more the user engages with it.

# **The Personalized Ranking Engine**

The ranking engine is the intelligence layer of PCIP. Every piece of content ingested from every source is passed through this engine before being placed in a digest. The engine produces a single number for each item: its Personalized Relevance Score, or PRS, for a specific user at the time the digest is generated. Items are sorted by PRS descending. The top items appear in the lead section of the digest. The rest are available in the full feed, also ranked.

The PRS is a weighted composite of multiple signal dimensions. The weighting is itself personalized: the system learns which signal dimensions are most predictive for each individual user. A user who is highly engaged by emerging topics gets a higher weight on novelty signals. A user who consistently reads long-form essays gets a higher weight on content depth signals. The meta-weights evolve over time just as the topic weights do.

The following sections describe each signal dimension in detail.

## **Signal Dimension 1: Semantic Interest Alignment**

This is the foundational signal. Every piece of ingested content is embedded using a sentence-level transformer model, producing a dense vector representation of its semantic content -- not its keywords, but its meaning. The user's interest profile is also represented as a vector space, built from the semantic content of everything they have read, engaged with, and explicitly endorsed over time.

The semantic distance between a piece of content and the user's interest vector is the base relevance signal. An article that sits close to the cluster of topics the user consistently engages with scores higher than one that is semantically distant, even if it contains keywords the user has flagged.

The key advantage of semantic embedding over keyword matching is generalization. A user interested in machine learning infrastructure does not need to have previously read about a specific new tool for that tool to score highly -- the system recognizes that the semantic content of the article falls within the user's established interest cluster and promotes it accordingly.

## **Signal Dimension 2: Reading Completion and Depth Signals**

What a user clicks is a weak signal. What they actually read is a much stronger one. PCIP tracks reading behavior at a granular level: how far into an article the user scrolled, how long they spent on it relative to the article's estimated reading time, whether they returned to it after an interruption, and whether they reached the end.

These signals are weighted as follows. A click with an immediate bounce -- less than ten seconds on the page -- is a slight negative signal: the preview was misleading or the content did not match expectations. A partial read, completing fifty to seventy percent of an article, is a moderate positive signal. A full read, completing ninety percent or more at a pace consistent with genuine reading rather than scanning, is a strong positive signal. A re-read -- returning to a piece the user has already encountered -- is the strongest organic signal the system can receive, indicating that the content had lasting value.

_The single most valuable signal in the entire system is when a user reads a piece the ranking engine surfaced as a suggestion -- one they would not have found themselves. That signal is recorded as a pure preference revelation, uncontaminated by prior knowledge of the source or the author._

## **Signal Dimension 3: Suggestion-Driven Reading (The Purest Signal)**

This signal deserves its own dedicated dimension because it is categorically different from all others. Every other signal the system receives is potentially contaminated by selection bias: the user chose to follow this source, the user sought out this creator, the user clicked this article partly because they already knew they liked the author. None of that is pure preference revelation.

When the ranking engine surfaces a piece of content from a source or creator the user has not explicitly followed -- discovered via the system's interest-graph expansion -- and the user reads it, that is a clean signal. They read it because the content itself resonated with their interests, not because of prior loyalty to the source. PCIP gives this signal a significantly higher weight in updating the interest model than any behavior toward followed sources.

This creates a virtuous loop. As the interest model improves, the system's suggestions become more accurate. As the suggestions become more accurate, more users read suggested content. As more suggested content gets read, the interest model receives cleaner signal and improves further. The product gets meaningfully better the more it is used, and the improvement accelerates over time.

This is also one of the product's key retention mechanics. A user who reads a suggested article from an unfamiliar source and finds it genuinely valuable has had an experience that no other tool in the category can provide. That experience creates loyalty.

## **Signal Dimension 4: Explicit Feedback Signals**

Explicit feedback is the highest-confidence signal the system receives, but it is also the most expensive for the user to provide. PCIP collects explicit feedback through several mechanisms, all designed to be as low-friction as possible.

A thumbs up on an item in the digest is a strong positive signal toward all the semantic dimensions of that content. A thumbs down is a strong negative signal. But PCIP also collects more nuanced explicit feedback: the user can tag an item with a reason -- too basic, already knew this, too tangential to my main interests, wrong depth level -- and each of these reasons informs a specific dimension of the interest model rather than just applying a generic penalty.

The user can also explicitly adjust their interest profile through a settings interface: marking topics as higher priority, lower priority, or temporarily suppressed. Temporarily suppressing a topic -- such as politics during a period when the user wants to focus on technical reading -- is a time-bounded signal that the system honors for a configurable period and then gently resurfaces.

The save or bookmark signal is treated separately from the thumbs up. Saving an article for later reading is a signal about intent, not about satisfaction. A saved article that is later read fully is a strong positive signal. A saved article that is never opened is a neutral or slightly negative signal -- the user found the premise interesting enough to save but not compelling enough to return to.

## **Signal Dimension 5: Source and Creator Trust Weights**

Not all sources are equal to a given user, even within a topic area. A developer who follows five blogs about distributed systems may trust two of them deeply for original research and treat the other three as good-but-secondary sources. The ranking engine learns this from behavior: articles from high-trust sources consistently get read fully and rated positively, while articles from lower-trust sources get skimmed or skipped.

The system builds an implicit trust weight for every source and creator in the user's library. These weights are never shown to the user as numbers -- they are just reflected in how the system ranks content from each source. A new source starts with a neutral weight. It earns higher weight through consistent positive engagement and loses weight through consistent skipping or early exits.

For creators specifically, the trust weight can become highly granular. A creator who publishes on multiple topics may be trusted deeply for their writing on one topic and less so on another. The system tracks this at the creator-topic intersection, not just at the creator level. A writer who is extraordinary on urban planning and mediocre on general politics will have high weight applied to their planning pieces and lower weight on political commentary, regardless of whether the user ever articulates that distinction explicitly.

## **Signal Dimension 6: Content Quality and Depth Signals**

Beyond personal preference, the ranking engine also incorporates signals about the objective qualities of content that tend to correlate with value across users. These signals are used to break ties within similar personal relevance scores and to penalize low-quality content that might otherwise score well on superficial interest alignment.

Content depth is estimated from several signals: article length, reading time relative to word count, presence of citations or references, whether the article links to primary sources, the vocabulary level and structural complexity of the writing, and whether the article contains original reporting or analysis versus summarizing existing work.

Recency is also factored, but not as a primary signal. A highly relevant article from three days ago should appear above a mildly relevant article from this morning. Recency is a tiebreaker and a decay function, not a primary ranking factor. Content has a recency decay curve that the system adjusts based on the user's behavior: users who consistently prefer fresh news get a steeper recency curve; users who consistently read evergreen essays get a flatter one.

## **Signal Dimension 7: Temporal and Contextual Signals**

Relevance is not constant over time. A user's intellectual priorities shift, and the ranking engine must shift with them. PCIP models interest at three temporal scales simultaneously.

The long-term interest model represents stable, enduring topics the user cares about across months and years. These are the core of the user's intellectual identity. They change slowly and require consistent contrary evidence to down-weight.

The medium-term context window represents topics the user has been focused on in the past two to four weeks. If a user has been reading heavily about a company's product strategy for three weeks because they are doing competitive research, that context elevates related content even if product strategy is not a permanent top interest. The medium-term window decays over four to eight weeks if engagement with the topic does not continue.

The short-term session context captures what the user has been reading in the past few days. If they have already read five articles about a specific event or announcement, the sixth article about the same event is down-ranked even if it would otherwise score well -- the user has already gotten substantial coverage and the marginal value of another piece on the same topic is low. This is the deduplication-by-saturation mechanism.

Time of day is also a contextual signal. Users exhibit consistent patterns in what they want to read at different times. Morning reads tend toward briefings and catch-ups; evening reads tend toward longer, more reflective pieces; weekend reads may lean toward deep essays and features. The system learns each user's individual time-of-day pattern and adjusts digest composition accordingly.

## **Signal Dimension 8: Novelty and Serendipity Controls**

A ranking engine that only promotes what a user has previously demonstrated interest in risks creating a filter bubble: the user sees only what confirms their existing interests and never encounters genuinely new ideas. PCIP addresses this through a deliberate novelty and serendipity layer.

A configurable percentage of each digest -- defaulting to fifteen percent -- is reserved for content that scores well on interest model similarity but comes from topics or sources slightly outside the user's established clusters. This content is labeled in the digest as something like: based on your reading, this might be of interest. Users can adjust this percentage, turning it down if they want a tighter focus or up if they want more discovery.

The system also tracks the diversity of content the user has been consuming. If the past two weeks show very narrow topical focus, the serendipity layer is gently increased to prevent intellectual stagnation. If the user has been reading broadly, the serendipity layer is reduced slightly in favor of depth within their core clusters.

Importantly, content surfaced through the serendipity layer that gets read fully generates the same high-value pure preference signal described in Signal Dimension 3. The serendipity layer is therefore not just good for the user -- it is good for the model.

## **How the Signals Combine: The Scoring Formula**

Each of the eight signal dimensions produces a score between zero and one for a given piece of content. These scores are combined into the final Personalized Relevance Score using a weighted sum, where the weights are themselves personalized and learned for each user.

_PRS = w1 x SemanticAlignment + w2 x ReadingDepth + w3 x SuggestionSignal + w4 x ExplicitFeedback + w5 x SourceTrust + w6 x ContentQuality + w7 x TemporalContext + w8 x NoveltyAdjustment where w1 through w8 sum to 1.0 and are individually learned per user._

New users start with equal weights across all dimensions, with a slightly higher initial weight on semantic alignment and explicit feedback, since those signals are available from day one. As the user accumulates behavioral history, the meta-learning layer -- a gradient boosting model trained on whether the user's actual reading behavior matched the predicted PRS ranking -- adjusts the weights to maximize prediction accuracy for that specific user.

This means that for one user, source trust might be the dominant signal. For another, reading depth signals might matter most. For a third, the temporal context window might be the most predictive factor. The system discovers this for each user rather than imposing a universal weighting.

# **The Personal Interest Graph**

The interest model is stored as a directed weighted graph, not as a flat list of topics. This distinction matters because intellectual interests are not independent of each other -- they form clusters, hierarchies, and cross-connections that a flat list cannot represent.

In a user's interest graph, nodes represent topics, subtopics, and specific intellectual domains at varying levels of granularity. Edges between nodes represent the strength of the user's tendency to move from one topic to another within a reading session -- their intellectual adjacencies. The weight of a node represents the user's overall engagement with that topic over time.

This graph structure enables a capability that flat keyword models cannot provide: transitive relevance. If a user reads heavily about programming language design and about compiler optimization, and those two nodes have a strong edge between them -- because the user consistently reads them together -- then a new article about type inference in systems languages can be recognized as highly relevant even if the user has never explicitly engaged with that exact subtopic before. It sits at the intersection of two strongly connected nodes in their graph.

The interest graph also enables the system to explain its ranking decisions to the user. Rather than just saying this article scored 0.87 on your interest model, the system can say: this article was ranked highly because it connects your interest in distributed consensus algorithms with your recent reading about database internals. That explanability builds trust in the ranking and helps users calibrate their explicit feedback.

### **Graph Initialization**

The interest graph is initialized during onboarding through a combination of explicit topic selection, a short reading sample -- the user reads three or four articles from different domains and the system embeds all of them -- and optionally by importing an OPML file from an existing RSS reader, which reveals which sources the user has historically chosen to follow.

Within the first week of normal use, the graph has enough behavioral data to begin producing meaningfully personalized rankings. Within the first month, most users report that the digest feels genuinely tailored to them. This timeline is a design target, not an aspiration: the onboarding and early experience must be carefully designed to collect high-quality signal quickly without burdening the user.

### **Graph Evolution and Decay**

Interest graphs change over time. Topics that were central three years ago may have become peripheral. New interests emerge. The graph must reflect the current user, not the user from two years ago.

PCIP applies temporal decay to all node weights using an exponential decay function with a half-life that varies by node type. Core stable interests -- large, well-connected nodes with years of consistent engagement -- have long half-lives and change slowly. Peripheral or recently acquired interests have shorter half-lives and fade more quickly if engagement drops.

The system also detects interest transitions: when a previously peripheral node begins receiving consistent engagement and a previously central node begins to be skipped. These transitions are detected algorithmically and reflected in the graph within days, so the ranking engine adapts quickly to shifts in what the user cares about.

# **Solving the Cold Start Problem**

The cold start problem is the single greatest risk to a personalization-first product: the system is not useful enough in the first days to retain the user long enough to collect the data needed to make it useful. This is not a hypothetical concern -- it is the reason many personalization products fail.

PCIP addresses cold start through three mechanisms that work in parallel.

### **Mechanism One: High-Quality Onboarding Signal**

Onboarding is designed to extract more signal per minute than any other part of the product experience. The user is asked to describe their interests in a free-text field -- not to select from a category list, because free text produces richer semantic data. They are asked to rate three to five sample articles on whether they would want to read something like this. They are asked which sources they currently find most valuable. Each of these interactions is immediately reflected in the initial interest graph, so the first digest is already meaningfully better than a generic feed.

### **Mechanism Two: Collaborative Filtering Warmup**

For new users whose interest graph is sparse, PCIP uses a collaborative filtering layer as a temporary scaffold. Users with similar onboarding profiles -- similar topic selections, similar source libraries, similar reading sample ratings -- are grouped, and the behavioral data from users who have been using the product longer is used to supplement the new user's sparse model. This collaborative warmup is gradually replaced by the user's own behavioral data as it accumulates, and is phased out entirely within two to three weeks of active use.

### **Mechanism Three: Explicit Early Feedback Prompts**

In the first two weeks, the digest includes a small number of targeted feedback prompts: not intrusive rating requests, but specific questions about specific items. Was this the right depth level for you? Would you want more from this source? Did this topic connection feel accurate? These prompts are presented conversationally and are limited to two or three per digest to avoid fatigue. The responses to these prompts provide high-quality labeled data that accelerates the interest graph toward accuracy faster than passive behavioral observation alone.

# **From Ranking to Digest Construction**

The PRS ranking produces an ordered list of items for a given user at a given moment. Converting this ordered list into a digest that a person actually wants to read requires several additional construction decisions.

### **Saturation Limits**

Even if the top ten items by PRS all happen to cover the same breaking news story from different angles, showing all ten is not useful. The digest applies a saturation limit: no single topic cluster can account for more than a defined percentage of the digest -- defaulting to thirty percent -- regardless of individual item scores. Once that limit is reached, the next item from that topic cluster is skipped in favor of the highest-ranked item from a different cluster. Saturation limits are also configurable by the user.

### **Digest Sectioning**

The final digest is divided into sections that reflect different reading intentions, not just different topics. The lead section -- typically three to five items -- contains the highest-ranked items across all clusters, the things the user most needs to see today. The creator section groups content by person rather than by topic, so the user can see what each of their followed creators has been producing. The deep reads section contains longer pieces ranked highly on the interest model. The discovery section contains the serendipity layer content, clearly labeled. This sectioning ensures that a user who only has five minutes can read the lead section and feel informed, while a user who has an hour can work through the entire digest.

### **Digest Length Personalization**

Different users have different digest length preferences, and the same user may have different preferences on different days. PCIP learns each user's typical engagement pattern -- how many items they open per digest on average, how much time they spend -- and calibrates the default digest length to match. A user who consistently reads eight items and then stops will receive a ten-item digest rather than a twenty-item one. A user who consistently reads through long digests will receive more items. Length preference can also be set explicitly.

# **Why the Ranking Engine Is a Defensible Advantage**

A ranking engine built on behavioral signals has a property that almost no other software feature has: it gets exponentially more valuable with use, and that accumulated value is not portable. A user who has been using PCIP for eighteen months has an interest graph that took eighteen months to build. That graph is personalized to a degree that no competitor can replicate for that user from a standing start. The switching cost is not just the friction of moving to a new tool -- it is the loss of a model that genuinely knows how you read.

This creates a natural retention flywheel. Users who use the product actively for thirty days experience a noticeably better digest than they did on day one. Users at ninety days experience it as genuinely indispensable. Users at one year find it difficult to imagine going back to managing their information diet manually. Each of these milestones is a retention checkpoint, and each one is driven by the accumulation of ranking signal rather than by any artificial lock-in.

The ranking engine is also difficult to replicate because the highest-quality signal -- reading behavior from suggested content -- only accumulates if the product is already surfacing good suggestions. A competitor starting from zero does not just need to build the same algorithm: they need to build it and then wait for enough behavioral data to make it competitive. That data advantage compounds over time.

This is the core of PCIP's competitive moat. It is not a feature moat -- any well-funded team can build similar features. It is a data and personalization moat built one user's reading session at a time.

# **The Existing Landscape and Its Failures**

The Perplexity-generated proposal that preceded this document covers the competitive landscape at a surface level. The following assessment goes deeper, with particular attention to where each competitor's approach to ranking and personalization breaks down.

### **Feedly and Leo AI**

Feedly is the most mature product in the category and Leo is the most developed AI layer on any RSS reader. Leo allows users to train it by marking articles as important or irrelevant and by creating keyword-based prioritization rules. The fundamental limitation is that Leo uses keyword and topic category matching rather than semantic embeddings and behavioral signal. It does not learn from how you read -- only from what you explicitly tell it. Users who have used Leo extensively report that it requires constant manual maintenance and still misses or misranks content in ways that a behavioral model would not. It also has no concept of temporal context, no medium-term context window, and no discovery or serendipity layer. All AI features are behind the $12.99 per month Pro+ tier.

### **Inoreader**

Inoreader has no AI layer whatsoever. It surfaces content chronologically with optional manual sorting rules. It is powerful as a raw feed aggregator but makes no attempt at personalization. Users who want intelligent ranking must build it themselves through elaborate rule systems, which most abandon within weeks.

### **Social Platform Algorithms**

Twitter/X, LinkedIn, and YouTube all have recommendation algorithms, but they optimize for time-on-platform, not for the user's genuine intellectual development. They amplify content that generates emotional reactions and engagement, not content that is accurate, deep, or genuinely relevant to the user's professional interests. Users cannot audit, explain, or meaningfully influence these algorithms. They are designed for the platform's revenue, not the user's benefit.

### **Newsletter Tools: Readless, Meco, Mailbrew**

None of these tools have a ranking layer. They aggregate and present content chronologically. Readless provides AI summaries, which is valuable, but it does not rank the summaries by personal relevance -- the user still must triage by hand. The absence of behavioral learning means these tools provide the same experience on day one hundred as on day one.

**Capability**

**PCIP**

**Feedly Leo**

**Inoreader**

**Readless**

**Social Algos**

Semantic interest alignment

Yes -- behavioral

Partial -- keyword only

No

No

No

Reads completion depth signal

Yes

No

No

No

No

Suggestion-driven pure signal

Yes -- highest weight

No

No

No

No

Explicit multi-dimension feedback

Yes -- granular

Partial -- thumbs only

No

No

No

Per-source trust weights (learned)

Yes

No

No

No

No

Content quality depth scoring

Yes

No

No

No

No

Three-scale temporal context model

Yes

No

No

No

No

Controlled serendipity layer

Yes -- configurable

No

No

No

No

Personalized meta-weights per user

Yes

No

No

No

No

Interest graph (not flat topics)

Yes

No

No

No

No

Cold start collaborative warmup

Yes

No

No

No

N/A

Available on free tier

Yes

No -- $12.99/mo

No

No

Yes (forced)

# **The Product: PCIP**

PCIP is built around two primitive objects: Sources and People. A Source is any publication, website, blog, forum, or channel. A Person is any individual creator who publishes across one or more platforms. Every capability in the product exists to serve the user's relationship with those two objects and to surface the most relevant content from those objects in the right order at the right time.

### **Adding a Source**

The user pastes any URL. PCIP detects RSS or Atom feeds automatically, falls back to web scraping for non-RSS sites, and begins ingestion immediately. The user can set a trust weight, tag the source with topics, or mark it as high priority. No RSS knowledge is required.

### **Adding a Person**

The user enters a name or any profile URL. PCIP resolves the creator identity across platforms -- linking their Substack, YouTube, Twitter/X, personal blog, Medium, LinkedIn, podcast feed, and any other publishing presence it can discover. Everything that person publishes across all linked platforms is ingested as a unified stream and ranked by the user's personal interest model.

### **The Digest**

Once or twice per day, PCIP generates a personalized digest. Items are ranked by Personalized Relevance Score. The digest is sectioned into lead items, creator updates, deep reads, and discovery content. Each item includes a headline, a two-to-three sentence summary, and a link. Items covering the same story from multiple sources are synthesized into a single entry with all perspectives noted. Digest length adapts to the user's typical engagement pattern.

# **Use Cases**

### **The Knowledge Worker Following Too Many Sources**

A product manager follows 80 sources across competitor blogs, industry analysis, newsletters, and thought leaders. Before PCIP, this means triaging 150 or more items per day across five different platforms. With PCIP, the morning digest presents the twelve most relevant items ranked by the interest model, with summaries. The product manager reads for fifteen minutes and has a complete picture of what matters today. The ranking engine has learned that this person cares more about product strategy than about general technology news, more about B2B SaaS than about consumer products, and adjusts accordingly.

### **The Developer With Deep Niche Interests**

A backend engineer cares specifically about distributed consensus, storage engine internals, and programming language semantics. Most tech news is irrelevant to them. The interest model learns this quickly and begins suppressing general technology coverage in favor of the deep technical pieces the engineer consistently reads in full. After six weeks, the engineer's digest is almost entirely composed of content they would have spent an hour hunting for manually -- surfaced automatically and ranked accurately.

### **The Researcher Tracking a Field and Its People**

An academic follows twenty-five researchers and wants to see everything they produce, across all platforms, ranked by how closely it aligns with their own current research focus. The creator tracking layer unifies each researcher's publishing presence. The interest model, aware of the academic's current project focus, promotes papers and posts in that area and surfaces tangentially related work in the discovery section. When the project focus shifts, the medium-term context window adapts within days.

### **The Writer Detecting Emerging Topics**

A journalist or independent writer needs early signal on topics before they become saturated. The cross-source synthesis layer detects when multiple sources in the user's library begin covering a new topic simultaneously and surfaces it as an emerging trend. The ranking engine promotes this emerging content because novelty is a factor in the PRS, and the writer can pitch or start drafting before the story is everywhere.

### **The Casual Reader Who Simply Wants Less Noise**

A general reader follows twenty sources and three creators and receives far more content than they want to engage with. For this user, the ranking engine is invisible: they just receive the five best things from everything they follow, every morning. The system learns their preferences passively from reading behavior. The digest quality improves over the first few weeks, and the user experiences it as simply having a smarter reading habit.

# **Technical Architecture**

### **Ingestion Layer**

Content enters PCIP through RSS and Atom parsing for well-maintained publications, web scraping via a headless browser cluster for non-RSS sources, platform API integrations where available with graceful fallback, and a newsletter forwarding address that routes subscriptions directly into the system. Ingestion is fault-tolerant: scraper blocks, API deprecations, and feed failures degrade gracefully with user notification rather than silent failure.

### **Intelligence Pipeline**

Each ingested item passes through a sequential pipeline: content extraction and cleaning, semantic embedding via a sentence-transformer model, PRS computation against all users following that source, deduplication by semantic similarity across items already in the user's queue, summarization at three levels -- headline, brief, and detailed takeaway -- and topic clustering for synthesis detection. The pipeline is asynchronous and runs on a job queue so that digest generation is fast even when underlying computation is deferred.

### **Interest Model Storage**

The interest graph for each user is stored as a combination of a dense embedding vector representing the aggregate of their reading history and a sparse graph structure representing topic nodes and their relationships. Updates are applied incrementally after each user interaction, not in batches, so the model reflects the most recent behavior immediately. pgvector in PostgreSQL handles the vector similarity computations needed for PRS scoring at scale.

**Component**

**Technology**

**Purpose**

Backend API

Python / FastAPI

Feed processing pipelines, ML inference orchestration, user API

Frontend

Next.js (React)

Web app, digest reader, source and creator management interfaces

Database

PostgreSQL + pgvector

User data, content archive, vector similarity for interest matching

Cache and Queue

Redis + Celery

Async feed fetching, PRS computation jobs, deduplication cache

Embeddings

sentence-transformers (local)

Semantic vectors for content and interest model -- no API cost

Summarization LLM

Llama 3 / Mistral (self-hosted)

Item summaries, cross-source synthesis -- commercial API as fallback

Meta-learning model

XGBoost / LightGBM

Learns per-user signal weightings from historical prediction accuracy

Email delivery

Resend or Amazon SES

Digest delivery with HTML templating

Scraping

Playwright + Browserless

Headless browser pool for non-RSS sources

Search

Meilisearch

Full-text search across the user's ingested content archive

Deployment

Docker Compose / Kubernetes

Self-hostable single-machine option and cloud-native scale

# **Development Roadmap**

### **Phase One: Reliable Ingestion (Months 1 through 3)**

RSS and Atom parsing, basic web scraping, newsletter forwarding, and a clean chronological feed with manual categorization. Email digest delivery. The goal of phase one is reliable, comprehensive ingestion infrastructure that the ranking layer will build on top of. No AI layer yet -- but the product must already feel useful as a clean aggregator so that users have a reason to stay and generate signal.

### **Phase Two: Core Ranking Engine (Months 4 through 6)**

The full PRS computation pipeline is implemented: semantic embeddings for all content, initial interest graph from onboarding, behavioral signal collection for reading depth and completion, explicit feedback mechanisms, and the first version of source trust weights. The digest is now ranked. Summarization is introduced for items above a PRS threshold. Deduplication is applied. The cold start collaborative warmup layer is implemented and active for new users. By the end of phase two, the core value proposition is fully demonstrable.

### **Phase Three: Advanced Personalization and Creator Tracking (Months 7 through 9)**

The meta-learning layer is introduced, learning per-user signal weights from accumulated prediction data. The three-scale temporal context model -- long-term, medium-term, and session context -- is implemented. The serendipity layer is activated. Creator identity resolution across platforms is built and launched. Cross-source topic synthesis is introduced. The interest graph structure replaces the flat topic vector for users with sufficient behavioral history.

### **Phase Four: Ecosystem and Scale (Months 10 through 12)**

Mobile progressive web app with offline support and push notifications. Browser extension for one-click source and creator addition. Integrations with Obsidian, Notion, and Logseq. A discover feature that suggests new sources and creators based on the interest graph. The self-hosted Docker Compose option is fully documented and supported. Team digest capability for collaborative use cases.

# **Pricing**

Pricing is a product decision. Gating the ranking engine behind a paywall would communicate that the unranked experience is acceptable, which contradicts the entire product premise. The full ranking engine is available on the free tier.

**Tier**

**Price**

**Sources**

**Creators**

**Ranking Engine**

**Digest Frequency**

Free

$0 / month

30 sources

5 creators

Full PRS ranking and summarization

Once daily

Pro

$4.99 / month

Unlimited

50 creators

Full engine + synthesis + serendipity controls

Up to 4x daily

Team

$11 / seat / month

Unlimited

Unlimited

Shared digests, team interest profiles

Configurable

Self-Hosted

Free (open source)

Unlimited

Unlimited

Full features, user-supplied LLM API key

Configurable

The free tier at thirty sources and five creators covers most casual users completely. The Pro tier at $4.99 per month undercuts Feedly Pro+ at $12.99, Readwise Reader at $9.99, and Readless at $9, while offering a more sophisticated ranking layer than any of them.

# **Unit Economics**

**Cost Item**

**Free User**

**Pro User**

**Notes**

Feed ingestion and scraping

$0.08 / mo

$0.20 / mo

Scales with source count and scraping frequency

LLM summarization inference

$0.12 / mo

$0.48 / mo

Lower with self-hosted; commercial API only as fallback

PRS computation (embedding similarity)

$0.04 / mo

$0.10 / mo

pgvector on commodity hardware -- very low marginal cost

Meta-learning model inference

$0.01 / mo

$0.03 / mo

Lightweight gradient boosting -- negligible compute

Email delivery

$0.02 / mo

$0.05 / mo

SES / Resend pricing at scale

Storage and database

$0.04 / mo

$0.09 / mo

Content archive, vectors, graph storage

Total estimated cost

$0.31 / mo

$0.95 / mo

Revenue per user

$0.00

$4.99

Gross margin (Pro)

\--

approx. 81%

The business reaches sustainable profitability at approximately eight thousand Pro subscribers, generating around forty thousand dollars per month in revenue against an estimated eight thousand dollars per month in infrastructure at that scale. Summary caching -- storing a generated summary and reusing it across all users who follow the same source -- significantly reduces LLM inference cost as the user base grows.

# **Risks and Honest Assessment**

### **The Cold Start Problem Is the Most Acute Risk**

A ranking engine that requires weeks to become accurate will lose users before it has data to work with. The three cold start mechanisms -- high-quality onboarding, collaborative filtering warmup, and early feedback prompts -- are designed to address this, but they must be implemented with exceptional care. The first digest a new user receives must already feel noticeably smarter than a generic feed. This is not guaranteed and requires deliberate design work to achieve.

### **Behavioral Signal Requires Active Use**

The ranking engine improves with use, which means it is weakest for light users who only open the digest occasionally. A user who opens the digest once per week and reads two items gives the system very little to learn from. PCIP must be useful enough for this user through content quality signals and the collaborative warmup that they keep using it at least occasionally, rather than churning before the model has a chance to personalize.

### **Scraping Reliability Is a Continuous Operational Burden**

Websites change their structure, introduce anti-bot measures, and move content behind paywalls. Keeping scrapers functional across hundreds of different source sites requires ongoing engineering investment. This is not a solvable problem -- it is a maintenance commitment. The team must budget for it as a recurring cost of the product, not a one-time setup.

### **Platform API Restrictions Are Worsening**

Twitter/X, Reddit, and YouTube have all significantly restricted API access in recent years. Creator tracking for creators who are primarily active on these platforms will be the weakest part of the product. The design must treat API access as a bonus rather than a requirement, with RSS and scraping as fallbacks. Users must be informed when a platform cannot be tracked reliably.

### **Competition from Well-Funded Incumbents**

Feedly could add behavioral signal to Leo. A well-funded startup could enter the space with more resources. The answer to this risk is speed, a better out-of-the-box user experience, and the data moat that accumulates with each user's reading history. A competitor starting from zero does not just need to build the same algorithm -- they need to wait for the same accumulation of behavioral signal that makes it accurate. That advantage compounds with time.

# **Conclusion**

The content curation market has been stuck in one of two failure modes: tools that aggregate without intelligence, leaving users to do their own triaging, or tools that apply intelligence through blunt keyword filters that require constant manual maintenance and still miss what matters.

PCIP is built around a different premise. Relevance is not a universal property of content -- it is a relationship between a specific piece of content and a specific person at a specific moment. Building a system that models that relationship accurately and continuously is the actual product. The digest, the summarization, the creator tracking, and the aggregation are all surfaces through which that model delivers value.

The ranking engine described in this proposal -- eight signal dimensions, personalized meta-weights, a three-scale temporal context model, a graph-structured interest model, and a pure-signal learning loop from suggestion-driven reading -- is technically achievable with existing tools and infrastructure. It is not being built today because the category has been dominated by simpler aggregation-first products and by enterprise-focused tools that have not prioritized the individual user.

That gap -- a genuinely intelligent personal reading tool, available at an individual-justifiable price, that gets meaningfully better the more you use it -- is the market opportunity. The ranking engine is how PCIP fills it, and it is why the product becomes harder to replace the longer someone uses it.