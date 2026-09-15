import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from qb_api import QbClient
from limiter import Config, LimiterState, TorrentSample, decide


HOLD_PREFIX = "U2LimitHoldUntil-"
HOLD_TTL_SECONDS = 90


def filter_allowed(rows, allowed_hosts):
    return [row for row in rows if row.get("category") == "U2"
            and (urlparse(row.get("tracker", "")).hostname or "") in allowed_hosts]


def host_counts(rows):
    counts = {}
    for row in rows:
        if row.get("category") == "U2":
            host = urlparse(row.get("tracker", "")).hostname or "(missing)"
            counts[host] = counts.get(host, 0) + 1
    return dict(sorted(counts.items()))


def hold_tags(row):
    return [tag for tag in row.get("tags", "").split(",") if tag.startswith(HOLD_PREFIX)]


def refresh_hold_tag(client, row, now):
    torrent_hash = row["hash"]
    tag = f"{HOLD_PREFIX}{now + HOLD_TTL_SECONDS}"
    client.add_tags(torrent_hash, tag)
    stale = [item for item in hold_tags(row) if item != tag]
    if stale:
        client.remove_tags(torrent_hash, ",".join(stale))


def clear_hold_tags(client, row):
    tags = hold_tags(row)
    if tags:
        client.remove_tags(row["hash"], ",".join(tags))


def limiter_config(config):
    return Config(
        bootstrap_bps=int(config.get("bootstrap_mib_per_sec", 45)) * 1024 * 1024,
        average_bps=int(config.get("average_mib_per_sec", 49)) * 1024 * 1024,
        safety_seconds=int(config.get("safety_seconds", 30)),
        reset_jump_seconds=int(config.get("reset_jump_seconds", 60)),
        burst_bps=int(config.get("burst_mib_per_sec", 100)) * 1024 * 1024,
        poll_seconds=int(config.get("poll_seconds", 15)),
    )


def reannounce_values(client, rows):
    values = {}
    failures = 0
    for row in rows:
        if row.get("category") != "U2":
            continue
        try:
            values[row["hash"]] = max(0, int(client.torrent_properties(row["hash"]).get("reannounce", 0)))
        except Exception:
            failures += 1
    return values, failures


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not config.get("nodes"):
        raise ValueError("nodes must be non-empty")
    if not 0 < int(config.get("average_mib_per_sec", 49)) < 50:
        raise ValueError("average_mib_per_sec must be below 50")
    for key, default in (("poll_seconds", 15), ("bootstrap_mib_per_sec", 45),
                         ("safety_seconds", 30), ("reset_jump_seconds", 60),
                         ("burst_mib_per_sec", 100)):
        if int(config.get(key, default)) <= 0:
            raise ValueError(f"{key} must be positive")
    return config


def load_state(path):
    state_path = Path(path)
    return json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}


def save_state(path, state):
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(state_path) + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(state_path)


def release_state(clients, records):
    remaining = {}
    for key, record in records.items():
        if not record.get("owned"):
            remaining[key] = record
            continue
        try:
            clients[record["node"]].set_upload_limit(record["hash"], record["original_limit_bps"])
        except Exception:
            remaining[key] = record
    return remaining


def run_once(clients, config, records, dry_run, now=None):
    now = int(time.time()) if now is None else now
    allowed = set(config.get("allowed_tracker_hosts", []))
    limits = limiter_config(config)
    for client in clients:
        node = getattr(client, "name", None) or client.node["name"]
        for row in filter_allowed(client.list_u2_torrents(), allowed):
            torrent_hash = row["hash"]
            try:
                properties = client.torrent_properties(torrent_hash)
                reannounce = max(0, int(properties.get("reannounce", 0)))
                uploaded = int(properties.get("total_uploaded", row.get("uploaded", 0)))
            except Exception:
                reannounce = 0
                uploaded = int(row.get("uploaded", 0))
            key = f"{node}/{torrent_hash}"
            record = records.get(key)
            previous = None if record is None or "observed_at" not in record else LimiterState(
                record["baseline_uploaded"], record["previous_reannounce"], record["observed_at"],
                record["announce_interval"], record["original_limit_bps"], record["owned"],
            )
            sample = TorrentSample(node, torrent_hash, "U2", urlparse(row["tracker"]).hostname or "",
                                   uploaded, reannounce,
                                   int(row.get("up_limit", -1)))
            decision = decide(sample, previous, now, limits)
            if not dry_run:
                original = decision.state.original_limit_bps
                holding = decision.reason == "dynamic" and (original < 0 or decision.limit_bps < original)
                if holding:
                    refresh_hold_tag(client, row, now)
                    client.set_upload_limit(torrent_hash, decision.limit_bps)
                else:
                    client.set_upload_limit(torrent_hash, decision.limit_bps)
                    clear_hold_tags(client, row)
                state = decision.state
                records[key] = {"node": node, "hash": torrent_hash, "owned": True,
                                "original_limit_bps": state.original_limit_bps,
                                "baseline_uploaded": state.baseline_uploaded,
                                "previous_reannounce": state.previous_reannounce,
                                "observed_at": state.observed_at,
                                "announce_interval": state.announce_interval}
    return records


def dry_run(config):
    allowed = set(config.get("allowed_tracker_hosts", []))
    for node in config["nodes"]:
        client = QbClient(node)
        rows = client.list_u2_torrents()
        reannounce, failures = reannounce_values(client, rows)
        print(json.dumps({"node": node["name"], "u2_category": len(rows),
                          "tracker_hosts": host_counts(rows),
                          "reannounce": reannounce,
                          "allowed": len(filter_allowed(rows, allowed)),
                          "properties_failures": failures}))


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--state", default="/runtime/state.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--release-managed-limits", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    clients = [QbClient(node) for node in config["nodes"]]
    if args.release_managed_limits:
        save_state(args.state, release_state({client.node["name"]: client for client in clients}, load_state(args.state)))
        return
    if args.dry_run:
        dry_run(config)
        return
    if not args.write:
        raise SystemExit("use --dry-run or explicit --write")
    while True:
        save_state(args.state, run_once(clients, config, load_state(args.state), dry_run=False))
        time.sleep(int(config.get("poll_seconds", 15)))


if __name__ == "__main__":
    cli()
