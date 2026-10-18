# 03 — Target User & ICP Definition

*Evidence types: **spec says** / **code shows** / **market shows**.*

## Status Snapshot

- **Spec says** five use cases: knowledge worker, niche developer, researcher, writer/trend-spotter, casual reader. All five are described; none is prioritized, resourced, or sized.
- **Code shows** the product as built serves the *developer/self-hoster* best today: Docker Compose deployment, OPML import, explainable ranking, honest platform-capability labels, MIT license — and serves the *casual reader* worst (setup friction, no mobile app, no hosted signup anywhere).
- The founder is a solo dev with no budget; LAUNCH.md already targets HN, r/rss, r/selfhosted — the channels where exactly one of the five ICPs lives.
- There is no hosted offering deployed, so any ICP that won't self-host cannot currently be served *at all*. This decides the first ICP by elimination.

## Ranked ICP recommendation

**#1 (court first): "The Developer With Deep Niche Interests" who already self-hosts.**
- Why: (a) reachable free via HN/r/selfhosted/r/rss where LAUNCH.md already has copy; (b) tolerates rough edges and cold-start weakness because they enjoy the machinery; (c) will read `services/ranking/` and become evangelists if the code is good — and it is presentable; (d) generates the highest-quality feedback on the ranking engine itself; (e) needs no billing infrastructure.
- Cost to serve: near zero (they run their own Postgres/Groq key). Risk: self-hosters convert to paid at only ~0.1–1% ([OSS monetization benchmarks](https://earnifyhub.com/blog/open-source-monetization-making-money-from-free-software)) — this ICP builds credibility and signal, not revenue.
- Success metric: 200 GitHub stars + 20 active self-hosted instances reporting anonymized cold-start metrics (opt-in) within 60 days of Show HN.

**#2 (court second, at hosted beta): "Knowledge Worker Following Too Many Sources."**
- The revenue ICP — matches the $4.99 Pro tier. But requires: hosted deployment, billing, mobile-decent web, deliverable email, and a cold-start experience that works without RSS literacy. **Code shows** none of the hosted/billing pieces exist yet. Do not market to this ICP before those exist; every one who bounces is burned.

**#3 (later): Researcher tracking people.** Creator-resolution code exists (`creator/resolver.py`, 13KB, cross-platform), but X/LinkedIn are unsupported (correctly labeled), which guts the academic use case where much discourse lives. Serve opportunistically.

**#4–5 (explicitly deprioritize): Writer/trend-spotter and Casual reader.** Trend detection is partially built (topic synthesis) but the emerging-trend surface the spec promises isn't; casual readers need a polished mobile product that is 2+ phases away. Cutting these focuses copy and roadmap.

## Checklist

- [ ] P0 | Declare ICP #1 in README and LAUNCH copy ("built for people who self-host and follow 50+ technical feeds") | Unfocused messaging converts nobody; the copy currently speaks to all five personas at once | README.md intro; spec §Use Cases | S | founder
- [ ] P0 | Add an opt-in anonymous telemetry ping for self-hosted instances (version, source count, digest opens) | Without it, ICP #1 produces zero learning | no such code in repo | M | eng
- [ ] P1 | Create a "5-minute self-host quickstart" path tested on a clean machine (single `.env` var required: GROQ_API_KEY) | ICP #1's activation moment is `docker compose up` working first try | README setup section exists; unverified E2E | M | eng
- [ ] P1 | Defer all knowledge-worker marketing until a hosted beta exists | Burning the revenue ICP on a self-host funnel wastes the only paid segment | no hosted deployment exists | S | founder
- [ ] P1 | Write the ICP-#1-specific value prop: "watch the engine learn" (expose meta-weights + interest graph viz in UI) | Devs adopt tools they can introspect; preferences page already fetches interest-graph data | frontend `api.preferences.interestGraph()` | M | eng
- [ ] P2 | Interview 5 r/selfhosted users who run FreshRSS/NewsBlur about what would make them switch | Cheapest possible ICP validation | none | S | founder
- [ ] P2 | Size ICP #2 properly before hosted launch (TAM of paying RSS users is small: NewsBlur sustains ~1 person; Feedly ~15M users mostly free) | The 8,000-Pro-subscriber target needs a reality-checked funnel | spec §Unit Economics; artifact 13 | S | founder

## Top 5 if you only do 5 things

1. Rewrite the README's first paragraph for the self-hosting developer, not the general knowledge worker.
2. Ship opt-in instance telemetry so ICP #1 generates learning.
3. Verify the clean-machine quickstart actually works end-to-end (see artifact 07 — it currently may not).
4. Add the interest-graph/meta-weights visualization — it's the demo that sells this ICP.
5. Write down "no knowledge-worker marketing until hosted beta" and hold to it.

**Revisit trigger:** re-run when a hosted beta exists, or after 50 active self-hosted instances.
