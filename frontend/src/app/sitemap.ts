import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://readprism.app";

// Audit 11-3: sitemap of the public, indexable marketing/comparison routes.
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const routes = [
    "",
    "/how-it-works",
    "/waitlist",
    "/vs/feedly",
    "/vs/inoreader",
    "/vs/newsblur",
  ];
  return routes.map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified: now,
    changeFrequency: "monthly",
    priority: path === "" ? 1 : 0.7,
  }));
}
