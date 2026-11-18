"use client";

import { Button } from "@relay/ui/components/button";
import { RelayMark } from "@relay/ui/components/relay-mark";
import { cn } from "@relay/ui/lib/utils";
import { useEffect, useState } from "react";
import { BRAND, FRAME, LINK } from "./classes";
import { Download } from "./download";
import { LanguageToggle, useLanguage } from "./i18n";
import { CONTACT } from "./words";

export const NAV_LINKS = ["#connect", "#map", "#proof", "#faq"];

export const HERO_ACTIONS = "hero-actions";

export function Nav() {
  const { t } = useLanguage();
  const [scrolled, setScrolled] = useState(false);
  const [heroActionsVisible, setHeroActionsVisible] = useState(true);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  useEffect(() => {
    const heroActions = document.getElementById(HERO_ACTIONS);
    if (!heroActions) return;
    const observer = new IntersectionObserver(([entry]) => setHeroActionsVisible(entry?.isIntersecting ?? false));
    observer.observe(heroActions);
    return () => observer.disconnect();
  }, []);

  return (
    <header data-scrolled={scrolled}
      className="sticky top-0 z-10 transition-[background-color,box-shadow] duration-200 motion-reduce:transition-none data-[scrolled=true]:bg-surface/82 data-[scrolled=true]:shadow-[0_1px_0_var(--border)] data-[scrolled=true]:backdrop-blur-[20px] data-[scrolled=true]:backdrop-saturate-[1.8]">
      <div className={cn(FRAME, "flex h-16 items-center gap-8")}>
        <a href="#top" className={cn(BRAND, "text-lg tracking-[-0.02em]")} aria-label={t.backToTop}>
          <RelayMark size={22} />
          <span>Relay</span>
        </a>
        <nav aria-label={t.nav.sections} className="flex gap-6 max-[1100px]:hidden">
          {NAV_LINKS.map((href, index) => (
            <a key={href} href={href} className={LINK}>{t.nav.links[index]}</a>
          ))}
        </nav>
        <div className="ml-auto flex gap-2">
          <LanguageToggle />
          <Button asChild variant="outline" className="max-[760px]:hidden">
            <a href={CONTACT}>{t.nav.contact}</a>
          </Button>
          <span className={heroActionsVisible ? "hidden" : "contents"} >
            <Download align="end" />
          </span>
        </div>
      </div>
    </header>
  );
}
