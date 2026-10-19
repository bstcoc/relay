"use client";

import { Button } from "@relay/ui/components/button";
import { cn } from "@relay/ui/lib/utils";
import { Download, LoaderCircle, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";
import { invoke, isDesktop, onUpdate, type UpdateState } from "../desktop";
import { usePreferences } from "../preferences";

function useUpdate() {
  const [state, setState] = useState<UpdateState | null>(null);
  useEffect(() => {
    if (!isDesktop()) {
      return;
    }
    void invoke<UpdateState>("update_state").then(setState, () => undefined);
    return onUpdate(setState);
  }, []);
  return state;
}

export function UpdateButton() {
  const { t } = usePreferences();
  const update = useUpdate();
  if (!update?.version || update.status === "idle") {
    return null;
  }
  const { status, version } = update;
  const label = status === "ready" ? t.update.restart(version)
    : status === "downloading" ? t.update.downloading(version, update.percent ?? 0)
    : t.update.download(version);
  const run = () => void invoke(status === "ready" ? "update_install" : "update_download").catch(() => undefined);
  return (
    <Button type="button" variant="ghost" size="icon-sm" aria-label={label} title={label}
      disabled={status === "downloading"} onClick={run}
      className="relative size-7 shrink-0 text-muted-foreground hover:text-foreground">
      {status === "downloading" ? <LoaderCircle className="animate-spin motion-reduce:animate-none" />
        : status === "ready" ? <RotateCw /> : <Download />}
      <span aria-hidden="true" className={cn("absolute top-1 right-1 size-1.5 rounded-full bg-action",
        status === "downloading" && "hidden")} />
    </Button>
  );
}
