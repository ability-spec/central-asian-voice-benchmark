"""Safe defaults and .env.example consistency (no providers, no network)."""

from pathlib import Path

from product.backend.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / "product" / "backend" / ".env.example"


def example_values():
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def test_server_binds_loopback_by_default(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    assert Settings().host == "127.0.0.1"


def test_env_example_does_not_expose_the_paid_api():
    assert example_values()["HOST"] == "127.0.0.1"


def test_env_example_matches_the_approved_diffusion_profile(monkeypatch):
    monkeypatch.delenv("ROUTE_B_DIFFUSION_STEPS", raising=False)
    assert int(example_values()["ROUTE_B_DIFFUSION_STEPS"]) == Settings().route_b_diffusion_steps == 10
