import type { Metadata } from "next";
import { Geist } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { LanguageProvider } from "./i18n";
import { SmoothScroll } from "./scroll";

const sans = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = {
  title: "Relay - move a database anywhere, prove every row arrived",
  description:
    "Relay is a desktop app that migrates data between any two databases, then checks every row, column and total on both sides",
};

const LANGUAGE = `(() => {
  try {
    const language = localStorage.getItem("relay.language");
    document.documentElement.lang = language === "fr" || language === "en" ? language : navigator.language.startsWith("fr") ? "fr" : "en";
  } catch {}
})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} scroll-pt-16  motion-reduce:scroll-auto`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: LANGUAGE }} />
      </head>
      <body className="bg-surface font-sans text-ink antialiased">
        <SmoothScroll />
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
