# Containers

Docker can run the server without installing Python on the host. Use Linux
containers on Windows/macOS Docker Desktop or Docker Engine on Linux.

## Build and test

```sh
docker build --target test .
docker build -t market-fiyati-mcp:0.2.0 .
```

The pinned Python base is a multi-architecture image index, including amd64 and
arm64. The standard container CI verifies amd64; other architectures are not
claimed as separately tested.

## Local stdio

```sh
docker run --rm -i market-fiyati-mcp:0.2.0 python -m market_fiyati_mcp
```

An MCP client can use docker as its command with these arguments. Keep -i; omit -t
so terminal output cannot interfere with MCP framing. No published port or volume
is needed for stdio.

## HTTP with a token

From the source checkout, use Python 3.13+ to generate .env:

```sh
python -m pip install .
market-fiyati-mcp-setup --auth bearer
docker compose up --build -d
```

If Python is not available on the host, the container can create settings in a
writable directory. In an interactive terminal:

```sh
docker run --rm -it --user 0:0 --mount type=bind,src=/absolute/path/to/checkout,dst=/config market-fiyati-mcp:0.2.0 python -m market_fiyati_mcp.setup --output /config/.env
```

The root user is used only for writing that setup file through the bind mount.
Runtime remains uid/gid 10001. On Windows, choose a Docker-accessible absolute
source path. Protect the generated file with your host's file permissions.

Compose binds host port 8000 to loopback. HOST=0.0.0.0 is internal to the container.
Bearer mode needs no database volume and works with a read-only filesystem.

For remote HTTPS, generate settings with --public-url YOUR_HTTPS_ORIGIN and configure
the existing reverse proxy/platform. The Caddy example is optional, not required.
MCP_PORT can select another host port without changing the internal listener.

## OAuth with durable state

```sh
market-fiyati-mcp-setup --auth oauth --public-url https://mcp.example.org
docker compose -f compose.yaml -f compose.oauth.yaml up --build -d
```

Generate a new settings file only when no .env exists. The helper refuses overwrites.
The OAuth override adds a named volume and forces the container state path to /state,
regardless of the host operating system.

Keep the database and matching STATE_ENCRYPTION_KEY together in encrypted backups.
Use SQLite's backup API or stop the service before copying the volume. Verify a
restore in an isolated location; do not test by overwriting the running database.

## Runtime limits

Examples cap memory at 256 MiB, CPU at 0.5, PIDs at 128 and /tmp at 16 MiB.
These are starting limits, not measured requirements for every host. Monitor your
workload and provider traffic before scaling.
