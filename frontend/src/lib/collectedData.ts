// Every field Weirling records about your reading (#134), in plain language.
// backend/tests/test_utils/test_privacy_page.py checks that each table below
// lists exactly the database columns, so this page can't silently drift.

export interface CollectedField {
  field: string;
  what: string;
  why: string;
}

export interface CollectedTable {
  table: string;
  title: string;
  summary: string;
  retention: string;
  fields: CollectedField[];
}

const LINK = "Links the record to you and to the article.";

export const COLLECTED: CollectedTable[] = [
  {
    table: "user_content_interactions",
    title: "What you did with each article",
    summary: "One row per article you opened, saved, rated or skipped.",
    retention:
      "Kept while your account exists. After 90 days (TELEMETRY_RAW_RETENTION_DAYS) the two finest-grained fields, scroll depth and active reading time, are cleared; completion, ratings and saves stay because your interest map is built from them.",
    fields: [
      { field: "id", what: "A random record number.", why: "Database bookkeeping." },
      { field: "user_id", what: "Your account.", why: LINK },
      { field: "content_item_id", what: "The article.", why: LINK },
      { field: "prs_score", what: "The score the article had for you when it was shown.", why: "To check later whether the ranking was right." },
      { field: "was_suggested", what: "Whether it was a discovery pick from outside your sources.", why: "To learn which discoveries you like." },
      { field: "surfaced_in_digest", what: "Whether your digest showed it.", why: "To tell digest reading from browsing." },
      { field: "opened_at", what: "When you first opened it.", why: "Reading habits, such as the best time to send your digest." },
      { field: "read_completion_pct", what: "How much of it you read (0–100%).", why: "The main signal: finished articles teach the ranking most." },
      { field: "time_on_page_seconds", what: "Seconds the reader page was open.", why: "A rough reading-time signal for older clients." },
      { field: "scroll_depth_pct", what: "How far down you scrolled.", why: "Part of the completion estimate. Cleared after 90 days." },
      { field: "active_time_seconds", what: "Seconds you were actively reading (not idle, tab visible).", why: "Part of the completion estimate. Cleared after 90 days." },
      { field: "reached_end", what: "Whether you reached the end.", why: "A strong sign you finished it." },
      { field: "re_read_count", what: "How often you came back to it in a later session.", why: "Re-reading is a strong sign of value." },
      { field: "explicit_rating", what: "Your thumbs up or down.", why: "Your direct feedback to the ranking." },
      { field: "explicit_rating_reason", what: "The reason you picked (e.g. too basic, off-topic).", why: "Adjusts the ranking in the way you asked." },
      { field: "saved", what: "Whether you saved it.", why: "Saves are a strong positive signal and fill your saved list." },
      { field: "saved_at", what: "When you saved it.", why: "Ordering your saved list." },
      { field: "saved_read_at", what: "When you finished a saved article.", why: "Learning whether saving leads to reading." },
      { field: "shared", what: "Whether you shared it.", why: "A positive signal." },
      { field: "skipped", what: "Whether you skipped it.", why: "A negative signal." },
      { field: "graph_signal_applied", what: "How much of this record has already updated your interest map.", why: "So the same read is never counted twice." },
      { field: "tags", what: "Tags you gave a saved article, or that came with an import.", why: "Organising your saved list." },
      { field: "created_at", what: "When the record was created.", why: "Database bookkeeping." },
      { field: "updated_at", what: "When it last changed.", why: "Database bookkeeping and the 90-day clean-up." },
    ],
  },
  {
    table: "digest_impressions",
    title: "What your digest showed you",
    summary: "One row per article placed in a digest, with the numbers behind its position.",
    retention:
      "Deleted after 90 days (TELEMETRY_RAW_RETENTION_DAYS). Before deletion they are folded into daily counts per digest section that contain no user at all.",
    fields: [
      { field: "id", what: "A random record number.", why: "Database bookkeeping." },
      { field: "user_id", what: "Your account.", why: LINK },
      { field: "content_item_id", what: "The article.", why: LINK },
      { field: "digest_id", what: "Which digest it was in.", why: "Grouping by digest." },
      { field: "section", what: "The digest section (top reads, discover…).", why: "Measuring each section." },
      { field: "position", what: "Its place in the digest.", why: "Correcting for 'people read the top item more'." },
      { field: "score", what: "Its ranking score.", why: "Learning how to rank better for you." },
      { field: "features_json", what: "The signal values behind the score (topic match, source trust…).", why: "Learning which signals matter to you." },
      { field: "weights_version", what: "Which version of the ranking model scored it.", why: "Comparing model versions fairly." },
      { field: "exploration", what: "Whether it was a deliberate 'try something new' pick.", why: "So exploration doesn't bias the learning." },
      { field: "propensity", what: "How likely that pick was.", why: "Correcting for exploration when learning." },
      { field: "viewed", what: "Whether you opened the digest it was in.", why: "An item in a digest you never opened isn't counted as ignored." },
      { field: "team", what: "Which ranking chose it, in a head-to-head test digest.", why: "Measuring whether Weirling's ranking beats newest-first." },
      { field: "shown_at", what: "When it was shown.", why: "Timing and the 90-day clean-up." },
    ],
  },
  {
    table: "digests",
    title: "Your digests",
    summary: "One row per digest built for you.",
    retention: "Kept while your account exists, so you can look back at past digests.",
    fields: [
      { field: "id", what: "A random record number.", why: "Database bookkeeping." },
      { field: "user_id", what: "Your account.", why: "Links the digest to you." },
      { field: "generated_at", what: "When it was built.", why: "Showing the right digest and your history." },
      { field: "delivered_at", what: "When it was emailed, if it was.", why: "Not emailing the same digest twice." },
      { field: "delivery_method", what: "In the app or by email.", why: "Delivery bookkeeping." },
      { field: "section_counts", what: "How many items each section had.", why: "Showing the digest layout." },
      { field: "opened", what: "Whether you opened it.", why: "Learning your digest length and send time; pausing nudges." },
      { field: "total_items", what: "How many items it had.", why: "Skipping near-empty emails." },
      { field: "created_at", what: "When the record was created.", why: "Database bookkeeping." },
      { field: "updated_at", what: "When it last changed.", why: "Database bookkeeping." },
    ],
  },
  {
    table: "product_events",
    title: "Product events (hosted service only)",
    summary:
      "On the hosted service, one row for each of these moments: signing up, finishing onboarding, adding sources, a digest being sent or opened, opening or finishing an article, rating, saving, answering 'how many of the top 5 did you want?', subscribing and cancelling. Self-hosted instances record none by default (PRODUCT_METRICS), and nothing is sent to any third party.",
    retention:
      "Kept while your account exists and deleted with it. Daily totals with no account attached are kept for trends.",
    fields: [
      { field: "id", what: "A random record number.", why: "Database bookkeeping." },
      { field: "user_id", what: "Your account.", why: "Counting readers rather than clicks, and deleting your events with your account." },
      { field: "event", what: "Which moment it was, e.g. digest opened.", why: "Measuring whether the product works: weekly satisfied readers, retention, time to a first good digest." },
      { field: "props", what: "A small detail: the plan, a count, or your top-5 answer. Never article titles or text.", why: "Telling those measurements apart." },
      { field: "created_at", what: "When it happened.", why: "Weekly and daily totals." },
    ],
  },
];
