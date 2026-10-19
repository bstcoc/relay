import type { Metadata } from "next";
import { Privacy } from "../legal/notice";

export const metadata: Metadata = { title: "Relay: privacy policy" };

export default function PrivacyPage() {
  return <Privacy />;
}
