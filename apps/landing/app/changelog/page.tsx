import type { Metadata } from "next";
import { type Release, Changelog } from "./changelog";

export const metadata: Metadata = { title: "Relay: changelog" };

const INSTALLER = /\.(dmg|exe|AppImage)$/;

const RELEASES = "https://api.github.com/repos/bstcoc/relay/releases?per_page=100";

const NEXT = /<([^>]+)>;\s*rel="next"/;

async function allReleases() {
  const releases: Release[] = [];
  let url: string | undefined = RELEASES;
  while (url) {
    const response: Response = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
    if (!response.ok) {
      throw new Error(`GitHub releases answered ${response.status}`);
    }
    releases.push(...await response.json() as Release[]);
    url = NEXT.exec(response.headers.get("link") ?? "")?.[1];
  }
  return releases;
}

export default async function ChangelogPage() {
  const releases = await allReleases();
  const shown = releases.filter((release) => !release.draft).map((release) => ({
    ...release, assets: release.assets.filter((asset) => INSTALLER.test(asset.name)),
  }));
  return <Changelog releases={shown} />;
}
