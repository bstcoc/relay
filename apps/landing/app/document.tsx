"use client";

import { RelayMark } from "@relay/ui/components/relay-mark";
import type { ReactNode } from "react";
import { BRAND } from "./classes";
import { useLanguage } from "./i18n";

export type Section = { heading: string; paragraphs: readonly string[] };

export function Document({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  const { t } = useLanguage();
  return (
    <main className="mx-auto flex max-w-[calc(72ch+48px)] flex-col gap-4 px-6 py-16 max-[760px]:px-4">
      <a href="/" className={`${BRAND} self-start`} aria-label={t.home}><RelayMark size={20} /> Relay</a>
      <h1 className="heading-1 mt-8">{title}</h1>
      {lead && <p className="body text-ink-muted">{lead}</p>}
      {children}
    </main>
  );
}

export function Sections({ sections }: { sections: readonly Section[] }) {
  return sections.map((section) => (
    <section key={section.heading} className="flex flex-col gap-3">
      <h2 className="heading-3 mt-6">{section.heading}</h2>
      {section.paragraphs.map((paragraph) => <p key={paragraph} className="body text-ink-muted">{paragraph}</p>)}
    </section>
  ));
}
