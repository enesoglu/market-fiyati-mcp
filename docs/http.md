# HTTP connections

The endpoint uses MCP Streamable HTTP at /mcp. A raw LLM API is not an MCP client;
use a client or agent framework that supports this transport.

## Same computer: no credentials or domain

```sh
market-fiyati-mcp --transport http
```

Connect to http://127.0.0.1:8000/mcp. The default binds only 127.0.0.1 and rejects
unauthenticated nonlocal binding. Use --port to choose another local port.

The local endpoint validates Origin and Host to protect against DNS rebinding.
A client with no Origin header can connect; a browser with an unrelated Origin cannot.

## A different machine, without a domain

Two options avoid a custom domain:

1. Use stdio over SSH, as described in the local guide.
2. Keep HTTP bound to loopback on the remote machine and create a tunnel:

```sh
ssh -N -L 8000:127.0.0.1:8000 user@192.0.2.10
```

The client still connects to http://127.0.0.1:8000/mcp. The transport between machines
is protected by SSH. Replace the documentation IP and login with your own.
A web-hosted client generally cannot reach your computer's loopback address; it
needs a publicly reachable HTTPS endpoint.

## Public endpoint: bearer token

Generate settings interactively:

```sh
market-fiyati-mcp-setup --auth bearer --public-url https://192.0.2.10:8443
market-fiyati-mcp --transport http --env-file .env
```

Use an HTTPS endpoint with a certificate your client trusts. That can be an IP with
a matching IP certificate, a provider-supplied HTTPS hostname, or your own domain.
A raw public IP does not remove the need for trusted TLS.

The server itself speaks HTTP; terminate TLS at a reverse proxy/platform. It binds
to loopback unless --host/HOST is explicitly changed. Configure the client to send:

```text
Authorization: Bearer <generated-token>
```

Enter the token into the client's secure credential field. Tokens in URL query
parameters are not accepted. Only a hash is stored on the server. Rotate the token
hash and restart/redeploy to invalidate all clients sharing it.

## Public endpoint: OAuth

```sh
market-fiyati-mcp-setup --auth oauth --public-url https://mcp.example.org
market-fiyati-mcp --transport http --env-file .env
```

Use this profile for clients that support OAuth discovery and automatic registration.
The operator enters the generated password on the server's consent page.
No model-vendor allowlist exists. HTTPS callbacks and desktop loopback callbacks
are supported; registered redirects and PKCE are validated.

The consent screen shows the callback destination. Treat client names as untrusted.
OAuth needs persistent state and is intended for one operator authorizing their
clients, not an account/signup service.

OAuth on an HTTP loopback origin is also supported for local integrations. Public
plaintext HTTP origins are rejected. See configuration.md for all settings.

## Client support

A client must support the selected transport and authentication method. Supporting
MCP does not imply support for every transport or OAuth feature. The test suite
checks the protocol implementation; verify real tool execution in your chosen client.
