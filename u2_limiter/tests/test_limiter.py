from dataclasses import replace

from limiter import Config, LimiterState, TorrentSample, decide, restore_limit


MIB = 1024 * 1024


def sample(**changes):
    value = TorrentSample(
        node="DE2", torrent_hash="a" * 40, category="U2",
        tracker_host="daydream.dmhy.best", uploaded=0, reannounce=1800,
        upload_limit=-1,
    )
    return replace(value, **changes)


def test_first_observation_uses_45_mib_cap_without_verified_cycle():
    assert decide(sample(), None, 1000, Config()).limit_bps == 45 * MIB


def test_countdown_jump_creates_a_cycle_baseline():
    old = decide(sample(reannounce=5, uploaded=10_000), None, 1_000, Config()).state
    result = decide(sample(reannounce=1_795, uploaded=11_000), old, 1_010, Config())
    assert result.reason == "announce-reset"
    assert result.state.baseline_uploaded == 11_000
    assert result.state.announce_interval == 1_810


def test_budget_can_allow_an_instantaneous_limit_above_50_mib():
    previous = LimiterState(0, 1_795, 1_000, 1_810, -1, True)
    result = decide(sample(reannounce=900, uploaded=0), previous, 1_020, Config())
    assert result.reason == "dynamic"
    assert result.limit_bps > 50 * MIB


def test_exhausted_budget_uses_protective_floor():
    previous = LimiterState(0, 1_000, 1_000, 1_800, -1, True)
    result = decide(sample(reannounce=600, uploaded=49 * MIB * 1_800), previous, 1_010, Config())
    assert result.limit_bps == Config().floor_bps


def test_invalid_countdown_keeps_the_verified_cycle_state():
    previous = LimiterState(10_000, 900, 1_000, 1_800, -1, True)
    result = decide(sample(reannounce=0, uploaded=11_000), previous, 1_010, Config())
    assert result.reason == "bootstrap"
    assert result.state == previous


def test_finite_original_limit_remains_when_lower_than_budget_limit():
    previous = LimiterState(0, 1_000, 1_000, 1_800, 20 * MIB, True)
    assert decide(sample(reannounce=900, uploaded=0), previous, 1_010, Config()).limit_bps == 20 * MIB


def test_release_restores_only_owned_original_limit():
    state = LimiterState(0, 0, 0, 1800, 20 * MIB, True)
    assert restore_limit(state) == 20 * MIB
