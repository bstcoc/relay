import type { Metadata } from "next";
import { Geist } from "next/font/google";
import type { ReactNode } from "react";
import "@relay/ui/globals.css";
import "./base.css";
import { AccountProvider } from "./account";
import { PreferencesProvider } from "./preferences";

const sans = Geist({ subsets: ["latin"], variable: "--font-geist" });

export const metadata: Metadata = { title: "Relay" };

const PREFERENCES = `(() => {
  try {
    const root = document.documentElement;
    if (navigator.userAgent.includes("Mac OS X")) {
      root.dataset.platform = "mac";
    }
    const language = localStorage.getItem("relay.language");
    const theme = localStorage.getItem("relay.theme");
    root.lang = language === "fr" || language === "en" ? language : navigator.language.startsWith("fr") ? "fr" : "en";
    if (theme === "light" || theme === "dark") {
      root.dataset.theme = theme;
    }
  } catch {}
})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" className={sans.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: PREFERENCES }} />
      </head>
      <body className="bg-surface font-sans text-sm text-foreground antialiased">
        <div data-drag-region
          className="fixed inset-x-0 top-0 z-30 hidden h-7 [[data-platform=mac]_body:not(:has([data-slot=sidebar-wrapper]))_&]:block" />
        <PreferencesProvider>
          <AccountProvider>{children}</AccountProvider>
        </PreferencesProvider>
      </body>
    </html>
  );
}
