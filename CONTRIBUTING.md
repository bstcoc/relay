# Contributing

Thanks for helping. Bug reports, ideas and pull requests are welcome.

## Setup

Install [Bun](https://bun.sh) and [uv](https://docs.astral.sh/uv/), then:

```sh
bun install                 # from the repository root
cd engine && uv sync --all-extras
```

Run the desktop app with `bun run desktop` from the root.

## Before opening a pull request

From `engine/`:

```sh
uv run pytest && uv run ruff check . && uv run ty check
```

If you change the data generator or a check, also run
`uv run python scripts/oracle_scan.py`. For the apps, run
`bun run typecheck` and `bun test` in the app you touched.

A Ruff or ty rule that blocks you is fixed in the code, not disabled.

## Rules worth knowing

- Amounts are decimals, never floats; business identifiers are strings.
- Database drivers live in their adapter, never in the engine core.
- No comments in code: names say what code does, the commit message or PR
  says why.
- Never commit datasets (`data/` is ignored) or credentials.
- Everything is in English, except the app's localized UI strings.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/), in English
  (`feat:`, `fix:`, `docs:`…).
- One pull request per change, against `main`, with a short description and
  a test plan.

By contributing, you agree your work is licensed under the
[Apache License 2.0](LICENSE).
