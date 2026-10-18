"""Headless Chrome is isolated behind an egress proxy (#127).

These guard the deployment config: a later edit must not put the renderer
back on the main network, publish its port, or drop a blocked range.
"""

from __future__ import annotations

import ipaddress
import re

import pytest

from tests.repo_files import require_repo_root

REPO = require_repo_root()  # skips in a backend-only mount
yaml = pytest.importorskip("yaml")
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text())
SQUID = (REPO / "deploy" / "egress-proxy" / "squid.conf").read_text()


def _nets(service: str) -> set[str]:
    nets = COMPOSE["services"][service].get("networks", [])
    return set(nets if isinstance(nets, list) else nets.keys())


def test_renderer_is_only_on_the_internal_network():
    assert COMPOSE["networks"]["render_net"].get("internal") is True
    assert _nets("browserless") == {"render_net"}
    assert "ports" not in COMPOSE["services"]["browserless"]


def test_data_stores_are_not_reachable_from_the_renderer():
    for service in ("db", "redis"):
        assert "render_net" not in _nets(service), service


def test_chrome_is_forced_through_the_proxy():
    args = COMPOSE["services"]["browserless"]["environment"]["DEFAULT_LAUNCH_ARGS"]
    assert "--proxy-server=http://egress-proxy:3128" in args
    assert "<-loopback>" in args
    assert _nets("egress-proxy") == {"render_net", "egress_net"}


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.17.0.2",
        "192.168.1.10",
        "169.254.169.254",
        "100.64.0.1",
        "::1",
        "fd00::1",
    ],
)
def test_proxy_blocks_every_private_and_metadata_range(address):
    ranges = [
        ipaddress.ip_network(m) for m in re.findall(r"^acl blocked_dst dst (\S+)", SQUID, re.M)
    ]
    ip = ipaddress.ip_address(address)
    assert any(ip.version == net.version and ip in net for net in ranges), address
    assert "http_access deny blocked_dst" in SQUID


@pytest.mark.asyncio
async def test_rendering_is_off_on_hosted_unless_allowed(monkeypatch):
    from app.services.ingestion import scraper

    monkeypatch.setattr(scraper.settings, "deployment_mode", "hosted")
    monkeypatch.setattr(scraper.settings, "browserless_hosted_allowed", False)
    assert await scraper._fetch_with_playwright("https://example.com/") == (None, None)
