import { headers } from "next/headers";
import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Playfair_Display, Source_Serif_4 } from "next/font/google";
import "../styles/globals.css";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";
import { InstallPrompt } from "../components/InstallPrompt";

// Fonts are downloaded at build time and served from this origin (next/font):
// no render-blocking third-party stylesheet, no request to Google per visit.
// Source Serif 4 is the successor of Source Serif Pro.
const sans = Inter({ subsets: ["latin"], variable: "--nf-sans", display: "swap" });
// Only the landing page's families are preloaded; the reader's serif and the
// code font load when a page uses them.
const serif = Source_Serif_4({
  subsets: ["latin"],
  preload: false,
  style: ["normal", "italic"],
  variable: "--nf-serif",
  display: "swap",
});
const display = Playfair_Display({
  subsets: ["latin"],
  style: ["italic"],
  variable: "--nf-display",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--nf-mono",
  display: "swap",
  preload: false,
});

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

// The CSP middleware sets a per-request nonce; the JSON-LD script must carry
// it, or a nonce-based CSP blocks the inline script tag (#187).
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="en"
      className={`${sans.variable} ${serif.variable} ${display.variable} ${mono.variable}`}
    >
      <body>
        <script
          type="application/ld+json"
          nonce={nonce}
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
        <ServiceWorkerRegister />
        <InstallPrompt />
        {children}
      </body>
    </html>
  );
}
