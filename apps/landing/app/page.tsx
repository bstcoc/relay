"use client";

import type { CSSProperties, ReactNode } from "react";
import { Button } from "@relay/ui/components/button";
import { cn } from "@relay/ui/lib/utils";
import { ArrowRight } from "lucide-react";
import { AppWindow, ConnectionCards, MapScreen, OverviewScreen, ReportScreen, type Screen } from "./app-window";
import { FRAME, LEAD, SECTION_GAP, SECTION_TITLE, SMALL } from "./classes";
import { Download } from "./download";
import { Mapping } from "./fragments";
import { useLanguage } from "./i18n";
import { HERO_ACTIONS, Nav } from "./nav";
import { type Engine, LogoMarquee } from "./marquee";
import { Faq, Footer } from "./sections";
import { REPOSITORY } from "./words";

const ENGINES: Engine[] = [
  { name: "PostgreSQL", logo: "/logos/postgresql.svg" },
  { name: "Supabase", logo: "/logos/supabase.svg" },
  { name: "SQL Server", logo: "/logos/sqlserver.svg" },
  { name: "CSV" },
  { name: "MySQL", logo: "/logos/mysql.svg" },
  { name: "SQLite", logo: "/logos/sqlite.svg" },
  { name: "Parquet", logo: "/logos/parquet.svg" },
  { name: "Neon", logo: "/logos/neon.svg" },
];

function Actions({ id, label, className }: { id?: string; label: string; className?: string }) {
  return (
    <div id={id} className={cn("flex flex-wrap gap-3", className)}>
      <Download />
      <Button asChild variant="outline"><a href={REPOSITORY}>{label}</a></Button>
    </div>
  );
}

function Feature({ id, title, line, list, flip = false, tall = false, screen, heading, children }: {
  id: string;
  title: string;
  line: ReactNode;
  list: { title: string; items: readonly string[] };
  flip?: boolean;
  tall?: boolean;
  screen: Screen;
  heading: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className={cn(FRAME, SECTION_GAP, "flex flex-col gap-12")}>
      <h2 className={cn(SECTION_TITLE, flip && "ml-[calc(100%/3)] max-[1100px]:ml-0")}>{title}</h2>
      <div className={cn("grid items-center gap-16 max-[1100px]:grid-cols-1",
        flip ? "grid-cols-[minmax(0,1fr)_minmax(0,2fr)]" : "grid-cols-[minmax(0,2fr)_minmax(0,1fr)]")}>
        <div className={cn("reveal", flip && "order-2 max-[1100px]:order-none")}>
          <AppWindow active={screen} title={heading} className={cn(tall ? "max-h-[760px] max-[760px]:max-h-[640px]" : "max-h-[560px] max-[760px]:max-h-[620px]")}>
            {children}
          </AppWindow>
        </div>
        <aside className="flex max-w-[22em] flex-col gap-8">
          <p className="text-[clamp(19px,1.35vw,26px)] leading-[1.38] tracking-[-0.02em] text-ink-muted *:text-ink">{line}</p>
          <div className="flex flex-col gap-2 text-sm/6">
            <span className="text-ink-muted">{list.title}</span>
            <ul className="flex flex-col gap-2 font-medium">
              {list.items.map((item) => (
                <li key={item} className="flex items-center gap-2 before:size-1 before:rounded-full before:bg-border-strong">{item}</li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </section>
  );
}

function MigrationTitle({ from, to }: { from: string; to: string }) {
  return <>{from}<ArrowRight className="size-3.5 flex-none text-ink-muted" aria-hidden="true" />{to}</>;
}

export default function Landing() {
  const { t } = useLanguage();
  const { connect, map, proof } = t.features;
  return (
    <>
      <Nav />
      <main id="top">
        <section className={cn(FRAME, "flex flex-col items-center pt-[clamp(40px,4.5vw,88px)] text-center")}>
          <div className="flex animate-rise flex-col items-center gap-6 motion-reduce:animate-none">
            <h1 className="flex flex-col text-[clamp(44px,4.4vw,88px)] leading-[0.98] font-semibold tracking-[-0.04em] text-balance">
              {t.hero.title.map((line, index) => <span key={line} className={index === 1 ? "text-ink-muted" : undefined}>{line}</span>)}
            </h1>
            <p className={cn(LEAD, "max-w-[30em]")}>{t.hero.lead}</p>
            <Actions id={HERO_ACTIONS} label={t.hero.source} className="mt-2 justify-center" />
            <span className={cn(SMALL, "text-ink-muted")}>{t.hero.note}</span>
          </div>
          <div className="mt-[clamp(40px,3.5vw,64px)] w-full animate-rise [animation-delay:200ms] motion-reduce:animate-none">
            <div className="hero-tilt">
              <AppWindow active="overview" title={t.app.nav[0]} className="h-[clamp(560px,46vw,760px)]">
                <OverviewScreen />
              </AppWindow>
            </div>
          </div>
        </section>

        <section className={cn(FRAME, "flex flex-col items-center gap-8 pt-16")} aria-label={t.hero.engines}>
          <p className={cn(SMALL, "font-medium text-ink-muted")}>{t.capabilities.label}</p>
          <LogoMarquee engines={ENGINES} />
        </section>

        <Feature id="connect" title={connect.title} line={<><span>{connect.lead}</span>{connect.line}</>} list={connect.list}
          screen="connections" heading={t.app.nav[1]}>
          <ConnectionCards />
        </Feature>

        <Feature id="map" flip tall title={map.title} line={<><span>{map.lead}</span>{map.line}</>} list={map.list}
          screen="map" heading={t.app.nav[2]}>
          <div className="flex flex-col gap-6">
            <MapScreen />
            <Mapping />
          </div>
        </Feature>

        <Feature id="proof" title={proof.title} line={<><span>{proof.lead}</span>{proof.line}</>} list={proof.list}
          screen="migrations" heading={<MigrationTitle from="Customer platform" to="Customer platform v2" />}>
          <ReportScreen />
        </Feature>

        <section id="security" className={cn(FRAME, SECTION_GAP, "flex flex-col gap-12")}>
          <h2 className={SECTION_TITLE}>{t.planes.title}</h2>
          <div className="reveal grid grid-cols-2 overflow-clip rounded-xl border border-border bg-background max-[760px]:grid-cols-1">
            {[t.planes.local, t.planes.relay].map((plane, index) => (
              <div key={plane.title} className={cn("p-8 max-[760px]:p-6", index === 0 ? "border-r border-border max-[760px]:border-r-0 max-[760px]:border-b" : "bg-surface")}>
                <h3 className={cn("mb-4 flex items-center gap-3 text-xl font-semibold tracking-[-0.02em] before:size-2 before:rounded-full",
                  index === 0 ? "before:bg-status-verified" : "before:bg-action")}>
                  {plane.title}
                </h3>
                <ul>
                  {plane.items.map((item, position) => (
                    <li key={item} style={{ "--index": position } as CSSProperties}
                      className="stagger border-t border-border py-3 text-ink-muted">{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>


        <Faq />

        <section className={cn(FRAME, SECTION_GAP, "flex flex-col items-center gap-8 text-center")}>
          <h2 className="text-[clamp(36px,3.2vw,64px)] leading-none font-semibold tracking-[-0.035em]">{t.closing.title}</h2>
          <p className={LEAD}>{t.closing.lead}</p>
          <Actions label={t.closing.source} className="justify-center" />
        </section>
      </main>
      <Footer />
    </>
  );
}
