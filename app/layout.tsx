import type { Metadata } from "next";
import { Poppins, JetBrains_Mono } from "next/font/google";
import { HUB } from "@/lib/site";
import "./globals.css";

// The site's single face: a bold geometric grotesque (the editorial reference's
// Campton stand-in). Headings lean on 600/700; body runs at 400.
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-poppins",
  display: "swap",
});
// Mono is reserved for real code (the guide's snippets) — never for chrome.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

// Root layout owns <html>/<body>/fonts and the hub-level title scope. It does
// NOT render any header/footer: the hub page ("/") supplies its own chrome, and
// the dashboard section (app/qdashboards/layout.tsx) supplies the plugin chrome.
export const metadata: Metadata = {
  title: {
    default: `${HUB.name} — ${HUB.tagline}`,
    template: `%s · ${HUB.name}`,
  },
  description:
    "A growing collection of free, open-source QGIS plugins from byZenterra.org — a DTI-registered GIS consultancy in the Philippines owned by Isaac Enage. Practical tools that extend the desktop GIS you already use.",
  metadataBase: new URL(`https://${HUB.domain}`),
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${poppins.variable} ${jetbrainsMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
