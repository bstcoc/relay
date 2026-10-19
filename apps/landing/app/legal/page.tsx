import type { Metadata } from "next";
import { Notice } from "./notice";

export const metadata: Metadata = { title: "Relay: legal notice" };

export default function Legal() {
  return <Notice />;
}
