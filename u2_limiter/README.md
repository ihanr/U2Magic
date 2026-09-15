# U2 Limiter

This sidecar does not restart or alter the Java `u2magic` container. It only
manages per-torrent qB upload limits for exact category `U2` after dry-run.
It reads qB's `reannounce` and `total_uploaded` properties; it does not read
U2 Cookie, UID, or passkey, and it never calls a U2 URL.

On the server, create `/opt/u2magic/runtime/limiter` with mode `0700`, copy
`config.example.json` to `config.json`, and add all nine qB nodes. Start with:

```bash
docker compose -f docker-compose.current-server.yml up --build
```

The supplied compose file is dry-run only. Review the node counts, observed
tracker hosts, and `reannounce` values, then add only those U2 hosts to
`allowed_tracker_hosts`. `average_mib_per_sec: 49` is a cycle-average budget.
`burst_mib_per_sec: 100` is the per-torrent front-loaded cap: calculated
early-cycle limits can reach 100 MiB/s, then fall as the cycle budget is used.
Until a complete announce cycle has been observed, or if a qB
properties request fails, the torrent stays at 45 MiB/s.

Only after reviewing dry-run output, explicitly replace `--dry-run` with
`--write` in the Compose command and start it again.

Rollback restores only recorded service-owned limits:

```bash
docker compose -f docker-compose.current-server.yml run --rm u2-limiter --config /runtime/config.json --release-managed-limits
docker compose -f docker-compose.current-server.yml stop u2-limiter
```
