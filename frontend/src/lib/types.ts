export interface User {
  id: string;
  email: string;
  display_name: string | null;
  onboarding_complete: boolean;
  digest_frequency: string;
  digest_time_morning: string;
  digest_max_items: number;
  serendipity_percentage: number;
  tier: string;
  timezone: string;
  created_at: string;
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
  fetch_error_count: number;
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
}

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
  created_at: string;
}

export interface DigestItem {
  id: string;
  digest_id: string;
  content_item_id: string;
  position: number;
  section: string;
  prs_score: number;
  signal_breakdown: Record<string, number>;
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
  signal_breakdown: Record<string, number>;
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
  access_token: string;
  token_type: string;
  expires_in: number;
}
