"use client";

import { cn } from "@relay/ui/lib/utils";
import { Download } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { LINK, SMALL } from "../classes";
import { Document } from "../document";
import { useLanguage } from "../i18n";

export type Release = {
  tag_name: string;
  html_url: string;
  published_at: string;
  draft: boolean;
  body: string | null;
  assets: { name: string; size: number; browser_download_url: string }[];
};

function inline(text: string) {
  return text.split(/(`[^`]+`)/).map((part, index) => part.startsWith("`") && part.endsWith("`")
    ? <span key={index} className="rounded-sm bg-surface-muted px-1 text-ink">{part.slice(1, -1)}</span>
    : <Fragment key={index}>{part}</Fragment>);
}

function Notes({ body }: { body: string }) {
  const blocks: ReactNode[] = [];
  for (const block of body.split(/\n\s*\n/)) {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    if (lines.every((line) => line.startsWith("- ") || line.startsWith("* "))) {
      blocks.push(
        <ul key={blocks.length} className="flex flex-col gap-1.5">
          {lines.map((line) => (
            <li key={line} className="flex gap-2 before:mt-2.5 before:size-1 before:flex-none before:rounded-full before:bg-border-strong">
              <span>{inline(line.slice(2))}</span>
            </li>
          ))}
        </ul>,
      );
    } else {
      blocks.push(<p key={blocks.length}>{inline(lines.join(" ").replace(/^#+\s*/, ""))}</p>);
    }
  }
  return <div className="flex flex-col gap-3 text-ink-muted">{blocks}</div>;
}

function megabytes(size: number) {
  return `${(size / 1_048_576).toFixed(0)} MB`;
}

export function Changelog({ releases }: { releases: Release[] }) {
  const { t, language } = useLanguage();
  const words = t.changelog;
  return (
    <Document title={words.title} lead={words.lead}>
      <ol className="mt-8 flex flex-col">
        {releases.map((release, index) => (
          <li key={release.tag_name} className="grid grid-cols-[140px_minmax(0,1fr)] gap-8 border-t border-border py-8 max-[760px]:grid-cols-1 max-[760px]:gap-3">
            <div className="flex flex-col gap-1">
              <a href={release.html_url} className={cn(LINK, "text-base font-semibold text-ink")}>{release.tag_name.replace(/^v/, "")}</a>
              <time dateTime={release.published_at} className={cn(SMALL, "text-ink-muted")}>
                {new Date(release.published_at).toLocaleDateString(language === "fr" ? "fr-FR" : "en-GB", { day: "numeric", month: "long", year: "numeric" })}
              </time>
              {index === 0 && <span className={cn(SMALL, "mt-1 inline-flex items-center gap-2 before:size-2 before:rounded-full before:bg-status-verified")}>{words.latest}</span>}
            </div>
            <div className="flex flex-col gap-5">
              {release.body ? <Notes body={release.body} /> : <p className="text-ink-muted">{words.none}</p>}
              {release.assets.length > 0 && (
                <ul className="flex flex-col overflow-hidden rounded-lg border border-border bg-background">
                  {release.assets.map((asset) => (
                    <li key={asset.name} className="border-b border-border last:border-b-0">
                      <a href={asset.browser_download_url} download
                        className="flex items-center justify-between gap-4 px-4 py-3 text-sm transition-colors duration-150 hover:bg-surface motion-reduce:transition-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring">
                        <span className="truncate">{asset.name}</span>
                        <span className={cn(SMALL, "flex flex-none items-center gap-2 text-ink-muted tabular-nums")}>
                          {megabytes(asset.size)}
                          <Download className="size-3.5" aria-hidden="true" />
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Document>
  );
}
