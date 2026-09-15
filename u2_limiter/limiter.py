from dataclasses import dataclass


MIB = 1024 * 1024


@dataclass(frozen=True)
class Config:
    bootstrap_bps: int = 45 * MIB
    average_bps: int = 49 * MIB
    safety_seconds: int = 30
    reset_jump_seconds: int = 60
    floor_bps: int = 1024


@dataclass(frozen=True)
class TorrentSample:
    node: str
    torrent_hash: str
    category: str
    tracker_host: str
    uploaded: int
    reannounce: int
    upload_limit: int


@dataclass(frozen=True)
class LimiterState:
    baseline_uploaded: int
    previous_reannounce: int
    observed_at: int
    announce_interval: int
    original_limit_bps: int
    owned: bool


@dataclass(frozen=True)
class Decision:
    limit_bps: int
    reason: str
    state: LimiterState


def _limit(limit_bps: int, original_limit_bps: int) -> int:
    return min(limit_bps, original_limit_bps) if original_limit_bps >= 0 else limit_bps


def _bootstrap(sample: TorrentSample, previous: LimiterState | None, now: int, config: Config, reason: str) -> Decision:
    original_limit_bps = sample.upload_limit if previous is None else previous.original_limit_bps
    return Decision(
        _limit(config.bootstrap_bps, original_limit_bps), reason,
        LimiterState(sample.uploaded, sample.reannounce, now, 0, original_limit_bps, True),
    )


def decide(sample: TorrentSample, previous: LimiterState | None, now: int, config: Config) -> Decision:
    if previous is None:
        return _bootstrap(sample, previous, now, config, "bootstrap")
    if sample.reannounce <= 0:
        return Decision(_limit(config.bootstrap_bps, previous.original_limit_bps), "bootstrap", previous)
    reset = sample.reannounce > previous.previous_reannounce + config.reset_jump_seconds
    if reset:
        interval = previous.previous_reannounce + max(0, now - previous.observed_at) + sample.reannounce
        return Decision(
            _limit(config.bootstrap_bps, previous.original_limit_bps), "announce-reset",
            LimiterState(sample.uploaded, sample.reannounce, now, interval,
                         previous.original_limit_bps, True),
        )
    if previous.announce_interval <= 0 or sample.uploaded < previous.baseline_uploaded:
        return _bootstrap(sample, previous, now, config, "bootstrap")
    used = max(0, sample.uploaded - previous.baseline_uploaded)
    budget = config.average_bps * max(0, previous.announce_interval - config.safety_seconds) - used
    cap = max(config.floor_bps, budget // max(1, sample.reannounce + config.safety_seconds))
    return Decision(
        _limit(cap, previous.original_limit_bps), "dynamic",
        LimiterState(previous.baseline_uploaded, sample.reannounce, now, previous.announce_interval,
                     previous.original_limit_bps, True),
    )


def restore_limit(state: LimiterState) -> int:
    if not state.owned:
        raise ValueError("refusing to restore a limit not owned by the limiter")
    return state.original_limit_bps
