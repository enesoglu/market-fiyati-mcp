# Security

The server exposes read-only price tools to MCP clients. It is operator-managed
software, not a multi-user identity/account platform.

## Transport profiles

Stdio inherits local process/SSH access. It opens no inbound listener.
Unauthenticated HTTP is restricted to explicit loopback binding and loopback origins.
Public HTTP requires bearer or OAuth authentication and an advertised HTTPS origin.
A custom domain is optional; a remote IP endpoint still needs trusted TLS.

Host/Origin checks protect the MCP endpoint against DNS rebinding. Forwarded proxy
headers are not trusted by default. Terminate TLS at a configured platform or reverse
proxy, and do not expose an unauthenticated backend port.

Bearer mode stores only a SHA-256 hash of a randomly generated token. Send tokens
in Authorization headers, not URLs. Every holder has the same read-only access.
Rotate the hash and restart to invalidate it. Bearer mode has no persistent state.

## OAuth

The official MCP SDK enforces PKCE, exact registered redirect matching, scopes and
resource binding. The generic callback policy accepts HTTPS and HTTP loopback,
not a list of model vendors. The consent page displays the registered callback
destination; an escaped client display name alone is not proof of identity.

Consent requires a matching Origin, per-request HttpOnly/SameSite cookie, CSRF,
unexpired request and operator password. HTTPS cookies are Secure. Non-Secure
consent cookies are used only for explicitly local HTTP origins.

The password is a salted scrypt hash (N=16384, r=8, p=1). Codes last 60 seconds and
are single-use. Access tokens last one hour. Stable refresh tokens/grants expire
after 90 inactive days; whole-grant revocation is available.

OAuth bodies are Fernet-encrypted and bearer lookup keys are SHA-256 hashes.
Back up the database and matching encryption key together. Restoring an older
database can restore formerly revoked grants. Password changes do not revoke grants.

## Data and limits

Only three fixed provider operations exist. There are no shell, filesystem,
arbitrary URL, purchasing or write tools. Product/store text is untrusted data.
Agent guidance says not to treat it as instructions; this cannot guarantee a model's
resistance to prompt injection.

Caches contain queries and optional locations in process memory until eviction/
restart. The application does not access-log them. Upstream and hosting providers
have their own data-handling policies. Authentication URLs can include codes;
configure external proxies to avoid logging sensitive authorization parameters.

Request budgets, response limits and container limits bound ordinary abuse but
do not replace network-level denial-of-service protection. Budgets are per process.
The credential helper refuses overwrites and does not save plaintext credentials.
Do not commit .env, state databases, tokens, passwords or private keys.

## Reporting

Use GitHub private vulnerability reporting when available, or contact the repository
maintainer privately. Do not publish live credentials or personal queries in a report.
