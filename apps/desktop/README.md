# @relay/desktop

Relay's desktop app, the main interface of the product. The user connects
their databases, sees their infrastructure, validates column mappings and
runs migrations.

Electron around a web interface, which calls the engine through a local
service started with it and reached over stdin and stdout, with no network
port. It runs inside the company network: it reaches internal databases, and
credentials stay in the system keychain.

Next.js 16 as a static export, on `@relay/ui`, in an Electron window served
over the `app://` protocol. The main process, in TypeScript (`electron/`),
starts the service on the first call and stops it with the app. The page has
no access to Node: it goes through `window.relay`.

## Connections

The user adds databases (PostgreSQL, Supabase, SQL Server, MySQL, SQLite)
and files (CSV, Parquet), with an environment (production, staging, test,
development), and tests them: a database lists its tables, a file its
columns.

- Connections are described in `connections.json`, in the app's data
  folder; **no password is ever written there**.
- The password goes to the system keychain (macOS Keychain, Windows
  Credential Manager, Secret Service on Linux). It never comes back to the
  interface: only the main process reads it, to build the URL it sends to
  the engine.
- Every field accepts an environment variable (`${DB_PASSWORD}`), read when
  connecting.

## Develop

Requirements: Bun, uv. From the repository root, once: `bun install`. Then,
from `apps/desktop/`:

```sh
bun run app          # the app; the interface reloads on every change
bun run package      # .dmg (macOS), .exe (Windows), .deb / .AppImage (Linux)
bun run typecheck
bun test
```

A change in `electron/` needs `bun run app` to be restarted.

In development only, the app starts the repository's engine with
`uv run relay-service` (`RELAY_ENGINE` points to another engine folder). A
production build never looks for a program in the `PATH` or a folder given
by the environment: the engine that receives database credentials must be
the one shipped with the app. Until it is shipped, the app says the engine
is not bundled.
