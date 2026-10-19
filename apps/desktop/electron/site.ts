import { existsSync, statSync } from "node:fs";
import { extname, join, normalize, sep } from "node:path";

export const ORIGIN = "app://relay";

export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "connect-src 'self' https://wjonadchmlrdiwvtpujf.supabase.co",
  "img-src 'self' data: https://*.googleusercontent.com https://wjonadchmlrdiwvtpujf.supabase.co",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "script-src 'self' 'unsafe-inline'",
].join("; ");

const OPENABLE = [
  { origin: "https://wjonadchmlrdiwvtpujf.supabase.co", path: "/auth/v1/authorize" },
  { origin: "https://supabase.com", path: "/dashboard/account/tokens" },
  { origin: "https://console.neon.tech", path: "/app/settings/api-keys" },
];

export function openable(address: string): boolean {
  let url: URL;
  try {
    url = new URL(address);
  } catch {
    return false;
  }
  if (url.username !== "" || url.password !== "") {
    return false;
  }
  return OPENABLE.some((allowed) => url.origin === allowed.origin && (!allowed.path || url.pathname === allowed.path));
}

export function siteFile(root: string, pathname: string): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  const file = normalize(join(root, decoded));
  if (file !== root && !file.startsWith(root + sep)) {
    return null;
  }
  for (const candidate of [file, join(file, "index.html"), extname(file) === "" ? `${file}.html` : null]) {
    if (candidate && existsSync(candidate) && statSync(candidate).isFile()) {
      return candidate;
    }
  }
  return null;
}

export function originOf(address: string): string | null {
  try {
    const url = new URL(address);
    return `${url.protocol}//${url.host}`;
  } catch {
    return null;
  }
}
