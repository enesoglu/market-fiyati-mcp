# Contributing

The project exposes read-only grocery price tools through standard MCP transports.
Keep provider behavior independent of authentication, operating system and hosting.

## Development

Use Python 3.13+ in an isolated environment:

```sh
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
ruff check .
ruff format --check .
pytest --cov=market_fiyati_mcp --cov-report=term-missing
docker build --target test .
```

CI exercises Windows, macOS, Linux and a Linux container. The container test stage
has networking disabled. The default suite uses injected provider responses.
scripts/smoke.py is an explicit live operator check, not part of the offline suite.

Add behavioral tests when changing authentication, resource limits, configuration,
provider contracts or error handling. Preserve explicit provider failures and avoid
treating fuzzy matches as exact identities.

Document supported behavior and practical limitations. Do not promise compatibility
with every client UI or a cloud deployment that has not actually been tested.
Installation examples should use reserved documentation addresses and no real
deployment/account details.

Never commit settings files, tokens, passwords, user locations or production state.
Report security issues as described in SECURITY.md.
