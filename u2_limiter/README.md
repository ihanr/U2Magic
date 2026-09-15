# U2 Limiter

This sidecar does not restart or alter the Java `u2magic` container. It only
manages per-torrent qB upload limits for exact category `U2` after dry-run.

On the server, create `/opt/u2magic/runtime/limiter` with mode `0700`, copy
`config.example.json` to `config.json`, and add all nine qB nodes. Start with:

```bash
docker compose -f docker-compose.current-server.yml up --build
```

The supplied compose file is dry-run only. Review the node counts and observed
tracker hosts, add only those U2 hosts to `allowed_tracker_hosts`, then replace
`--dry-run` with `--write` in the Compose command and start it again.

Rollback restores only recorded service-owned limits:

```bash
docker compose -f docker-compose.current-server.yml run --rm u2-limiter --config /runtime/config.json --release-managed-limits
docker compose -f docker-compose.current-server.yml stop u2-limiter
```
