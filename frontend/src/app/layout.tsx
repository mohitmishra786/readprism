import type { Metadata, Viewport } from "next";
import "../styles/globals.css";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";

export const metadata: Metadata = {
  title: "ReadPrism — Personalized Content Intelligence",
  description:
    "Aggregate every source and creator you follow, ranked by personal relevance. A daily digest with exactly what you need to read, in the right order, for you.",
  applicationName: "ReadPrism",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "ReadPrism" },
  icons: {
    // SVG works for modern browsers. iOS apple-touch-icon requires PNG, so we
    // omit the `apple` key rather than point it at an SVG that iOS can't render
    // (it would fall back to a screenshot, which is fine).
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
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
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
