import hashlib
import json
import sys

import httpx
import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from market_fiyati_mcp.client import MarketClient
from market_fiyati_mcp.config import Settings, password_hash
from market_fiyati_mcp.oauth import allowed_redirect
from market_fiyati_mcp.server import build_app


def prices():
    return MarketClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"content": [], "numberOfFound": 0})
        )
    )


def rpc(client, token=None, headers=None):
    request_headers = {"Accept": "application/json, text/event-stream"}
    if token:
        request_headers["Authorization"] = "Bearer " + token
    request_headers.update(headers or {})
    return client.post(
        "/mcp",
        headers=request_headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        },
    )


def test_local_http_needs_no_credentials_or_state(tmp_path):
    settings = Settings(auth_mode="none", state_dir=str(tmp_path))
    with TestClient(build_app(settings, prices()), base_url=settings.public_url) as client:
        assert rpc(client).status_code == 200
        assert len(rpc(client).json()["result"]["tools"]) == 3
        assert client.get("/livez").status_code == 200
        assert rpc(client, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert not (tmp_path / "oauth.db").exists()


def test_bearer_profile_authenticates_without_persistent_state(tmp_path):
    token = "test-token-with-sufficient-length-for-fixture"
    settings = Settings(
        public_url="https://192.0.2.1:8443",
        auth_mode="bearer",
        access_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        state_dir=str(tmp_path),
        host="0.0.0.0",
        port=8080,
    )
    with TestClient(build_app(settings, prices()), base_url=settings.public_url) as client:
        assert rpc(client).status_code == 401
        assert rpc(client, "wrong-token-value-long-enough").status_code == 401
        assert rpc(client, token).status_code == 200
        assert client.get("/livez").status_code == 200
        # Local health checks remain usable when the public endpoint is platform-managed.
        assert client.get("http://127.0.0.1:8080/livez").status_code == 200
    assert not (tmp_path / "oauth.db").exists()


@pytest.mark.parametrize(
    "host,url",
    [
        ("0.0.0.0", "http://127.0.0.1:8000"),
        ("127.0.0.1", "https://agent.example"),
    ],
)
def test_unauthenticated_remote_configuration_is_rejected(host, url):
    with pytest.raises(ValueError, match="loopback"):
        Settings(auth_mode="none", host=host, public_url=url)


@pytest.mark.parametrize(
    "url",
    [
        "https://192.0.2.1",
        "https://[2001:db8::1]:8443",
        "https://service.example:9443",
        "http://127.0.0.1:8000",
        "http://[::1]:9000",
        "http://localhost:9000",
    ],
)
def test_origins_support_ip_and_loopback(url):
    Settings(public_url=url, auth_mode="bearer", access_token_hash="ab" * 32)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.0.2.1",
        "http://service.example",
        "https://service.example/path",
        "https://user:pass@example.org",
        "https://service.example:99999",
    ],
)
def test_invalid_or_cleartext_remote_origins_fail_closed(url):
    with pytest.raises(ValueError):
        Settings(public_url=url, auth_mode="bearer", access_token_hash="ab" * 32)


@pytest.mark.parametrize(
    "url",
    [
        "https://any-client.example/callback",
        "http://localhost:39123/callback",
        "http://[::1]:39123/callback",
    ],
)
def test_oauth_callback_policy_has_no_vendor_allowlist(url):
    assert allowed_redirect(url)


def test_loopback_oauth_cookie_can_complete_consent(tmp_path):
    import base64
    from urllib.parse import urlparse

    password = "temporary-fixture-password"
    settings = Settings(
        public_url="http://127.0.0.1:8000",
        state_dir=str(tmp_path),
        encryption_key=Fernet.generate_key().decode(),
        owner_password_hash=password_hash(password),
    )
    with TestClient(
        build_app(settings, prices()), base_url=settings.public_url, follow_redirects=False
    ) as client:
        redirect = "http://127.0.0.1:39123/callback"
        agent = client.post(
            "/register",
            json={
                "client_name": "Generic client",
                "redirect_uris": [redirect],
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        ).json()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(b"x" * 64).digest()).decode().rstrip("=")
        )
        url = client.get(
            "/authorize",
            params={
                "client_id": agent["client_id"],
                "response_type": "code",
                "redirect_uri": redirect,
                "scope": "market:read",
                "resource": settings.public_url + "/mcp",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        ).headers["location"]
        page = client.get(url)
        assert redirect in page.text
        assert "Secure;" not in page.headers["set-cookie"]
        request_id = urlparse(url).path.rsplit("/", 1)[-1]
        csrf = client.app.state.provider.pending(request_id)["csrf"]
        assert (
            client.post(
                url,
                data={"csrf": csrf, "password": password},
                headers={"Origin": settings.public_url},
            ).status_code
            == 200
        )


def test_generated_settings_round_trip_without_plaintext_secret(tmp_path, monkeypatch, capsys):
    from dotenv import dotenv_values

    from market_fiyati_mcp.setup import main

    output = tmp_path / "settings.env"
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys, "argv", ["setup", "--auth", "bearer", "--output", str(output)])
    main()
    printed = capsys.readouterr().out
    token = printed.rsplit(": ", 1)[-1].strip()
    values = dotenv_values(output)
    assert values["ACCESS_TOKEN_HASH"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in output.read_text()
    with pytest.raises(FileExistsError):
        main()


def test_oauth_setup_preserves_windows_paths(tmp_path, monkeypatch, capsys):
    from dotenv import dotenv_values

    from market_fiyati_mcp.setup import main

    output = tmp_path / "settings.env"
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup",
            "--auth",
            "oauth",
            "--state-dir",
            r"D:\Application Data\Market",
            "--output",
            str(output),
        ],
    )
    main()
    capsys.readouterr()
    values = dotenv_values(output)
    assert values["STATE_DIR"] == r"D:\Application Data\Market"
    Settings(
        public_url=values["PUBLIC_URL"],
        state_dir=values["STATE_DIR"],
        encryption_key=values["STATE_ENCRYPTION_KEY"],
        owner_password_hash=values["OWNER_PASSWORD_HASH"],
    )


def test_serverless_port_and_safe_bind_are_honored(monkeypatch):
    import uvicorn

    from market_fiyati_mcp.__main__ import main

    calls = []
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("PUBLIC_URL", "https://service.example")
    monkeypatch.setenv("AUTH_MODE", "bearer")
    monkeypatch.setenv("ACCESS_TOKEN_HASH", "ab" * 32)
    monkeypatch.setattr(sys, "argv", ["market-fiyati-mcp", "--transport", "http"])
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    main()
    assert calls[0]["host"] == "0.0.0.0" and calls[0]["port"] == 8080
    assert calls[0]["proxy_headers"] is False


def test_client_config_uses_current_interpreter(monkeypatch, capsys):
    from market_fiyati_mcp.__main__ import main

    monkeypatch.setattr(sys, "argv", ["market-fiyati-mcp", "--client-config"])
    main()
    config = json.loads(capsys.readouterr().out)
    assert config["mcpServers"]["market-fiyati"]["command"] == sys.executable
