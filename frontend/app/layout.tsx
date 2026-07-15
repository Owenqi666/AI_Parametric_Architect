import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AI Parametric Architect Studio",
    template: "%s — AI Parametric Architect Studio",
  },
  description: "A safe, constraint-aware world-model planning environment for architectural AI.",
  openGraph: {
    title: "AI Parametric Architect Studio",
    description: "Natural-language intent, detached constraint planning, reproducible benchmarks, and an authoritative read-only World Model.",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light",
  themeColor: "#171c1d",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
