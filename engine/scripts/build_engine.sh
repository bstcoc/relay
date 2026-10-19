#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync --quiet --all-extras --group build
uv run --all-extras --group build python -m nuitka \
  --mode=standalone \
  --output-dir=dist \
  --include-package=relay_engine \
  --include-package-data=relay_engine \
  --include-package=sqlalchemy.dialects \
  --include-package=psycopg \
  --include-package=psycopg_binary \
  --include-package=pymssql \
  --include-package=pymysql \
  --include-package=paramiko \
  --include-package=connectorx \
  --noinclude-pytest-mode=nofollow \
  --assume-yes-for-downloads \
  --quiet \
  --main=scripts/relay-service.py \
  --main=scripts/relay.py
rm -rf dist/relay-service
mv dist/relay-service.dist dist/relay-service
if [ -f dist/relay-service/relay-service.bin ]; then
  mv dist/relay-service/relay-service.bin dist/relay-service/relay-service
fi
