# Configuration

Stdio uses none of the HTTP settings. HTTP reads environment variables and an
optional explicitly selected --env-file. Existing environment variables take
precedence over file values; command-line host/port/auth flags take precedence over both.

| Setting | Default | Meaning |
| --- | --- | --- |
| HOST | 127.0.0.1 | Listener bind address; containers/platforms explicitly use 0.0.0.0 |
| PORT | 8000 | Listener port; managed platforms may supply it |
| AUTH_MODE | none | none (loopback only), bearer, or oauth |
| PUBLIC_URL | Local loopback origin | Advertised origin; HTTPS hostname/IP or HTTP loopback |
| ACCESS_TOKEN_HASH | unset | SHA-256 digest of a random bearer token; bearer mode |
| STATE_DIR | OS-specific user state directory | Durable encrypted OAuth database directory |
| STATE_ENCRYPTION_KEY | unset | Fernet key; required for OAuth |
| OWNER_PASSWORD_HASH | unset | Salted scrypt password hash; required for OAuth |

PUBLIC_URL is an origin without a path, query or embedded credentials. Custom HTTPS
ports and IPv6 literals are supported. /mcp is appended by the server.

The credential helper creates a private .env and prints a random token/password
once. It refuses to overwrite files. On POSIX systems it requests mode 0600; on
Windows also protect the file using the account/directory ACL. Neither plaintext
token nor plaintext operator password is written to the settings file.

OAuth defaults to the user's local state directory:
Windows LOCALAPPDATA, macOS Library/Application Support, or Linux XDG_STATE_HOME /
.local/state. Choose a durable explicit path for hosted installations. Container
OAuth examples use a named volume at /state.

## CLI

```text
market-fiyati-mcp
market-fiyati-mcp --client-config
market-fiyati-mcp --transport http
market-fiyati-mcp --transport http --port 9000
market-fiyati-mcp --transport http --env-file /path/to/settings.env
market-fiyati-mcp-setup --auth bearer --public-url https://192.0.2.10:8443
market-fiyati-mcp-setup --auth oauth --public-url https://mcp.example.org
```

## Revoke or rotate

Bearer mode: replace ACCESS_TOKEN_HASH with the hash of a newly generated token
and restart/redeploy. All clients using the previous shared token lose access.

OAuth mode: use the standard revoke endpoint through the client where supported.
Revoking either credential invalidates the entire grant. An operator can revoke
all grants by deleting grant records from the state database using SQLite:

```sql
DELETE FROM entries WHERE kind = 'grant';
```

Changing the operator password does not revoke existing grants. Keep the encryption
key unchanged when only rotating the password; restoring OAuth state requires its
matching key. Never edit production state through an MCP tool.
