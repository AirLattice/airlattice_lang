#!/usr/bin/env bash
set -euo pipefail

MIGRATE_URL="https://github.com/golang-migrate/migrate/releases/download/v4.17.0/migrate.linux-amd64.deb"

sudo docker run --rm -t --network host \
  -v "$PWD/backend:/backend" -w /backend \
  -e POSTGRES_HOST=127.0.0.1 \
  -e POSTGRES_PORT=5433 \
  -e POSTGRES_DB=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  python:3.11-bullseye bash -lc \
  "apt-get update && apt-get install -y wget \
   && wget -O /tmp/migrate.deb \"$MIGRATE_URL\" \
   && dpkg -i /tmp/migrate.deb && rm /tmp/migrate.deb \
   && pip install poetry==1.5.1 \
   && poetry install --with dev,lint,test \
   && make lint \
   && make test" | tee backend-ci.log
