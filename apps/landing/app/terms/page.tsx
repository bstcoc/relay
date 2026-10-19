import type { Metadata } from "next";
import { Terms } from "../legal/notice";

export const metadata: Metadata = { title: "Relay: terms of service" };

export default function TermsPage() {
  return <Terms />;
}
