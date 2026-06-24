FROM kuanghom/u2magic:latest AS source

FROM alpine:3.21 AS patcher
RUN apk add --no-cache zip
COPY --from=source /data/u2Magic/lib/app.jar /work/app.jar
COPY jar-overrides/ /work/overrides/
RUN cd /work \
    && (zip -d app.jar \
        'BOOT-INF/classes/com/khc/u2/Security/BasicAuthFilter.class' >/dev/null 2>&1 || true) \
    && zip -d app.jar \
        'BOOT-INF/classes/static/index.html' \
        'BOOT-INF/classes/static/addTorrent.html' \
        'BOOT-INF/classes/com/khc/u2/Service/QbScheduleService.class' >/dev/null \
    && cd /work/overrides \
    && zip /work/app.jar \
        'BOOT-INF/classes/static/index.html' \
        'BOOT-INF/classes/static/addTorrent.html' \
        'BOOT-INF/classes/com/khc/u2/Service/QbScheduleService.class'

FROM kuanghom/u2magic:latest
COPY --from=patcher /work/app.jar /data/u2Magic/lib/app.jar
COPY defaults/ /opt/u2magic-defaults/
COPY entrypoint.sh /usr/local/bin/u2magic-entrypoint.sh
RUN chmod +x /usr/local/bin/u2magic-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/u2magic-entrypoint.sh"]
CMD []
