from dataclasses import dataclass


MIB = 1024 * 1024


@dataclass(frozen=True)
class Config:
    bootstrap_bps: int = 45 * MIB
    target_bps: int = 49 * MIB
    floor_bps: int = 1024


@dataclass(frozen=True)
class TorrentSample:
    node: str
    torrent_hash: str
    category: str
    tracker_host: str
    uploaded: int
    next_announce: int
    upload_limit: int


@dataclass(frozen=True)
class LimiterState:
    baseline_uploaded: int
    previous_next_announce: int
    announce_interval: int
    original_limit_bps: int
    owned: bool


@dataclass(frozen=True)
class Decision:
    limit_bps: int
    reason: str
    state: LimiterState


def _cap(limit_bps: int, existing_bps: int) -> int:
    return limit_bps if existing_bps < 0 else min(limit_bps, existing_bps)


def decide(sample: TorrentSample, previous: LimiterState | None, now: int, config: Config) -> Decision:
    if previous is None or sample.next_announce <= 0:
        return Decision(
            _cap(config.bootstrap_bps, sample.upload_limit), "bootstrap",
            LimiterState(sample.uploaded, sample.next_announce, max(sample.next_announce, 1),
                         sample.upload_limit, True),
        )
    reset = previous.previous_next_announce <= 30 and sample.next_announce > previous.previous_next_announce + 30
    if reset:
        return Decision(
            _cap(config.bootstrap_bps, previous.original_limit_bps), "announce-reset",
            LimiterState(sample.uploaded, sample.next_announce, sample.next_announce,
                         previous.original_limit_bps, True),
        )
    used = max(0, sample.uploaded - previous.baseline_uploaded)
    budget = config.target_bps * previous.announce_interval - used
    cap = min(config.target_bps, max(config.floor_bps, budget // max(1, sample.next_announce)))
    return Decision(
        _cap(cap, previous.original_limit_bps), "dynamic",
        LimiterState(previous.baseline_uploaded, sample.next_announce, previous.announce_interval,
                     previous.original_limit_bps, True),
    )


def restore_limit(state: LimiterState) -> int:
    if not state.owned:
        raise ValueError("refusing to restore a limit not owned by the limiter")
    return state.original_limit_bps
