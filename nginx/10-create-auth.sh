#!/bin/sh
set -eu

: "${NGINX_USERNAME:?NGINX_USERNAME is required}"
: "${NGINX_PASSWORD:?NGINX_PASSWORD is required}"

htpasswd -bcB /etc/nginx/.htpasswd "$NGINX_USERNAME" "$NGINX_PASSWORD"
chmod 640 /etc/nginx/.htpasswd
chown root:nginx /etc/nginx/.htpasswd
