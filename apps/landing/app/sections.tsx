"use client";

import { RelayMark } from "@relay/ui/components/relay-mark";
import { cn } from "@relay/ui/lib/utils";
import { Plus } from "lucide-react";
import type { CSSProperties } from "react";
import { BRAND, FOCUS, FRAME, LEAD, LINK, SECTION_GAP, SECTION_TITLE, SMALL } from "./classes";
import { BUILDS, RELEASES } from "./download";
import { useLanguage } from "./i18n";
import { NAV_LINKS } from "./nav";
import { CONTACT, REPOSITORY } from "./words";

const UNDERLINE = "font-medium underline decoration-border-strong underline-offset-4 transition-[text-decoration-color] duration-150 hover:decoration-ink motion-reduce:transition-none";

export function Faq() {
  const { t } = useLanguage();
  const words = t.faq;
  return (
    <section id="faq" className={cn(FRAME, SECTION_GAP, "grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-16 max-[1100px]:grid-cols-1 max-[1100px]:gap-10")}>
      <div className="flex flex-col gap-4">
        <h2 className={SECTION_TITLE}>{words.title}</h2>
        <p className={LEAD}>{words.lead}</p>
        <p className="mt-4 text-ink-muted">
          {words.more} <a href={CONTACT} className={cn(UNDERLINE, FOCUS, "text-ink")}>{words.write}</a>
        </p>
      </div>
      <div className="border-t border-border">
        {words.items.map((item) => (
          <details key={item.question} name="faq" className="faq group border-b border-border">
            <summary className={cn(FOCUS, "flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-[17px] font-medium [&::-webkit-details-marker]:hidden")}>
              {item.question}
              <Plus className="size-4 flex-none text-ink-muted transition-transform duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] group-open:rotate-45 motion-reduce:transition-none" aria-hidden="true" />
            </summary>
            <p className="max-w-[60ch] pb-6 leading-[1.6] text-ink-muted">{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export function Footer() {
  const { t } = useLanguage();
  const words = t.footer;
  const columns = [
    { title: words.product, links: NAV_LINKS.map((href, index) => [t.nav.links[index]!, href]) },
    { title: words.databases, links: words.databaseItems.map((item) => [item, null]) },
    { title: words.download, links: BUILDS.flatMap((file, index) => file ? [[t.download.builds[index]!, `${RELEASES}/${file}`]] : []) },
    { title: words.company, links: [[words.source, REPOSITORY], [words.license, `${REPOSITORY}/blob/main/LICENSE`], [words.changelog, "/changelog/"], [words.contact, CONTACT], [words.terms, "/terms/"], [words.privacy, "/privacy/"], [words.legal, "/legal/"]] },
  ];
  return (
    <footer className="footer relative mt-[clamp(120px,11vw,220px)] overflow-hidden border-t border-border bg-background">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 h-[420px] bg-[radial-gradient(ellipse_at_bottom,color-mix(in_oklab,var(--verified)_14%,transparent),transparent_70%)]" />
      <div className={cn(FRAME, "relative flex justify-between gap-16 pt-16 pb-[clamp(160px,17vw,320px)] max-[1100px]:flex-col max-[1100px]:gap-12")}>
        <div className="footer-rise flex max-w-sm flex-col items-start">
          <a href="#top" className={cn(BRAND, "text-lg tracking-[-0.02em]")} aria-label={t.backToTop}>
            <RelayMark size={22} /> Relay
          </a>
          <p className="mt-5 text-[clamp(22px,1.6vw,28px)] leading-tight font-semibold tracking-[-0.02em] text-balance">{words.tagline}</p>
          <span className={cn(SMALL, "mt-5 inline-flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1.5 text-ink-muted")}>
            <span className="size-2 rounded-full bg-status-verified" />
            {words.local}
          </span>
        </div>
        <div className="grid grid-cols-4 gap-x-12 gap-y-10 max-[760px]:grid-cols-2">
          {columns.map((column, index) => (
            <nav key={column.title} aria-label={column.title} style={{ "--index": index + 1 } as CSSProperties} className="footer-rise">
              <span className={cn(SMALL, "font-medium text-ink-muted")}>{column.title}</span>
              <ul className="mt-5 flex flex-col gap-3">
                {column.links.map(([label, href]) => (
                  <li key={label}>
                    {href ? <a href={href} className={LINK}>{label}</a> : <span className="text-[14px] text-ink-muted">{label}</span>}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
      </div>
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center overflow-hidden select-none">
        <span className="footer-word translate-y-[30%] bg-linear-to-b from-ink/10 to-verified/14 bg-clip-text px-[0.1em] text-[26vw] leading-none font-semibold tracking-[-0.06em] text-transparent mask-[linear-gradient(to_bottom,black,transparent_85%)]">
          Relay
        </span>
      </div>
      <p className={cn(FRAME, SMALL, "relative py-6 text-center text-ink-muted")}>© 2026 Relay</p>
    </footer>
  );
}
