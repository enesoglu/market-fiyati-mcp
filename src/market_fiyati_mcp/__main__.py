"""Market Fiyatı MCP: local stdio or configurable Streamable HTTP."""

import argparse
import os
import sys
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from .client import MarketClient
from .server import INSTRUCTIONS
from .tools import register_tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", help="HTTP bind address; default: HOST or 127.0.0.1")
    parser.add_argument("--port", type=int, help="HTTP port; default: PORT or 8000")
    parser.add_argument(
        "--auth", choices=("none", "bearer", "oauth"), help="HTTP authentication mode"
    )
    parser.add_argument(
        "--env-file", help="Load explicitly chosen settings; existing environment wins"
    )
    parser.add_argument(
        "--client-config", action="store_true", help="Print a stdio client configuration"
    )
    args = parser.parse_args()
    if args.client_config:
        import json

        print(
            json.dumps(
                {
                    "mcpServers": {
                        "market-fiyati": {
                            "command": sys.executable,
                            "args": ["-m", "market_fiyati_mcp"],
                        }
                    }
                },
                indent=2,
            )
        )
        return
    if args.env_file:
        from dotenv import load_dotenv

        if not os.path.isfile(args.env_file):
            parser.error("--env-file does not exist.")
        load_dotenv(args.env_file, override=False)
    for name in ("host", "port", "auth"):
        value = getattr(args, name)
        if value is not None:
            os.environ["AUTH_MODE" if name == "auth" else name.upper()] = str(value)
    if args.transport == "http":
        import uvicorn

        from .config import Settings

        settings = Settings.from_env()  # Validate before opening a listening socket.
        uvicorn.run(
            "market_fiyati_mcp.server:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            access_log=False,
            log_level="warning",
            limit_concurrency=24,
            timeout_keep_alive=5,
            proxy_headers=False,
        )
    else:
        client = MarketClient()

        @asynccontextmanager
        async def lifespan(_server):
            try:
                yield
            finally:
                await client.close()

        mcp = MCPServer(
            "Market Fiyatı",
            version="0.2.0",
            instructions=INSTRUCTIONS,
            lifespan=lifespan,
            log_level="WARNING",
        )
        register_tools(mcp, client)
        mcp.run()


if __name__ == "__main__":
    main()
