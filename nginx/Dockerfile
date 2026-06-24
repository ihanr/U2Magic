FROM nginx:1.27-alpine

RUN apk add --no-cache apache2-utils

COPY default.conf /etc/nginx/conf.d/default.conf
COPY 10-create-auth.sh /docker-entrypoint.d/10-create-auth.sh
RUN chmod +x /docker-entrypoint.d/10-create-auth.sh

