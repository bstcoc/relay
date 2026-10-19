"use client";

import { createContext, type ReactNode, useCallback, useContext, useLayoutEffect, useState } from "react";
import { ToggleGroup, ToggleGroupItem } from "@relay/ui/components/toggle-group";
import { cn } from "@relay/ui/lib/utils";
import { en, type Words } from "./words/en";
import { fr } from "./words/fr";

type Language = "en" | "fr";

const Context = createContext<{ language: Language; t: Words; setLanguage: (language: Language) => void } | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");

  useLayoutEffect(() => {
    setLanguageState(document.documentElement.lang === "fr" ? "fr" : "en");
  }, []);

  const setLanguage = useCallback((next: Language) => {
    document.documentElement.lang = next;
    localStorage.setItem("relay.language", next);
    setLanguageState(next);
  }, []);

  return <Context value={{ language, t: language === "fr" ? fr : en, setLanguage }}>{children}</Context>;
}

export function useLanguage() {
  const value = useContext(Context);
  if (!value) {
    throw new Error("useLanguage needs a LanguageProvider");
  }
  return value;
}

export function LanguageToggle({ className }: { className?: string }) {
  const { language, t, setLanguage } = useLanguage();
  return (
    <ToggleGroup type="single" spacing={1} aria-label={t.language} value={language}
      onValueChange={(value) => value && setLanguage(value as Language)}
      className={cn("gap-0 self-center rounded-full border border-border p-0.5", className)}>
      {(["fr", "en"] as const).map((value) => (
        <ToggleGroupItem key={value} value={value}
          className="caption h-6 min-w-7 rounded-full px-1 text-ink-muted hover:bg-transparent hover:text-ink data-[state=on]:bg-muted data-[state=on]:text-ink">
          {value.toUpperCase()}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
