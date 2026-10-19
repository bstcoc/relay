"use client";

import { RelayMark } from "@relay/ui/components/relay-mark";
import { FOCUS } from "../classes";
import { Download } from "../download";
import { LanguageToggle, useLanguage } from "../i18n";

export default function Invite() {
  const { t } = useLanguage();

  return (
    <main className="relative grid min-h-screen place-items-center px-6 py-12">
      <LanguageToggle className="absolute top-6 right-6" />
      <div className="flex w-[min(360px,100%)] flex-col items-center gap-6 text-center">
        <a href="/" aria-label={t.home} className={FOCUS}><RelayMark size={32} /></a>
        <div className="flex flex-col gap-2">
          <h1 className="heading-2">{t.invite.title}</h1>
          <p className="body text-ink-muted">{t.invite.body}</p>
        </div>
        <div className="flex flex-col items-center gap-3">
          <p className="body text-ink-muted">{t.invite.noApp}</p>
          <Download />
        </div>
      </div>
    </main>
  );
}
