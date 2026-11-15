# Cloud hosting

The same container can run on a virtual machine, a container host or a managed
HTTP container platform. No custom domain, specific service manager or particular
backup provider is required.

## Hosting contract

- Run one HTTP process with HOST=0.0.0.0 and the platform's PORT.
- Publish a trusted HTTPS origin and set PUBLIC_URL to that origin.
- Configure AUTH_MODE=bearer and ACCESS_TOKEN_HASH using protected settings/secrets.
- Forward /mcp and, if selected, the OAuth/discovery/consent routes unchanged.
- Allow outbound HTTPS to the price provider.
- Use /livez for local process readiness; monitor provider availability separately.

Bearer mode is stateless and needs no writable disk. The token hash must be the
same across instances. Cache and provider budgets are per process, so cap instance
count to control aggregate load.

OAuth uses SQLite and must have durable single-host storage. Disposable container
filesystems and multiple independent SQLite replicas are unsuitable for persistent
OAuth grants. Use bearer mode on a stateless platform or choose a host with an
appropriate durable disk.

## Example: Google Cloud Run

Cloud Run supplies an HTTPS URL and PORT; no custom domain is needed.
The deploy script only runs when you invoke it with your own cloud credentials.
It does not create a project, billing account, registry or secret.

Prerequisites:

1. Build and push the container to an image registry your project can access.
2. Generate bearer settings locally and save the token securely.
3. Store the ACCESS_TOKEN_HASH value in Secret Manager, and grant the runtime
   service account access to that secret.
4. Install/authenticate the cloud CLI and choose an existing project/region.

Then run:

```sh
sh deploy/cloud-run.sh PROJECT REGION IMAGE_URL TOKEN_HASH_SECRET
```

The script deploys privately first, obtains the platform URL, updates PUBLIC_URL,
then enables public platform invocation. Application bearer authentication remains
required. This is necessary for ordinary external MCP clients that do not send a
separate cloud IAM identity token.

No credentials or real cloud project values are part of the script. It uses 256 MiB,
one CPU, request concurrency 24, a 60-second platform timeout and at most three
instances. Review those choices for your provider budget.

## Other platforms

Use the same hosting contract for a managed container host, Kubernetes or an ordinary
machine. Kubernetes should use Secret references and a Deployment/Service/Ingress;
a VM can use its preferred process manager and reverse proxy. Those integrations
are choices of the operator, not dependencies of the Python package.

## Verification

Check HTTPS /livez, rejection of an unauthenticated /mcp request, then complete an
authenticated tool call through an MCP client. The repository tests application and
container behavior, including PORT binding; it does not claim a live deployment
test in every cloud or platform.

## Platform reference

[Cloud Run container configuration](https://docs.cloud.google.com/run/docs/configuring/services/containers)
