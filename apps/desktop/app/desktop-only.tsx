"use client";

import { Button } from "@relay/ui/components/button";
import { type ReactNode, useSyncExternalStore } from "react";
import { CenteredCard } from "./components/ui";
import { isDesktop } from "./desktop";
import { usePreferences } from "./preferences";

const RELEASES = "https://github.com/bstcoc/relay/releases/latest";

const unchanging = () => () => undefined;

export function DesktopOnly({ children }: { children: ReactNode }) {
  const { t } = usePreferences();
  const desktop = useSyncExternalStore(unchanging, isDesktop, () => null);
  if (desktop === null) {
    return null;
  }
  if (!desktop) {
    return (
      <CenteredCard title={t.desktopOnly.title} body={t.desktopOnly.body}>
        <Button asChild><a href={RELEASES}>{t.desktopOnly.download}</a></Button>
      </CenteredCard>
    );
  }
  return children;
}
