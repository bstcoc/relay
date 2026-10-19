# App icon layers for Icon Composer

Three 1024 × 1024 px layers, assembled in Apple's Icon Composer for the
macOS 26 icon:

- `background.svg`: the graphite background, full frame. Icon Composer
  applies the rounded shape itself: do not round the background.
- `half-top-left.svg` and `half-bottom-right.svg`: the two halves of the
  mark, in white, each on its own layer so it gets its own depth. The mark
  covers 45% of the side.

## Steps

1. Open Icon Composer, create an icon, drop `background.svg` as the
   background, then both halves in one group above it.
2. Scale the mark group to 130%, then tune the Liquid Glass rendering
   (highlights, depth, shadow) and check the light, dark and tinted
   variants.
3. Save the `.icon` file in this folder, then export a 1024 px image
   (`relay-app-icon-1024.png`).

The exported image fills the whole frame; Dock icons follow Apple's grid,
824 px centered in a 1024 frame. It is therefore shrunk into
`../relay-app-icon-macos.png`, which generates the app icons for macOS,
Windows and Linux:

```sh
bunx electron-icon-builder --input=relay-brand/logos/relay-app-icon-macos.png --output=/tmp/relay-icons --flatten
cp /tmp/relay-icons/icons/icon.icns /tmp/relay-icons/icons/icon.ico apps/desktop/build/
cp /tmp/relay-icons/icons/1024x1024.png apps/desktop/build/icon.png
```

Only `icon.png`, `icon.icns` and `icon.ico` are used: `electron-builder`
reads them from `apps/desktop/build/`. Neither the mark's paths, nor its
proportions, nor its color change: only the icon's rendering varies by
system.
