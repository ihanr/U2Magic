from dataclasses import replace

from limiter import Config, LimiterState, TorrentSample, decide, restore_limit


MIB = 1024 * 1024


def sample(**changes):
    value = TorrentSample(
        node="DE2", torrent_hash="a" * 40, category="U2",
        tracker_host="u2.dmhy.org", uploaded=0, next_announce=1800,
        upload_limit=-1,
    )
    return replace(value, **changes)


def test_first_observation_uses_45_mib_cap():
    assert decide(sample(), None, 1000, Config()).limit_bps == 45 * MIB


def test_near_announce_budget_reduces_cap():
    previous = decide(sample(), None, 1000, Config()).state
    current = sample(uploaded=49 * MIB * 1790, next_announce=100)
    assert 0 < decide(current, previous, 2700, Config()).limit_bps < 49 * MIB


def test_release_restores_only_owned_original_limit():
    state = LimiterState(0, 0, 1800, 20 * MIB, True)
    assert restore_limit(state) == 20 * MIB
