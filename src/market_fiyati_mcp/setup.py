"""Interactive, portable credential setup. Never writes plaintext credentials."""

import argparse
import hashlib
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

from .config import origin, password_hash, state_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth", choices=("bearer", "oauth"), default="bearer")
    parser.add_argument("--public-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state-dir", default=state_directory())
    parser.add_argument("--output", type=Path, default=Path(".env"))
    args = parser.parse_args()
    public_url = origin(args.public_url.rstrip("/"))
    if not sys.stdout.isatty():
        raise SystemExit("Run interactively; credentials are printed once. Do not redirect output.")
    secret = secrets.token_urlsafe(32)
    values = {"AUTH_MODE": args.auth, "PUBLIC_URL": public_url}
    if args.auth == "bearer":
        values["ACCESS_TOKEN_HASH"] = hashlib.sha256(secret.encode()).hexdigest()
    else:
        values.update(
            STATE_DIR=args.state_dir,
            STATE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
            OWNER_PASSWORD_HASH=password_hash(secret),
        )
    # Quote for dotenv, including Windows paths. Refuse overwrites and use private POSIX permissions.
    if any(any(c in value for c in "\r\n\x00") for value in values.values()):
        raise ValueError("Settings must not contain control characters.")
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        for key, value in values.items():
            # Single-quoted dotenv strings preserve literal dollar signs and Windows backslashes.
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            stream.write(key + "='" + escaped + "'\n")
    label = "Bearer token" if args.auth == "bearer" else "Owner password"
    print("Settings created. Protect this file with your OS file permissions; do not commit it.")
    print(label + " (save in your password manager): " + secret)


if __name__ == "__main__":
    main()
