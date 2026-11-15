# Architecture

## Data flow

A client connects through stdio or Streamable HTTP and invokes one of three tools.
The tools delegate to a shared asynchronous price client. That module owns input
validation, the fixed upstream operations, retry policy, cache and result conversion.

The server does not run an LLM. A model uses it through an MCP client or agent runtime.
There is no model-vendor allowlist.

| Module | Responsibility |
| --- | --- |
| client.py | Provider requests, validation, budgets, cache and normalized results |
| tools.py | MCP tool schemas and read-only annotations |
| config.py | Portable settings and safe network defaults |
| server.py | HTTP transport, authentication profiles and consent routes |
| oauth.py | Encrypted grant state, client binding, expiry and revocation |
| setup.py | Optional interactive credential/configuration generation |
| __main__.py | Command-line entrypoint and local client configuration |

HTTP transport has three authentication profiles:

- **none:** local loopback only; no credentials or persistent state.
- **bearer:** operator-configured token hash; no database or writable disk.
- **oauth:** dynamic registration, browser consent and encrypted persistent SQLite state.

Stdio requires no HTTP settings or OAuth credentials. The client owns the local
process. It is suitable for desktop clients and SSH-launched processes.

## Provider contract

The fixed POST operations are search, searchByIdentity and searchSmilarProduct.
The final spelling follows the upstream interface. Product identity/barcode lookup
is distinct from name search and suggested alternatives.

Prices are decimal strings in TRY. Products retain package quantity and unit.
The output includes at most 25 products and 20 offers per product, with explicit
truncation flags and provider-reported counts. No unsupported pagination is invented.

fetched_at is the server's UTC retrieval time. provider_updated_at is unmodified
provider metadata, which may use a different format/timezone. Neither guarantees
checkout availability or complete retailer coverage.

Location filters require all three fields together: latitude, longitude and
radius in meters (100–50000). No IP geolocation is performed.

## Failure and capacity policy

- Provider timeout: 10 seconds; connect timeout: 5 seconds.
- Whole query, including waiting for another cache miss: 25 seconds.
- At most one 250 ms retry for network failures or HTTP 502/503/504.
- No retry for provider rate limiting, authorization errors or invalid data.
- 30 outbound attempts per minute **per process**, including retries.
- One active cache miss, coalescing concurrent identical requests.
- 120-second cache, at most 64 keys / 8 MiB of serialized provider responses.
- At most 1 MiB of decompressed provider response and 16 KiB of incoming HTTP body.

Provider failures are tool errors. Successful zero-result searches are normal
responses. A previously cached success can be used until its TTL expires during
an outage; cache status and original retrieval time remain visible.

The cache is process-local and includes query/location keys in memory. Restart
clears it. Multiple instances have separate caches and request budgets. Use platform
instance limits to control aggregate provider traffic.

## OAuth interoperability

Registration accepts valid HTTPS callbacks and HTTP loopback callbacks for desktop
clients, with exact registered redirect matching and PKCE enforced by the SDK.
No client-brand URLs are hard-coded. Arbitrary remote plaintext HTTP callbacks,
credentials in URLs, fragments and unsafe schemes are rejected.

The consent screen displays the registered callback destination and escaped client
name. A display name is not proof of identity; the operator must inspect the request.
Consent requires an operator password, per-request cookie, matching Origin and CSRF.

Codes expire after 60 seconds and are single-use. Access tokens last one hour.
Refresh tokens and their grants expire after 90 inactive days. Refresh token values
remain stable for persistent-link clients; this trades rotation for interoperability.
Whole-grant revocation invalidates all associated credentials.

OAuth record bodies are Fernet-encrypted; bearer lookup keys are SHA-256 hashes.
SQLite and its matching encryption key must be restored together. SQLite OAuth mode
requires durable single-host storage. Stateless bearer mode is the default container
choice for platforms with disposable filesystems.

## Deployment seam

The executable reads HOST and PORT rather than assuming a specific host layout.
PUBLIC_URL is an HTTPS origin (hostname or IP) or an HTTP loopback origin.
Container TLS is normally terminated by the selected reverse proxy/platform.

Core behavior does not depend on a cloud provider, operating-system service manager,
backup provider, notification channel or pre-existing application.

## References

- [MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [Official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Market Fiyatı](https://marketfiyati.org.tr/)

## Acknowledgements

The community [market-fiyati-mcp-server](https://github.com/mehmetcanbozkus/market-fiyati-mcp-server)
helped identify the upstream operation names. Its source is not vendored.
