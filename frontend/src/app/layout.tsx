import type { Metadata, Viewport } from "next";
import "../styles/globals.css";
import { ServiceWorkerRegister } from "../components/ServiceWorkerRegister";

export const metadata: Metadata = {
  title: "ReadPrism — Personalized Content Intelligence",
  description:
    "Aggregate every source and creator you follow, ranked by personal relevance. A daily digest with exactly what you need to read, in the right order, for you.",
  applicationName: "ReadPrism",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "ReadPrism",
  },
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#1d4ed8",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ServiceWorkerRegister />
        {children}
      </body>
    </html>
  );
}
