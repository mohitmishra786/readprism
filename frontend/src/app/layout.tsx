import type { Metadata, Viewport } from "next";
import "../styles/globals.css";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://readprism.app";

// Positioning per audit 12-1: retire "Personalized Content Intelligence
// Platform"; lead with the plain, provable value.
const TAGLINE = "The reading app that ranks by how you actually read";
const DESCRIPTION =
  "ReadPrism aggregates every source and creator you follow and orders your daily digest by personal relevance — a behavioral, explainable ranking engine that gets sharper the more you read. Open source and self-hostable.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `ReadPrism — ${TAGLINE}`,
    template: "%s — ReadPrism",
  },
  description: DESCRIPTION,
  applicationName: "ReadPrism",
  keywords: [
    "RSS reader",
    "self-hosted RSS reader",
    "open source Feedly alternative",
    "personalized news aggregator",
    "behavioral content ranking",
    "AI news digest",
    "newsletter aggregator",
  ],
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "ReadPrism" },
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    siteName: "ReadPrism",
    title: `ReadPrism — ${TAGLINE}`,
    description: DESCRIPTION,
    url: SITE_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: `ReadPrism — ${TAGLINE}`,
    description: DESCRIPTION,
  },
  icons: {
    // SVG works for modern browsers. iOS apple-touch-icon requires PNG, so we
    // omit the `apple` key rather than point it at an SVG that iOS can't render
    // (it would fall back to a screenshot, which is fine).
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

// SoftwareApplication structured data for rich results / AI citation (11-7).
const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "ReadPrism",
  applicationCategory: "News aggregator, RSS reader",
  operatingSystem: "Web, self-hostable (Docker)",
  description: DESCRIPTION,
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  url: SITE_URL,
};

export const viewport: Viewport = {
  themeColor: "#2563eb",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@1,400;1,500;1,600&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
