#!/bin/sh
set -eu
pg_dump --format=custom --no-owner --no-acl \
  --schema=collector --schema=analytics \
  --dbname="$PGURI" --file=/tmp/yongin-collector.dump
