#!/bin/sh
set -eu

mkdir -p /data/u2/config /data/u2/cookie /data/u2/db /data/u2/xml
mkdir -p /data/u2Magic/logs

if [ ! -f /data/u2/config/config.json ]; then
    cp /opt/u2magic-defaults/config.json /data/u2/config/config.json
fi

cp /opt/u2magic-defaults/application-base.yml \
    /data/u2Magic/config/application-base.yml

exec /__cacert_entrypoint.sh /bin/bash ./server.sh

