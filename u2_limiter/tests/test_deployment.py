from pathlib import Path


def test_compose_has_no_ports_and_private_runtime_mount():
    text = Path("u2_limiter/docker-compose.current-server.yml").read_text()
    assert "ports:" not in text
    assert "/opt/u2magic/runtime/limiter:/runtime" in text
    assert "--dry-run" in text
