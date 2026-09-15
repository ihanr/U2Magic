# U2 Category Dynamic Limiter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone sidecar that dynamically limits only `U2` category torrents across nine qBittorrent nodes so their announce-window average upload remains below 50 MiB/s.

**Architecture:** Python polls each qB WebUI, filters exact category `U2` and an observed tracker-host allow-list, and persists one state record per node/hash. It starts at 45 MiB/s and adjusts only limits it owns, never Java U2Magic, magic APIs, qB global limits, SSH, or `tc`.

**Tech Stack:** Python 3.13, standard-library HTTP/JSON, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-u2-category-dynamic-limiter-design.md`

## Global Constraints

- Use private runtime configuration for exactly nine qB nodes; never commit credentials.
- Act only when category equals `U2` and tracker host is allowed.
- Bootstrap/missing tracker information means 45 MiB/s; dynamic cap never exceeds 49 MiB/s.
- Store and restore an existing per-torrent limit; release only state marked owned.
- On errors retain service-owned limit and emit redacted node/path/status logs.
- No U2 Cookie, promotion, global qB limit, SSH, or network-interface shaping.

## File Structure

- `u2_limiter/limiter.py`: pure rate/state calculation.
- `u2_limiter/qb_api.py`: authenticated qB API adapter.
- `u2_limiter/main.py`: config, poll loop, dry-run/release modes.
- `u2_limiter/config.example.json`: secret-free schema.
- `u2_limiter/Dockerfile` and `u2_limiter/docker-compose.current-server.yml`: isolated sidecar.
- `u2_limiter/tests/test_limiter.py`, `u2_limiter/tests/test_qb_api.py`, `u2_limiter/tests/test_deployment.py`: regression checks.
- `u2_limiter/README.md`: diagnostics-first activation and rollback.

### Task 1: Implement and test the pure limiter core

**Files:** Create `u2_limiter/limiter.py`; create `u2_limiter/tests/test_limiter.py`.

**Interfaces:** Produce `Config`, `TorrentSample`, `LimiterState`, `Decision`, `decide(sample, previous, now, config)`, and `restore_limit(state)`.

- [ ] **Step 1: Write the failing tests**

```python
MIB = 1024 * 1024
def test_first_observation_uses_45_mib_cap():
    assert decide(sample(), None, 1000, Config()).limit_bps == 45 * MIB
def test_near_announce_budget_reduces_cap():
    prior = decide(sample(uploaded=0), None, 1000, Config()).state
    assert decide(sample(uploaded=49*MIB*1700, next_announce=100), prior, 2700, Config()).limit_bps < 49*MIB
def test_release_restores_only_owned_original_limit():
    assert restore_limit(LimiterState(original_limit_bps=20*MIB, owned=True)) == 20*MIB
```

- [ ] **Step 2: Verify red**

Run: `py -3.13 -m pytest u2_limiter/tests/test_limiter.py -v`

Expected: FAIL because `limiter` is absent.

- [ ] **Step 3: Implement the minimum calculation**

```python
cap = min(config.target_bps, max(config.floor_bps,
    (config.target_bps * previous.announce_interval - uploaded_since_baseline)
    // max(1, sample.next_announce)))
```

First observation/missing announce state returns `min(45 MiB/s, preexisting limit)` and stores the preexisting limit. A rising `next_announce` after it approached zero resets baseline to the current uploaded amount.

- [ ] **Step 4: Verify green and commit**

Run: `py -3.13 -m pytest u2_limiter/tests/test_limiter.py -v`

Expected: PASS.

```powershell
git add u2_limiter/limiter.py u2_limiter/tests/test_limiter.py
git commit -m "feat: add safe per-torrent limiter core"
```

### Task 2: Add qB API adapter with category-safe reads

**Files:** Create `u2_limiter/qb_api.py`; create `u2_limiter/tests/test_qb_api.py`.

**Interfaces:** Produce `QbClient.list_u2_torrents()` and `QbClient.set_upload_limit(torrent_hash, limit_bps)`.

- [ ] **Step 1: Write failing local-server tests**

```python
def test_list_requests_exact_u2_category(server):
    assert QbClient(server.node()).list_u2_torrents() == ["a" * 40]
    assert server.paths == ["/api/v2/torrents/info?category=U2"]
def test_write_uses_qb_bytes_per_second(server):
    QbClient(server.node()).set_upload_limit("a" * 40, 45 * 1024 * 1024)
    assert server.last_form["limit"] == str(45 * 1024 * 1024)
```

- [ ] **Step 2: Verify red**

Run: `py -3.13 -m pytest u2_limiter/tests/test_qb_api.py -v`

Expected: FAIL because `QbClient` is absent.

- [ ] **Step 3: Implement qB login, `torrents/info?category=U2`, `torrents/trackers`, and `torrents/setUploadLimit`**

Use a separate `http.cookiejar.CookieJar` per node. Retry exactly one failed request after re-login on HTTP 403. Keep tracker host filtering out of this adapter so dry-run can show nonmatching hosts.

- [ ] **Step 4: Verify green and commit**

Run: `py -3.13 -m pytest u2_limiter/tests/test_qb_api.py -v`

Expected: PASS.

```powershell
git add u2_limiter/qb_api.py u2_limiter/tests/test_qb_api.py
git commit -m "feat: add qB limiter API adapter"
```

### Task 3: Add persistent poll loop, diagnostics, and release

**Files:** Create `u2_limiter/main.py`; create `u2_limiter/config.example.json`; modify `u2_limiter/tests/test_limiter.py`.

**Interfaces:** Consume `--config`, `--state`, `--dry-run`, `--release-managed-limits`; produce redacted JSON log lines.

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_dry_run_never_writes(fake_client, paths):
    run_once([fake_client], paths.config, paths.state, dry_run=True)
    assert fake_client.set_calls == []
def test_non_allowed_tracker_never_writes(fake_client, paths):
    fake_client.samples = [sample(tracker_host="other.example")]
    run_once([fake_client], paths.config, paths.state, dry_run=False)
    assert fake_client.set_calls == []
```

- [ ] **Step 2: Verify red, implement, then verify green**

Run: `py -3.13 -m pytest u2_limiter/tests/test_limiter.py -v`

Expected before implementation: FAIL because `run_once` is absent. Implement atomic `state.json.tmp` + `fsync` + replace; validate unique node names, HTTP hosts, nonempty allow-list, and target `< 50`. `--release-managed-limits` restores recorded originals only.

Run after implementation: `py -3.13 -m pytest u2_limiter/tests -v`

Expected: PASS.

- [ ] **Step 3: Commit**

```powershell
git add u2_limiter/main.py u2_limiter/config.example.json u2_limiter/tests/test_limiter.py
git commit -m "feat: add limiter service modes and state"
```

### Task 4: Package isolated sidecar and document staged activation

**Files:** Create `u2_limiter/Dockerfile`, `u2_limiter/docker-compose.current-server.yml`, `u2_limiter/tests/test_deployment.py`, `u2_limiter/README.md`.

- [ ] **Step 1: Write failing deployment test**

```python
def test_compose_has_no_ports_and_private_runtime_mount():
    text = Path("u2_limiter/docker-compose.current-server.yml").read_text()
    assert "ports:" not in text
    assert "/opt/u2magic/runtime/limiter:/runtime" in text
```

- [ ] **Step 2: Verify red, implement, then verify green**

Run: `py -3.13 -m pytest u2_limiter/tests/test_deployment.py -v`

Expected before implementation: FAIL because compose file is absent.

Create a Python 3.13 image with `limiter.py`, `qb_api.py`, and `main.py`; Compose must expose no port, use `/opt/u2magic/runtime/limiter:/runtime`, and have `restart: unless-stopped`.

Run after implementation: `py -3.13 -m pytest u2_limiter/tests/test_deployment.py -v`

Expected: PASS.

- [ ] **Step 3: Add server preflight and rollback instructions, then commit**

README commands must: create private runtime directory; add all nine nodes; run `--dry-run`; inspect discovered U2 tracker hosts/counts; add only observed hosts; start sidecar; inspect logs; run `--release-managed-limits` and stop for rollback. It must state that existing Java `u2magic` is not restarted.

```powershell
git add u2_limiter
git commit -m "feat: package U2 limiter sidecar"
```

### Task 5: Live staging

**Files:** Modify `u2_limiter/README.md` only if real command output reveals a documented mismatch.

- [ ] **Step 1: Build without touching Java U2Magic**

Run on the server: `docker compose -f u2_limiter/docker-compose.current-server.yml build u2-limiter`

Expected: build succeeds and `u2magic` stays healthy.

- [ ] **Step 2: Complete all-nine-node read-only preflight**

Run: `docker run --rm -v /opt/u2magic/runtime/limiter:/runtime u2-limiter --config /runtime/config.json --state /runtime/state.json --dry-run`

Expected: nine node summaries, tracker-host/count diagnostics, and no qB write request.

- [ ] **Step 3: Activate only after reviewing preflight, then verify rollback**

Run: `docker compose -f u2_limiter/docker-compose.current-server.yml up -d u2-limiter`

Expected: only allowed-host `U2` category torrents receive limits. Before production acceptance run `docker compose -f u2_limiter/docker-compose.current-server.yml run --rm u2-limiter --release-managed-limits`; expected result is restoration of only recorded owned limits.

## Self-Review

- Spec coverage: Tasks 1–3 implement safe dynamic state, ownership, failures, and release; Task 2 provides category/tracker evidence; Task 4 isolates deployment; Task 5 requires read-only validation across all nine nodes before writes.
- Placeholder scan: tracker hosts intentionally come from observed live diagnostics and are not guessed.
- Type consistency: `TorrentSample`, `LimiterState`, and `Decision` originate in Task 1; Task 2 supplies samples; Task 3 consumes and persists decisions.
