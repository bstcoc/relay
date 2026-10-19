"use client";

import { Button } from "@relay/ui/components/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@relay/ui/components/dropdown-menu";
import { ChevronDown } from "lucide-react";
import { useLanguage } from "./i18n";
import { SMALL } from "./classes";

export const RELEASES = "https://github.com/bstcoc/relay/releases/latest/download";

export const BUILDS = ["Relay-macOS-AppleSilicon.dmg", null, "Relay-Windows.exe", "Relay-Linux.AppImage"];

const ITEM = "justify-between gap-4 rounded-lg px-3 py-2 leading-6 font-medium whitespace-nowrap";

export function Download({ align = "start" }: { align?: "start" | "end" }) {
  const { t } = useLanguage();
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button className="gap-2">
          {t.download.button} <ChevronDown className="size-3.5" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} sideOffset={8} className="min-w-[260px] border-0">
        {BUILDS.map((file, index) => file ? (
          <DropdownMenuItem key={index} asChild className={ITEM}>
            <a href={`${RELEASES}/${file}`} download>
              <span>{t.download.builds[index]}</span>
              <span className={`${SMALL} text-ink-muted`}>{file.slice(file.lastIndexOf("."))}</span>
            </a>
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem key={index} disabled className={`${ITEM} text-ink-muted data-[disabled]:opacity-100`}>
            <span>{t.download.builds[index]}</span>
            <span className={SMALL}>{t.download.soon}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
