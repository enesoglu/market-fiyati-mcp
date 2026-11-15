"""Owner-bound OAuth grants for the official MCP SDK."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class Store:
    def __init__(self, directory, key):
        path = Path(directory)
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = path / "oauth.db"
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS entries(kind TEXT, id TEXT, body BLOB NOT NULL, expires REAL, PRIMARY KEY(kind,id))"
            )
            db.execute("CREATE INDEX IF NOT EXISTS expiry ON entries(expires)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, key, body, expires=None):
        encrypted = self.cipher.encrypt(json.dumps(body, separators=(",", ":")).encode())
        with self.connect() as db:
            db.execute(
                "DELETE FROM entries WHERE expires IS NOT NULL AND expires < ?", (time.time(),)
            )
            db.execute(
                "INSERT OR REPLACE INTO entries VALUES(?,?,?,?)", (kind, key, encrypted, expires)
            )

    def get(self, kind, key, consume=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE" if consume else "BEGIN")
            row = db.execute(
                "SELECT body,expires FROM entries WHERE kind=? AND id=?", (kind, key)
            ).fetchone()
            if not row:
                return None
            if consume or (row[1] and row[1] < time.time()):
                db.execute("DELETE FROM entries WHERE kind=? AND id=?", (kind, key))
            if row[1] and row[1] < time.time():
                return None
        return json.loads(self.cipher.decrypt(row[0]))

    def delete(self, kind, key):
        with self.connect() as db:
            db.execute("DELETE FROM entries WHERE kind=? AND id=?", (kind, key))

    def count(self, kind):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM entries WHERE kind=?", (kind,)).fetchone()[0]


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def allowed_redirect(value):
    from .config import loopback

    raw = str(value)
    try:
        url = urlparse(raw)
        return bool(
            len(raw) <= 2048
            and url.hostname
            and not url.username
            and not url.password
            and not url.fragment
            and url.port != 0
            and (url.scheme == "https" or url.scheme == "http" and loopback(url.hostname))
            and not any(c.isspace() or c in "\\\x00" for c in raw)
            and not any(c in raw.lower() for c in ("%0a", "%0d", "%00"))
        )
    except ValueError:
        return False


class OwnerOAuth(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, store, public_base, owner_id):
        self.store = store
        self.base = public_base.rstrip("/")
        self.resource = self.base + "/mcp"
        self.owner = owner_id

    async def get_client(self, client_id):
        data = self.store.get("client", client_id)
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def register_client(self, client_info):
        if self.store.count("client") >= 1000:
            raise RegistrationError(
                error="invalid_client_metadata", error_description="Registration capacity reached"
            )
        if len(client_info.client_name or "") > 100 or len(client_info.redirect_uris or []) > 10:
            raise RegistrationError(
                error="invalid_client_metadata", error_description="Client metadata too large"
            )
        if not client_info.redirect_uris or not all(
            allowed_redirect(u) for u in client_info.redirect_uris
        ):
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="Use an HTTPS callback or an HTTP loopback callback without credentials or fragments",
            )
        if set(client_info.grant_types) - {"authorization_code", "refresh_token"}:
            raise RegistrationError(
                error="invalid_client_metadata", error_description="Unsupported grant type"
            )
        if client_info.token_endpoint_auth_method not in (
            "none",
            "client_secret_post",
            "client_secret_basic",
        ):
            raise RegistrationError(
                error="invalid_client_metadata",
                error_description="Unsupported client authentication",
            )
        self.store.put("client", client_info.client_id, client_info.model_dump(mode="json"))

    async def authorize(self, client, params):
        if params.resource and params.resource.rstrip("/") != self.resource:
            raise AuthorizeError(error="invalid_request", error_description="Wrong resource")
        if not allowed_redirect(params.redirect_uri):
            raise AuthorizeError(
                error="invalid_request", error_description="Callback is not allowed"
            )
        if set(params.scopes or ["market:read"]) - {"market:read"}:
            raise AuthorizeError(error="invalid_scope", error_description="Unsupported scope")
        if self.store.count("pending") >= 1000:
            raise AuthorizeError(
                error="temporarily_unavailable", error_description="Consent capacity reached"
            )
        request_id = secrets.token_urlsafe(32)
        self.store.put(
            "pending",
            request_id,
            {
                "client": client.client_id,
                "params": params.model_dump(mode="json"),
                "csrf": secrets.token_urlsafe(32),
            },
            time.time() + 600,
        )
        return self.base + "/consent/" + request_id

    def pending(self, request_id):
        return self.store.get("pending", request_id)

    def approve(self, request_id, csrf):
        pending = self.store.get("pending", request_id, consume=True)
        if not pending or not hmac.compare_digest(pending["csrf"], csrf):
            raise ValueError("Consent expired or invalid")
        params = AuthorizationParams.model_validate(pending["params"])
        grant_id = secrets.token_urlsafe(24)
        self.store.put(
            "grant",
            grant_id,
            {"client": pending["client"], "owner": self.owner},
            time.time() + 90 * 86400,
        )
        code = secrets.token_urlsafe(32)
        model = AuthorizationCode(
            code=code,
            client_id=pending["client"],
            scopes=params.scopes or ["market:read"],
            expires_at=time.time() + 60,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self.resource,
            subject=self.owner,
        )
        self.store.put(
            "code",
            fingerprint(code),
            {"model": model.model_dump(mode="json", exclude={"code"}), "grant": grant_id},
            model.expires_at,
        )
        return code, params

    async def load_authorization_code(self, client, authorization_code):
        data = self.store.get("code", fingerprint(authorization_code))
        if not data or data["model"]["client_id"] != client.client_id:
            return None
        return AuthorizationCode(code=authorization_code, **data["model"])

    def _access(self, client_id, grant_id, scopes):
        token = secrets.token_urlsafe(48)
        expiry = int(time.time()) + 3600
        model = AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expiry,
            resource=self.resource,
            subject=self.owner,
            claims={"grant_id": grant_id, "iss": self.base},
        )
        self.store.put(
            "access",
            fingerprint(token),
            {"model": model.model_dump(mode="json", exclude={"token"}), "grant": grant_id},
            expiry,
        )
        return token

    async def exchange_authorization_code(self, client, authorization_code):
        data = self.store.get("code", fingerprint(authorization_code.code), consume=True)
        if (
            not data
            or data["model"]["client_id"] != client.client_id
            or not self.store.get("grant", data["grant"])
        ):
            raise TokenError(
                error="invalid_grant",
                error_description="Authorization code already used or revoked",
            )
        grant_id = data["grant"]
        refresh = secrets.token_urlsafe(48)
        model = RefreshToken(
            token=refresh,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 90 * 86400,
            resource=self.resource,
            subject=self.owner,
        )
        self.store.put(
            "refresh",
            fingerprint(refresh),
            {"model": model.model_dump(mode="json", exclude={"token"}), "grant": grant_id},
            model.expires_at,
        )
        return OAuthToken(
            access_token=self._access(client.client_id, grant_id, model.scopes),
            token_type="Bearer",
            expires_in=3600,
            refresh_token=refresh,
            scope=" ".join(model.scopes),
        )

    async def load_refresh_token(self, client, refresh_token):
        data = self.store.get("refresh", fingerprint(refresh_token))
        if (
            not data
            or data["model"]["client_id"] != client.client_id
            or not self.store.get("grant", data["grant"])
        ):
            return None
        return RefreshToken(token=refresh_token, **data["model"])

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        data = self.store.get("refresh", fingerprint(refresh_token.token))
        if (
            not data
            or data["model"]["client_id"] != client.client_id
            or not self.store.get("grant", data["grant"])
        ):
            raise TokenError(error="invalid_grant", error_description="Refresh token revoked")
        if not set(scopes) <= set(refresh_token.scopes):
            raise TokenError(error="invalid_scope", error_description="Scope escalation denied")
        # Stable refresh tokens support persistent-link clients; whole-grant revocation remains available.
        data["model"]["expires_at"] = int(time.time()) + 90 * 86400
        grant = self.store.get("grant", data["grant"])
        self.store.put("grant", data["grant"], grant, data["model"]["expires_at"])
        self.store.put(
            "refresh", fingerprint(refresh_token.token), data, data["model"]["expires_at"]
        )
        return OAuthToken(
            access_token=self._access(client.client_id, data["grant"], scopes),
            token_type="Bearer",
            expires_in=3600,
            refresh_token=refresh_token.token,
            scope=" ".join(scopes),
        )

    async def load_access_token(self, token):
        data = self.store.get("access", fingerprint(token))
        if not data or not self.store.get("grant", data["grant"]):
            return None
        return AccessToken(token=token, **data["model"])

    async def revoke_token(self, token):
        kind = "access" if isinstance(token, AccessToken) else "refresh"
        data = self.store.get(kind, fingerprint(token.token))
        if data:
            # All access and refresh tokens for this grant become unusable immediately.
            self.store.delete("grant", data["grant"])
            self.store.delete(kind, fingerprint(token.token))
