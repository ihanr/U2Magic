# qB Reannounce U2 Dynamic Limiter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `u2-limiter` dynamically control per-torrent U2 upload limits from qBittorrent's own announce countdown and uploaded-byte counters.

**Architecture:** qB's `/api/v2/torrents/properties` supplies `reannounce` and `total_uploaded` for each exact-category, allowed-tracker torrent. The limiter persists a baseline when the countdown jumps back after an announce, then divides the remaining average-upload budget by time remaining; the resulting instantaneous limit may exceed 50 MiB/s. Before a verified cycle baseline exists, any qB observation fails, or a countdown is invalid, it applies the existing 45 MiB/s conservative limit.

**Tech Stack:** Python 3.13 standard library, pytest, qBittorrent Web API, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-15-u2-category-dynamic-limiter-design.md`

## Global Constraints

- Process only the exact qB category `U2` and only configured allowed tracker hostnames.
- Do not access U2 website URLs or read/use U2 Cookie, UID, or passkey.
- Do not alter Java `u2magic`, qB global limits, non-U2 torrents, download limits, `tc`, or SSH.
- `average_mib_per_sec` must remain strictly below 50; it is a cycle-average budget, not an instantaneous cap.
- Store qB credentials only in server-private runtime configuration; never log passwords or full tracker query strings.
- A failed observation must keep or apply the 45 MiB/s bootstrap limit, never relax a limit.
- Release only records explicitly owned by this service, restoring their captured original per-torrent limit.

---

## File structure

- Modify `u2_limiter/qb_api.py`: add the qB properties endpoint and a narrow `torrent_properties()` reader.
- Modify `u2_limiter/limiter.py`: replace unusable tracker `next_announce` logic with persistent reannounce-cycle budget decisions.
- Modify `u2_limiter/main.py`: read properties per selected torrent, migrate records safely, and expose reannounce data in dry-run output.
- Modify `u2_limiter/config.example.json`: document the renamed average-budget and safety settings without credentials.
- Modify `u2_limiter/README.md`: document read-only validation, activation, fallback and release behavior.
- Modify `u2_limiter/tests/test_qb_api.py`, `u2_limiter/tests/test_limiter.py`, `u2_limiter/tests/test_main.py`, `u2_limiter/tests/test_deployment.py`: cover the qB API, arithmetic, safety fallbacks, state persistence and deployment contract.

### Task 1: Read qB properties without tracker-endpoint assumptions

**Files:**
- Modify: `u2_limiter/qb_api.py`
- Test: `u2_limiter/tests/test_qb_api.py`

**Interfaces:**
- Produces: `QbClient.properties_path(torrent_hash: str) -> str` and `QbClient.torrent_properties(torrent_hash: str) -> dict`.
- Consumed by: `main.run_once()` and `main.dry_run()` in Task 3.

- [ ] **Step 1: Write the failing API-path and payload tests**

```python
def test_properties_path_uses_one_hash_query():
    client = QbClient({"name": "DE2", "host": "http://example.test", "username": "", "password": ""})
    assert client.properties_path("a" * 40) == "/api/v2/torrents/properties?hash=" + "a" * 40


def test_torrent_properties_returns_qb_reannounce_and_uploaded(monkeypatch):
    client = QbClient({"name": "DE2", "host": "http://example.test", "username": "", "password": ""})
    monkeypatch.setattr(client, "_request", lambda path, data=None: b'{"reannounce":224,"total_uploaded":123}')
    assert client.torrent_properties("a" * 40) == {"reannounce": 224, "total_uploaded": 123}
```

- [ ] **Step 2: Run the focused test file and verify it fails**

Run: `python -m pytest u2_limiter/tests/test_qb_api.py -v`

Expected: FAIL because `properties_path` and `torrent_properties` do not exist.

- [ ] **Step 3: Implement the narrow qB properties reader**

```python
def properties_path(self, torrent_hash):
    return "/api/v2/torrents/properties?" + urlencode({"hash": torrent_hash})


def torrent_properties(self, torrent_hash):
    return json.loads(self._request(self.properties_path(torrent_hash)))
```

Keep `next_announce()` temporarily so the next task can remove all callers in one commit; do not add a second HTTP library.

- [ ] **Step 4: Run the focused test file and verify it passes**

Run: `python -m pytest u2_limiter/tests/test_qb_api.py -v`

Expected: PASS, including the new properties tests.

- [ ] **Step 5: Commit the API reader**

```bash
git add u2_limiter/qb_api.py u2_limiter/tests/test_qb_api.py
git commit -m "feat: read qB reannounce properties"
```

### Task 2: Implement persistent announce-budget decisions

**Files:**
- Modify: `u2_limiter/limiter.py`
- Test: `u2_limiter/tests/test_limiter.py`

**Interfaces:**
- Consumes: qB `reannounce`, `total_uploaded`, `now`, `average_bps`, `safety_seconds`, and the prior persisted state.
- Produces: `TorrentSample(..., reannounce: int, uploaded: int, upload_limit: int)`, `LimiterState(baseline_uploaded, previous_reannounce, observed_at, announce_interval, original_limit_bps, owned)`, and `Decision(limit_bps, reason, state)`.

- [ ] **Step 1: Write failing arithmetic and fallback tests**

```python
def test_first_observation_uses_bootstrap_without_verified_cycle():
    assert decide(sample(reannounce=900), None, 1_000, Config()).limit_bps == 45 * MIB


def test_countdown_jump_creates_a_cycle_baseline():
    old = decide(sample(reannounce=5, uploaded=10_000), None, 1_000, Config()).state
    result = decide(sample(reannounce=1_795, uploaded=11_000), old, 1_010, Config())
    assert result.reason == "announce-reset"
    assert result.state.baseline_uploaded == 11_000
    assert result.state.announce_interval == 1_810


def test_budget_allows_an_instantaneous_limit_above_50_mib():
    previous = LimiterState(0, 1_795, 1_000, 1_810, -1, True)
    result = decide(sample(reannounce=900, uploaded=0), previous, 1_020, Config())
    assert result.reason == "dynamic"
    assert result.limit_bps > 50 * MIB


def test_exhausted_budget_uses_protective_floor():
    previous = LimiterState(0, 1_000, 1_000, 1_800, -1, True)
    result = decide(sample(reannounce=600, uploaded=49 * MIB * 1_800), previous, 1_010, Config())
    assert result.limit_bps == Config().floor_bps
```

- [ ] **Step 2: Run the focused limiter tests and verify they fail**

Run: `python -m pytest u2_limiter/tests/test_limiter.py -v`

Expected: FAIL because the current state lacks `observed_at` and uses `next_announce` / a 49 MiB/s instantaneous cap.

- [ ] **Step 3: Replace the decision model with the cycle-budget formula**

Implement these exact rules:

```python
interval_on_reset = previous.previous_reannounce + (now - previous.observed_at) + sample.reannounce
used = max(0, sample.uploaded - previous.baseline_uploaded)
budget = config.average_bps * max(0, previous.announce_interval - config.safety_seconds) - used
candidate = max(config.floor_bps, budget // max(1, sample.reannounce + config.safety_seconds))
```

Treat a reset as `sample.reannounce > previous.previous_reannounce + config.reset_jump_seconds`. On a reset, set the baseline to the current `total_uploaded`, set `announce_interval` to `interval_on_reset`, preserve `original_limit_bps`, and return bootstrap. For invalid/non-positive countdowns, missing state, non-positive interval, or a non-monotonic uploaded counter, return bootstrap. If `candidate >= original_limit_bps` for a finite original limit, return the original limit. If the original limit is unlimited (`-1`), always write the calculated candidate: releasing it early would allow an unknown future burst to consume the remaining budget. Otherwise apply the candidate. Remove `next_announce` fields and `_cap()`.

- [ ] **Step 4: Run limiter tests and the full limiter suite**

Run: `python -m pytest u2_limiter/tests/test_limiter.py -v; python -m pytest u2_limiter/tests -v`

Expected: PASS. The full suite may initially expose callers still constructing the old state; update only those callers in Task 3 rather than weakening the tests.

- [ ] **Step 5: Commit the decision engine**

```bash
git add u2_limiter/limiter.py u2_limiter/tests/test_limiter.py
git commit -m "feat: budget U2 limits by qB reannounce cycle"
```

### Task 3: Wire properties into runtime, state, and dry-run diagnostics

**Files:**
- Modify: `u2_limiter/main.py`
- Modify: `u2_limiter/config.example.json`
- Test: `u2_limiter/tests/test_main.py`

**Interfaces:**
- Consumes: `QbClient.torrent_properties()` from Task 1 and `decide()` from Task 2.
- Produces: records with `baseline_uploaded`, `previous_reannounce`, `observed_at`, `announce_interval`, `original_limit_bps`, `owned`, plus dry-run JSON with only counts, tracker hostnames and non-sensitive reannounce values.

- [ ] **Step 1: Write failing runtime tests**

```python
def test_run_once_bootstraps_when_properties_fail():
    class Client:
        name = "DE2"
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/a", "up_limit": -1}]
        def torrent_properties(self, torrent_hash):
            raise OSError("temporary failure")
        def set_upload_limit(self, torrent_hash, limit_bps): self.calls.append((torrent_hash, limit_bps))
        def __init__(self): self.calls = []
    client = Client()
    run_once([client], {"allowed_tracker_hosts": ["daydream.dmhy.best"]}, {}, dry_run=False, now=1_000)
    assert client.calls == [("a", 45 * 1024 * 1024)]


def test_dry_run_reports_reannounce_not_cookie_or_tracker_query(monkeypatch, capsys):
    class Client:
        def __init__(self, node): pass
        def list_u2_torrents(self):
            return [{"hash": "a", "category": "U2", "tracker": "https://daydream.dmhy.best/private-query"}]
        def torrent_properties(self, torrent_hash):
            return {"reannounce": 224, "total_uploaded": 123}
    dry_run({"nodes": [{"name": "DE2"}], "allowed_tracker_hosts": ["daydream.dmhy.best"]}, client_factory=Client)
    output = capsys.readouterr().out
    assert '"reannounce": {"a": 224}' in output
    assert "password" not in output
    assert "private-query" not in output
```

Pass the local fake client constructor through a new optional `client_factory=QbClient` parameter; assert the serialized output contains `"reannounce"`, does not contain `password`, and does not contain the path/query portion of a tracker URL.

- [ ] **Step 2: Run the focused main tests and verify they fail**

Run: `python -m pytest u2_limiter/tests/test_main.py -v`

Expected: FAIL because `run_once()` has no `now` parameter and still calls `next_announce()`.

- [ ] **Step 3: Wire the new reader and safe fallbacks**

Replace `announce_values()` with a helper that calls `torrent_properties()` once per selected row and returns only integer reannounce values. In `run_once()`, catch an exception per torrent properties request, construct a sample with `reannounce=0` on failure, and still call `decide()` so bootstrap is written. Add `now=None` and use `int(time.time())` when omitted. Persist the Task-2 state fields atomically; when reading an old record missing `observed_at`, treat it as no verified cycle rather than raising or trusting stale state.

Change `load_config()` and the example file to:

```json
{
  "poll_seconds": 15,
  "bootstrap_mib_per_sec": 45,
  "average_mib_per_sec": 49,
  "safety_seconds": 30,
  "reset_jump_seconds": 60,
  "allowed_tracker_hosts": ["daydream.dmhy.best"],
  "nodes": []
}
```

Reject `average_mib_per_sec >= 50`, non-positive poll/bootstrap/safety/reset values, and an empty node list. Keep node credentials in the server's private config only. Dry-run must query no U2 web resource and print only node name, U2 count, host counts, reannounce map, selected count and properties-failure count.

- [ ] **Step 4: Run main and complete test suite**

Run: `python -m pytest u2_limiter/tests/test_main.py -v; python -m pytest u2_limiter/tests -v`

Expected: PASS, including fallback bootstrap and state migration tests.

- [ ] **Step 5: Commit runtime wiring**

```bash
git add u2_limiter/main.py u2_limiter/config.example.json u2_limiter/tests/test_main.py
git commit -m "feat: drive limiter from qB reannounce properties"
```

### Task 4: Document safe operation and lock the deployment contract

**Files:**
- Modify: `u2_limiter/README.md`
- Modify: `u2_limiter/tests/test_deployment.py`

**Interfaces:**
- Consumes: the dry-run and `--release-managed-limits` CLI from Task 3.
- Produces: copyable deployment validation and rollback instructions that preserve the Java deployment.

- [ ] **Step 1: Write failing documentation-contract tests**

```python
def test_readme_documents_reannounce_budget_and_no_u2_cookie():
    text = Path("u2_limiter/README.md").read_text(encoding="utf-8")
    assert "reannounce" in text
    assert "Cookie" in text
    assert "不读取" in text
    assert "45 MiB/s" in text
```

- [ ] **Step 2: Run the deployment tests and verify the new assertion fails**

Run: `python -m pytest u2_limiter/tests/test_deployment.py -v`

Expected: FAIL because the existing README does not explain the qB properties source or explicitly state that U2 Cookie is not read.

- [ ] **Step 3: Update the README without enabling the service by default**

Document that the compose file remains `--dry-run`; show a read-only command that verifies all configured nodes and displays reannounce values, then an explicit operator-only change from `--dry-run` to `--write`. State that `average_mib_per_sec: 49` is the average budget and does not cap instantaneous limits at 49 MiB/s. State that failures hold 45 MiB/s and that the release command restores only service-owned limits. Explicitly state that the limiter never reads U2 Cookie/UID/passkey or calls U2 URLs.

- [ ] **Step 4: Run all local verification**

Run: `python -m pytest u2_limiter/tests -v; docker compose -f u2_limiter/docker-compose.current-server.yml config --quiet`

Expected: all tests PASS and Compose validation exits 0.

- [ ] **Step 5: Commit documentation and deployment checks**

```bash
git add u2_limiter/README.md u2_limiter/tests/test_deployment.py
git commit -m "docs: describe qB reannounce limiter operation"
```

### Task 5: Publish and perform read-only server validation

**Files:**
- Modify: no additional source files.

**Interfaces:**
- Consumes: the built sidecar from Tasks 1-4 and `/opt/u2magic/runtime/limiter/config.json`.
- Produces: evidence that the deployed image has the new code and that dry-run can inspect all nine nodes without qB write calls.

- [ ] **Step 1: Verify the committed source before publication**

Run: `git status --short; git log --oneline -5; python -m pytest u2_limiter/tests -v`

Expected: only pre-existing user artifacts may remain untracked; all limiter tests PASS.

- [ ] **Step 2: Push the feature commits to the writable `user/main` remote**

Run: `git push user HEAD:main; git ls-remote user refs/heads/main`

Expected: the remote main SHA matches the local pushed commit.

- [ ] **Step 3: Update only the sidecar source on the server and keep dry-run mode**

Run on the Debian server:

```bash
stage=$(mktemp -d)
git clone --depth 1 --branch main https://github.com/ihanr/U2Magic.git "$stage"
cp -a "$stage/u2_limiter/." /opt/u2magic/u2_limiter/
cd /opt/u2magic/u2_limiter
docker compose -f docker-compose.current-server.yml build --no-cache u2-limiter
docker compose -f docker-compose.current-server.yml run --rm u2-limiter --config /runtime/config.json --state /runtime/state.json --dry-run
```

Expected: dry-run prints all configured node names, counts, tracker hostnames, and reannounce values; it must not call `setUploadLimit` or start a persistent writer.

- [ ] **Step 4: Inspect only safe operational evidence**

Run on the Debian server:

```bash
stat -c '%a %n' /opt/u2magic/runtime/limiter/config.json
docker image inspect u2_limiter-u2-limiter --format '{{.Id}}'
```

Expected: configuration permission is `600`; image is present. Do not print the configuration contents.

- [ ] **Step 5: Require explicit activation approval**

Do not change Compose from `--dry-run` to `--write` in this task. Present the read-only output to the user and obtain a new explicit approval before any qB per-torrent limit is written.
