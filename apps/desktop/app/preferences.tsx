"use client";

import { createContext, type ReactNode, useCallback, useContext, useLayoutEffect, useState } from "react";
import { en } from "./words/en";
import { fr, type Words } from "./words/fr";

export type Language = "fr" | "en";
export type Theme = "system" | "light" | "dark";

type Preferences = {
  language: Language;
  theme: Theme;
  t: Words;
  setLanguage: (language: Language) => void;
  setTheme: (theme: Theme) => void;
};

const Context = createContext<Preferences | null>(null);

function stored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  const value = localStorage.getItem(key);
  return allowed.includes(value as T) ? (value as T) : fallback;
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("fr");
  const [theme, setThemeState] = useState<Theme>("system");

  useLayoutEffect(() => {
    setLanguageState(document.documentElement.lang === "en" ? "en" : "fr");
    setThemeState(stored("relay.theme", ["system", "light", "dark"] as const, "system"));
  }, []);

  const setLanguage = useCallback((next: Language) => {
    document.documentElement.lang = next;
    localStorage.setItem("relay.language", next);
    setLanguageState(next);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    const root = document.documentElement;
    if (next === "system") {
      delete root.dataset.theme;
    } else {
      root.dataset.theme = next;
    }
    localStorage.setItem("relay.theme", next);
    setThemeState(next);
  }, []);

  return (
    <Context value={{ language, theme, t: language === "fr" ? fr : en, setLanguage, setTheme }}>
      {children}
    </Context>
  );
}

export function usePreferences() {
  const preferences = useContext(Context);
  if (!preferences) {
    throw new Error("usePreferences needs a PreferencesProvider");
  }
  return preferences;
}
