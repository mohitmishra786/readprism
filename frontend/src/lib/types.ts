export interface User {
  id: string;
  email: string;
  display_name: string | null;
  onboarding_complete: boolean;
  digest_frequency: string;
  digest_time_morning: string;
  send_time_locked: boolean;
  digest_max_items: number;
  digest_length_locked: boolean;
  serendipity_percentage: number;
  preferred_languages: string[];
  tier: string;
  timezone: string;
  created_at: string;
  /** False only while this instance requires email confirmation (#175). */
  email_verified?: boolean;
  /** Hosted fetch budget exhausted until then (#169). */
  fetch_paused_until?: string | null;
  /** Keep my reading out of other readers' collaborative warmup counts (#210). */
  collaborative_opt_out?: boolean;
}

export interface Source {
  id: string;
  user_id: string;
  url: string;
  name: string | null;
  feed_url: string | null;
  source_type: string;
  trust_weight: number;
  is_active: boolean;
  last_fetched_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
  fetch_error_count: number;
  health: "healthy" | "degraded" | "failing" | "dead";
  items_per_week: number;
  topics: string[];
  priority: string;
  created_at: string;
}

export interface CreatorPlatform {
  id: string;
  creator_id: string;
  platform: string;
  platform_url: string;
  feed_url: string | null;
  is_verified: boolean;
  last_fetched_at: string | null;
  tracking_tier: string | null;
  display_label: string | null;
}

/** Platform → { tracking_tier, display_label } from the backend capabilities map. */
export type PlatformCapabilities = Record<
  string,
  { tracking_tier: string; display_label: string }
>;

export interface Creator {
  id: string;
  user_id: string;
  display_name: string;
  resolved: boolean;
  priority: string;
  trust_weight: number;
  platforms: CreatorPlatform[];
  created_at: string;
}

export interface ContentItem {
  id: string;
  source_id: string | null;
  creator_platform_id: string | null;
  url: string;
  title: string;
  author: string | null;
  published_at: string | null;
  fetched_at: string;
  summary_headline: string | null;
  summary_brief: string | null;
  summary_detailed: string | null;
  reading_time_minutes: number | null;
  content_depth_score: number | null;
  word_count: number | null;
  has_citations: boolean;
  is_original_reporting: boolean | null;
  topic_clusters: string[];
  summarization_cached: boolean;
  /** "llm" summaries are labelled as AI-written (#177). */
  summary_source?: string | null;
  paywalled?: boolean;
  page_type?: string | null;
  language?: string | null;
  created_at: string;
}

/** Full content item including the extracted body — only from the single-item endpoint. */
export interface ContentItemFull extends ContentItem {
  full_text: string | null;
  /** Text exists but the hosted display policy withholds it (#177). */
  full_text_withheld?: boolean;
}

export interface DigestItem {
  id: string;
  digest_id: string;
  content_item_id: string;
  position: number;
  section: string;
  prs_score: number;
  signal_breakdown: Record<string, number | string>;
  content: ContentItem | null;
}

export interface Digest {
  id: string;
  user_id: string;
  generated_at: string;
  delivered_at: string | null;
  delivery_method: string;
  section_counts: Record<string, number>;
  opened: boolean;
  total_items: number;
  items: DigestItem[];
  created_at: string;
}

export interface FeedItem {
  content: ContentItem;
  prs_score: number | null;
  signal_breakdown: Record<string, number | string>;
}

export interface InterestGraphNode {
  label: string;
  weight: number;
  is_core: boolean;
}

export interface InterestGraphEdge {
  from_label: string;
  to_label: string;
  weight: number;
}

export interface InterestGraph {
  nodes: InterestGraphNode[];
  edges: InterestGraphEdge[];
}

export interface Token {
  /** Empty in cookie mode (#103): credentials are httpOnly cookies. */
  access_token: string;
  refresh_token?: string | null;
  token_type: string;
  expires_in: number;
  csrf_token?: string | null;
}

export interface BillingState {
  plan: "selfhost" | "trial" | "pro" | "team" | "free";
  billing_enabled: boolean;
  /** Academic discount applies at checkout (verified academic email, #250). */
  academic_discount?: boolean;
  status: string | null;
  trial_ends_at: string | null;
  trial_days_left: number | null;
  plan_expires_at: string | null;
  can_manage: boolean;
}

/** A curated starter pack of feeds (#152). */
export interface StarterPack {
  id: string;
  title: string;
  feed_count: number;
  feeds: { name: string; url: string }[];
  /** Matches the user's confirmed topics; pre-selected in the picker. */
  suggested: boolean;
  /** How many of the pack's feeds the user already follows. */
  subscribed: number;
}

/** Result of a feed or saved-article import (#150, #202). */
export interface ImportResult {
  kind?: string;
  created: number;
  skipped?: number;
  already_had?: number;
  queued?: boolean;
  job_id?: string;
  errors: { row?: number; url: string; error: string }[];
}

/** Live score and explanation for one item (#267). */
export interface WhyNotSeen {
  content_id: string;
  title: string;
  score: number;
  explanation: string;
  why_topics: string | null;
  verdict: "shown" | "not_an_article" | "not_followed" | "ranked_below_cutoff" | "no_digest_yet" | "outside_window";
  message: string;
  latest_digest_cutoff: number | null;
  contributions: { signal: string; feature: number; weight: number; contribution: number; has_data: boolean }[];
  raise_it: { signal: string; how: string }[];
}
