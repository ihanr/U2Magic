import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from qb_api import QbClient
from limiter import Config, LimiterState, TorrentSample, decide


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


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not config.get("nodes"):
        raise ValueError("nodes must be non-empty")
    if config.get("target_mib_per_sec", 49) >= 50:
        raise ValueError("target_mib_per_sec must be below 50")
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


def run_once(clients, config, records, dry_run):
    allowed = set(config.get("allowed_tracker_hosts", []))
    for client in clients:
        node = getattr(client, "name", None) or client.node["name"]
        for row in filter_allowed(client.list_u2_torrents(), allowed):
            torrent_hash = row["hash"]
            key = f"{node}/{torrent_hash}"
            record = records.get(key)
            previous = None if record is None else LimiterState(
                record["baseline_uploaded"], record["previous_next_announce"],
                record["announce_interval"], record["original_limit_bps"], record["owned"],
            )
            sample = TorrentSample(node, torrent_hash, "U2", urlparse(row["tracker"]).hostname or "",
                                   int(row.get("uploaded", 0)), int(row.get("next_announce", 0)),
                                   int(row.get("up_limit", -1)))
            decision = decide(sample, previous, 0, Config())
            if not dry_run:
                client.set_upload_limit(torrent_hash, decision.limit_bps)
                state = decision.state
                records[key] = {"node": node, "hash": torrent_hash, "owned": True,
                                "original_limit_bps": state.original_limit_bps,
                                "baseline_uploaded": state.baseline_uploaded,
                                "previous_next_announce": state.previous_next_announce,
                                "announce_interval": state.announce_interval}
    return records


def dry_run(config):
    allowed = set(config.get("allowed_tracker_hosts", []))
    for node in config["nodes"]:
        rows = QbClient(node).list_u2_torrents()
        print(json.dumps({"node": node["name"], "u2_category": len(rows),
                          "tracker_hosts": host_counts(rows),
                          "allowed": len(filter_allowed(rows, allowed))}))


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
