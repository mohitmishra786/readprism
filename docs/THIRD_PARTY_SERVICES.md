# Third-Party Services & Compliance

ReadPrism integrates the services below. This document records what each is used
for and the relevant terms, so operators can confirm compliant use (audit 08-8).
Software licenses of bundled libraries are separate from the service terms noted
here.

| Service | Used for | Data sent | Terms notes |
|---|---|---|---|
| **Groq** (Llama 3.3 70B / 3.1 8B) | Summarization, topic extraction | Article title + text | Content policy prohibits certain content classes; the digest/summarization use is compliant. No cold email. Summaries are cached to limit calls. |
| **OpenAI** (optional fallback) | Summarization when `OPENAI_FALLBACK_ENABLED=true` | Article title + text | Same content-policy considerations as Groq. Disabled by default. |
| **Zoho SMTP / Resend** | Digest email delivery | Recipient email + digest content | Transactional/user-requested email only — no cold or bulk marketing. Include a working unsubscribe (implemented) and, for bulk sending, a physical address and SPF/DKIM/DMARC on a sending subdomain. |
| **Browserless / Chrome** | Headless rendering of JS-heavy pages | Target URL | Runs in the operator's own container. Fetching respects robots.txt and the honest-bot posture. |
| **Meilisearch** | Full-text search index | Content titles/summaries | Self-hosted (MIT-licensed). Enforce a master key outside development. |

## Libraries (licenses)

sentence-transformers (Apache-2.0), pgvector (PostgreSQL License), feedparser,
trafilatura, BeautifulSoup, FastAPI, SQLAlchemy, Next.js, DOMPurify — all
permissively licensed and compatible with the project license.

## Operator responsibilities

- Set your own API keys; when self-hosting with your own keys, you are the
  contracting party with those providers and their terms apply to you.
- Keep summary caching enabled to control LLM spend and call volume.
- Do not use ReadPrism email delivery for unsolicited/bulk marketing.
