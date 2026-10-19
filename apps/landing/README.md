# @relay/landing

Relay's landing page, in English and French, static (`next build` produces
`out/`).

```sh
bun run --cwd apps/landing dev
```

It follows the `@relay/ui` theme.

## Downloads

The "Download" button points to the latest release of
[`bstcoc/relay`](https://github.com/bstcoc/relay/releases). Relay is free:
the landing sells nothing.

## Publishing a version

Release Please keeps a version PR open on `main`, built from Conventional
Commits. Merging it tags the version, and the `release` workflow builds
macOS (Apple silicon), Windows and Linux and publishes the apps to
that release. Installed apps find it on their next launch.

The app is only ad hoc signed: on first launch, macOS blocks it; the user
allows it in System Settings → Privacy & Security → "Open Anyway".
