"""Verify built containers with real HTTP listeners, no provider searches."""

import base64
import hashlib
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def run(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def probe(port, path="/livez", token=None):
    headers = {}
    data = None
    if path == "/mcp":
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/event-stream"
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        ).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def check(mode, port):
    name = "market-fiyati-check-" + uuid.uuid4().hex[:12]
    volume = name + "-state"
    token = secrets.token_urlsafe(32)
    env = {
        "HOST": "0.0.0.0",
        "PORT": "8080",
        "PUBLIC_URL": f"http://127.0.0.1:{port}",
        "AUTH_MODE": mode,
    }
    if mode == "bearer":
        env["ACCESS_TOKEN_HASH"] = hashlib.sha256(token.encode()).hexdigest()
    else:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(token.encode(), salt=salt, n=16384, r=8, p=1).hex()
        env.update(
            STATE_DIR="/state",
            STATE_ENCRYPTION_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode(),
            OWNER_PASSWORD_HASH=salt.hex() + ":" + digest,
        )
    arguments = [
        "run",
        "-d",
        "--name",
        name,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        "256m",
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:size=16m",
        "-p",
        f"127.0.0.1:{port}:8080",
    ]
    for key, value in env.items():
        arguments.extend(["-e", key + "=" + value])
    if mode == "oauth":
        arguments.extend(["-v", volume + ":/state"])
    arguments.append("market-fiyati-mcp:ci")
    try:
        run(*arguments)
        for _ in range(45):
            try:
                if probe(port)[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Container readiness failed")
        assert probe(port, "/mcp")[0] == 401
        if mode == "bearer":
            status, body = probe(port, "/mcp", token)
            assert status == 200 and len(json.loads(body)["result"]["tools"]) == 3
        # Check the image's health probe uses the non-default PORT, not a fixed port.
        for _ in range(40):
            state = json.loads(run("inspect", "--format", "{{json .State}}", name))
            if state.get("Health", {}).get("Status") == "healthy":
                break
            time.sleep(1)
        else:
            raise RuntimeError("Container health check did not honor PORT")
        print(mode + ": readiness, authentication, filesystem and dynamic port passed")
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, check=False)
        if mode == "oauth":
            subprocess.run(
                ["docker", "volume", "rm", volume], stdout=subprocess.DEVNULL, check=False
            )


if __name__ == "__main__":
    check("bearer", 18080)
    check("oauth", 18081)
