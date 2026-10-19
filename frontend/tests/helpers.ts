import type { ContentItem, ContentItemFull } from "../src/lib/types";

export function makeItem(over: Partial<ContentItemFull> = {}): ContentItemFull {
  return {
    id: "item-1",
    source_id: "src-1",
    creator_platform_id: null,
    url: "https://www.example.com/post",
    title: "How compilers lower loops",
    author: "Ada",
    published_at: "2026-10-19T08:00:00Z",
    fetched_at: "2026-10-19T09:00:00Z",
    summary_headline: null,
    summary_brief: "A brief summary.",
    summary_detailed: "A detailed takeaway.",
    reading_time_minutes: 6,
    content_depth_score: 0.7,
    word_count: 1200,
    has_citations: true,
    is_original_reporting: true,
    topic_clusters: ["compilers"],
    summarization_cached: true,
    summary_source: "llm",
    paywalled: false,
    page_type: "article",
    language: "en",
    created_at: "2026-10-19T09:00:00Z",
    full_text: null,
    ...over,
  } as ContentItemFull;
}

export type { ContentItem };
