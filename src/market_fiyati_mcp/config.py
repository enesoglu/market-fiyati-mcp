"""Portable runtime configuration and credential validation."""

import hashlib
import hmac
import ipaddress
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def origin(value: str) -> str:
    """Accept HTTPS hostnames or IPs, and HTTP only for explicit loopback addresses."""
    try:
        url = urlsplit(value)
        valid = (
            url.hostname
            and not url.username
            and not url.password
            and not url.path
            and not url.query
            and not url.fragment
            and "?" not in value
            and "#" not in value
            and (url.scheme == "https" or url.scheme == "http" and loopback(url.hostname))
            and not any(c.isspace() or c in "\\\x00" for c in value)
        )
        if url.port is not None and not 1 <= url.port <= 65535:
            valid = False
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Use an HTTPS origin (hostname or IP), or HTTP on localhost/loopback.")
    return urlunsplit((url.scheme, url.netloc.lower(), "", "", ""))


def state_directory() -> str:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return str(root / "market-fiyati-mcp")


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ":" + digest.hex()


def verify_password(password: str, encoded: str) -> bool:
    if not 1 <= len(password) <= 256:
        return False
    try:
        salt, expected = encoded.split(":")
        return hmac.compare_digest(password_hash(password, salt).split(":")[1], expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True, repr=False)
class Settings:
    public_url: str = "http://127.0.0.1:8000"
    state_dir: str = ""
    encryption_key: str = ""
    owner_password_hash: str = ""
    auth_mode: str = "oauth"
    access_token_hash: str = ""
    host: str = "127.0.0.1"
    port: int = 8000

    def __post_init__(self):
        object.__setattr__(self, "public_url", origin(self.public_url))
        if self.auth_mode not in ("none", "bearer", "oauth"):
            raise ValueError("AUTH_MODE must be none, bearer or oauth.")
        if not 1 <= self.port <= 65535:
            raise ValueError("PORT must be between 1 and 65535.")
        if self.auth_mode == "none":
            if not loopback(self.host) or not loopback(urlsplit(self.public_url).hostname):
                raise ValueError(
                    "Unauthenticated HTTP is restricted to loopback; use bearer or OAuth remotely."
                )
        if self.auth_mode == "bearer":
            try:
                if (
                    len(self.access_token_hash) != 64
                    or len(bytes.fromhex(self.access_token_hash)) != 32
                ):
                    raise ValueError
            except ValueError:
                raise ValueError("ACCESS_TOKEN_HASH must be a SHA-256 hex digest.") from None
        object.__setattr__(self, "access_token_hash", self.access_token_hash.lower())
        if self.auth_mode == "oauth":
            salt, digest = self.owner_password_hash.split(":")
            if len(bytes.fromhex(salt)) != 16 or len(bytes.fromhex(digest)) != 64:
                raise ValueError("OWNER_PASSWORD_HASH is not a valid scrypt hash.")
            from cryptography.fernet import Fernet

            Fernet(self.encryption_key.encode())
            if not self.state_dir:
                raise ValueError("STATE_DIR is required for persistent OAuth state.")

    @classmethod
    def from_env(cls):
        host = os.environ.get("HOST", "127.0.0.1")
        port = int(os.environ.get("PORT", "8000"))
        local_host = "[" + host + "]" if ":" in host else host
        default_url = (
            f"http://{local_host}:{port}" if loopback(host) else "http://127.0.0.1:" + str(port)
        )
        return cls(
            public_url=os.environ.get("PUBLIC_URL", default_url).rstrip("/"),
            state_dir=os.environ.get("STATE_DIR", state_directory()),
            encryption_key=os.environ.get("STATE_ENCRYPTION_KEY", ""),
            owner_password_hash=os.environ.get("OWNER_PASSWORD_HASH", ""),
            auth_mode=os.environ.get("AUTH_MODE", "none"),
            access_token_hash=os.environ.get("ACCESS_TOKEN_HASH", ""),
            host=host,
            port=port,
        )
