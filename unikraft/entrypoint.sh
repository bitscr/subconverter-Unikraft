#!/bin/sh
set -eu

: "${API_TOKEN:?Set API_TOKEN to a private administration token}"
# Keep all runtime writes in RAM, also when Docker's root filesystem is read-only.
mkdir -p /tmp/subconverter
cp -R /base/. /tmp/subconverter/
# Persist the environment override in the temporary config so /readconf keeps it.
awk '/^api_access_token=/ { print "api_access_token=" ENVIRON["API_TOKEN"]; next } { print }' \
    /base/pref.ini > /tmp/subconverter/pref.ini
cd /tmp/subconverter
exec /usr/bin/subconverter --file /tmp/subconverter/pref.ini "$@"
