import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://readprism.app";

// Audit 11-3: expose a crawlable robots policy. The authenticated app routes are
// user-specific and shouldn't be indexed; the marketing/comparison pages should.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/digest", "/feed", "/sources", "/creators", "/search", "/read", "/preferences", "/api/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
