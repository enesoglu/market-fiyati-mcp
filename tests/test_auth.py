import base64
import hashlib
import html
import re
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from market_fiyati_mcp.client import MarketClient
from market_fiyati_mcp.config import Settings, password_hash, verify_password
from market_fiyati_mcp.oauth import fingerprint
from market_fiyati_mcp.server import build_app

BASE = "https://market.example.org"
REDIRECT = "https://agent.example.org/oauth/callback"
PASSWORD = "test-only-password-with-enough-entropy"


class Flow:
    def __init__(self, app, client):
        self.app, self.client = app, client

    def register(self, redirect=REDIRECT, auth="none"):
        response = self.client.post(
            "/register",
            json={
                "client_name": "Test agent",
                "redirect_uris": [redirect],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": auth,
                "scope": "market:read",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def begin(self, agent, resource=BASE + "/mcp"):
        verifier = "x" * 64
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        response = self.client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": agent["client_id"],
                "redirect_uri": agent["redirect_uris"][0],
                "scope": "market:read",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "state-123",
                "resource": resource,
            },
        )
        return response.headers["location"], verifier

    def approve(self, url, password=PASSWORD):
        page = self.client.get(url)
        assert page.status_code == 200
        request_id = url.rsplit("/", 1)[-1]
        csrf = self.app.state.provider.pending(request_id)["csrf"]
        return self.client.post(
            url, data={"csrf": csrf, "password": password}, headers={"Origin": BASE}
        )

    def code(self, agent):
        url, verifier = self.begin(agent)
        response = self.approve(url)
        assert response.status_code == 200, response.text
        target = html.unescape(re.search("id='return-to-client' href='([^']+)'", response.text)[1])
        query = parse_qs(urlparse(target).query)
        assert query["state"] == ["state-123"]
        return query["code"][0], verifier

    def token(self, agent, code, verifier, redirect=None):
        form = {
            "grant_type": "authorization_code",
            "client_id": agent["client_id"],
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect or agent["redirect_uris"][0],
            "resource": BASE + "/mcp",
        }
        if agent.get("client_secret"):
            form["client_secret"] = agent["client_secret"]
        return self.client.post("/token", data=form)

    def grant(self, agent=None):
        agent = agent or self.register()
        code, verifier = self.code(agent)
        response = self.token(agent, code, verifier)
        assert response.status_code == 200, response.text
        return agent, response.json()

    def rpc(self, token, method="tools/list", params=None):
        return self.client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        )


@pytest.fixture
def flow(tmp_path):
    settings = Settings(
        BASE, str(tmp_path), Fernet.generate_key().decode(), password_hash(PASSWORD)
    )

    def upstream(_request):
        return httpx.Response(200, json={"content": [], "numberOfFound": 0})

    app = build_app(settings, MarketClient(transport=httpx.MockTransport(upstream)))
    with TestClient(app, base_url=BASE, follow_redirects=False) as client:
        result = Flow(app, client)
        result.settings = settings
        yield result


def test_discovery_and_anonymous_denial(flow):
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
        "/livez",
    ):
        assert flow.client.get(path).status_code == 200
    response = flow.client.post("/mcp", json={})
    assert response.status_code == 401
    assert "resource_metadata" in response.headers["www-authenticate"]


@pytest.mark.parametrize(
    "url",
    [
        "http://agent.example.org/callback",
        "javascript:alert(1)",
        "https://user:password@agent.example.org/cb",
        "https://agent.example.org/cb#fragment",
        "http://192.0.2.1/callback",
        "https://agent.example.org:99999/cb",
        "https://agent.example.org/cb%0d%0aheader",
    ],
)
def test_redirect_restrictions(flow, url):
    assert flow.client.post("/register", json={"redirect_uris": [url]}).status_code == 400


@pytest.mark.parametrize(
    "redirect",
    [
        REDIRECT,
        "https://another-client.example.net/return",
        "http://127.0.0.1:39123/callback",
    ],
)
def test_supported_clients_and_tool_call(flow, redirect):
    _, tokens = flow.grant(flow.register(redirect))
    response = flow.rpc(tokens["access_token"])
    tools = response.json()["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "search_products",
        "find_product",
        "find_similar_products",
    }
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    result = flow.rpc(
        tokens["access_token"],
        "tools/call",
        {
            "name": "search_products",
            "arguments": {"keywords": "süt"},
        },
    ).json()["result"]
    assert not result.get("isError")
    assert "total_matches_reported" in str(result)


def test_csrf_origin_and_password_required(flow):
    url, _ = flow.begin(flow.register())
    flow.client.get(url)
    request_id = url.rsplit("/", 1)[-1]
    csrf = flow.app.state.provider.pending(request_id)["csrf"]
    for origin, supplied in [(BASE, "wrong"), ("https://evil.example", csrf)]:
        response = flow.client.post(
            url, data={"csrf": supplied, "password": PASSWORD}, headers={"Origin": origin}
        )
        assert response.status_code == 403
    assert flow.approve(url, "wrong-password").status_code == 403
    assert flow.app.state.store.count("grant") == 0
    assert flow.approve(url).status_code == 200


def test_parallel_consent_and_html_policy(flow):
    urls = [flow.begin(flow.register())[0] for _ in range(2)]
    for url in urls:
        page = flow.client.get(url)
        assert "form-action 'self'" in page.headers["content-security-policy"]
        assert "no-transform" in page.headers["cache-control"]
        assert page.headers["referrer-policy"] == "same-origin"
    for url in urls:
        response = flow.approve(url)
        assert response.status_code == 200
        assert "location.replace(" in response.text
        assert response.headers["referrer-policy"] == "no-referrer"


def test_pkce_redirect_and_single_use(flow):
    agent = flow.register()
    code, verifier = flow.code(agent)
    assert flow.token(agent, code, "wrong").status_code == 400
    assert flow.token(agent, code, verifier, "https://evil.example").status_code == 400
    assert flow.token(agent, code, verifier).status_code == 200
    assert flow.token(agent, code, verifier).status_code == 400


def test_refresh_and_revoke_invalidates_all_access(flow):
    agent, tokens = flow.grant()
    form = {
        "grant_type": "refresh_token",
        "client_id": agent["client_id"],
        "refresh_token": tokens["refresh_token"],
    }
    refreshed = flow.client.post("/token", data=form)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"] == tokens["refresh_token"]
    access = refreshed.json()["access_token"]
    assert flow.rpc(access).status_code == 200
    assert (
        flow.client.post(
            "/revoke",
            data={
                "client_id": agent["client_id"],
                "token": tokens["refresh_token"],
            },
        ).status_code
        == 200
    )
    assert flow.rpc(access).status_code == 401
    assert flow.rpc(tokens["access_token"]).status_code == 401
    assert flow.client.post("/token", data=form).status_code == 400


def test_client_binding_scope_and_audience(flow):
    agent, tokens = flow.grant()
    other = flow.register()
    for client_id, scope in [(other["client_id"], "market:read"), (agent["client_id"], "admin")]:
        response = flow.client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": tokens["refresh_token"],
                "scope": scope,
            },
        )
        assert response.status_code == 400
    key = fingerprint(tokens["access_token"])
    data = flow.app.state.store.get("access", key)
    data["model"]["resource"] = "https://other.example/mcp"
    flow.app.state.store.put("access", key, data, time.time() + 60)
    assert flow.rpc(tokens["access_token"]).status_code in (401, 403)


def test_wrong_resource_authorization(flow):
    url, _ = flow.begin(flow.register(), "https://other.example/mcp")
    assert parse_qs(urlparse(url).query)["error"] == ["invalid_request"]


def test_confidential_client_secret(flow):
    agent, tokens = flow.grant(flow.register(auth="client_secret_post"))
    form = {"client_id": agent["client_id"], "token": tokens["refresh_token"]}
    assert flow.client.post("/revoke", data=form).status_code == 401
    form["client_secret"] = agent["client_secret"]
    assert flow.client.post("/revoke", data=form).status_code == 200


def test_encrypted_state_expiration_and_restart(flow):
    _, tokens = flow.grant()
    from pathlib import Path

    for file in Path(flow.settings.state_dir).glob("oauth.db*"):
        content = file.read_bytes()
        assert tokens["access_token"].encode() not in content
        assert tokens["refresh_token"].encode() not in content
        assert PASSWORD.encode() not in content
    other_app = build_app(
        flow.settings,
        MarketClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"content": [], "numberOfFound": 0})
            )
        ),
    )
    with TestClient(other_app, base_url=BASE) as client:
        assert Flow(other_app, client).rpc(tokens["access_token"]).status_code == 200
    key = fingerprint(tokens["access_token"])
    data = flow.app.state.store.get("access", key)
    flow.app.state.store.put("access", key, data, time.time() - 1)
    assert flow.rpc(tokens["access_token"]).status_code == 401


def test_body_and_registration_rate_limits(flow):
    assert flow.client.post("/register", content=b"x" * 17000).status_code == 413
    for _ in range(10):
        flow.register()
    assert flow.client.post("/register", json={}).status_code == 429


def test_unknown_tool_is_not_executable(flow):
    _, tokens = flow.grant()
    response = flow.rpc(tokens["access_token"], "tools/call", {"name": "execute", "arguments": {}})
    assert response.json()["result"]["isError"]


def test_password_hashing_and_configuration():
    hashed = password_hash(PASSWORD)
    assert verify_password(PASSWORD, hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("x" * 257, hashed)
    assert not verify_password("anything", "invalid")
    for url in ("http://example.org", "https://example.org/path", "https://user:pass@example.org"):
        with pytest.raises(ValueError):
            Settings(url, "/state", Fernet.generate_key().decode(), hashed)
