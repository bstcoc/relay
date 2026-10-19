"use client";

import type { ReactNode } from "react";
import { Shell } from "../shell";

export default function AppLayout({ children }: { children: ReactNode }) {
  return <Shell>{children}</Shell>;
}
