# Local installation

Python 3.13+ works on Windows, macOS and Linux. A local MCP client launches the
server as a subprocess, so stdio needs no domain, HTTP listener, login or cloud account.

## Install in an isolated environment

From a downloaded/cloned source directory:

Windows PowerShell:

```powershell
.\setup\install.ps1
# Or choose a Python executable:
.\setup\install.ps1 -PythonPath "C:\Python313\python.exe"
```

macOS / Linux:

```sh
sh setup/install.sh
# Or select another interpreter:
PYTHON=python3.13 sh setup/install.sh
```

The scripts only create .venv, install pinned dependencies and the local package.
They do not require administrator/root access or change system services.

Manual Windows alternative:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps .
.\.venv\Scripts\python.exe -m market_fiyati_mcp --client-config
```

Manual macOS / Linux alternative:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m market_fiyati_mcp --client-config
```

If using a system/user installation instead of a virtual environment, python -m pip
install . is supported. No package publication on a public package index is required.

## Connect an MCP client

Copy the generated configuration into the client's MCP server settings. Clients
with a graphical setup form need the same command and arguments:

```json
{
  "mcpServers": {
    "market-fiyati": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "market_fiyati_mcp"]
    }
  }
}
```

The --client-config command fills in your actual interpreter path. JSON container
keys vary between clients; the executable and arguments stay the same.
On Windows, generated JSON escapes backslashes correctly.

Avoid shell activation commands inside an MCP client's command field.
Use the virtual environment's interpreter directly. Do not allocate a terminal
for stdio; stdout contains only MCP messages.

## SSH without a domain

Install the package on another computer, then configure the client to launch:

```text
command: ssh
args: ["-T", "user@192.0.2.10", "/path/to/environment/bin/python", "-m", "market_fiyati_mcp"]
```

192.0.2.10 is a documentation address; replace it with the other machine's IP.
Authenticate SSH independently and verify its host key. This needs no public MCP
port or TLS certificate, and is suitable for clients that can launch local commands.

## Test

Ask the agent to search for a common product, then inspect quantity/unit, source and
freshness. A running subprocess alone does not prove the client's full integration.
