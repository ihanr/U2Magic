import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from qb_api import QbClient


def filter_allowed(rows, allowed_hosts):
    return [row for row in rows if row.get("category") == "U2"
            and (urlparse(row.get("tracker", "")).hostname or "") in allowed_hosts]


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not config.get("nodes") or not config.get("allowed_tracker_hosts"):
        raise ValueError("nodes and allowed_tracker_hosts must be non-empty")
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


def dry_run(config):
    allowed = set(config["allowed_tracker_hosts"])
    for node in config["nodes"]:
        rows = QbClient(node).list_u2_torrents()
        print(json.dumps({"node": node["name"], "u2_category": len(rows),
                          "allowed": len(filter_allowed(rows, allowed))}))


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if not args.dry_run:
        raise SystemExit("write mode is not enabled until preflight is reviewed")
    dry_run(config)


if __name__ == "__main__":
    cli()
