# AID2E Code-Assist: User Setup Guide

This guide sets up the AID2E 100B code-assist model in VS Code and, if
needed, the AID2E MCP tools. Each person uses an individual LiteLLM API key,
so usage is attributed to that user and a key can be revoked independently.

## Before you begin

You need:

- VS Code with the current **GitHub Copilot Chat** extension.
- An account that can SSH to SciClone, if you will use the SSH-tunnel route.
- Python 3 and Git.
- A personal LiteLLM API key beginning with `sk-`.

Request a key by emailing [jgiroux@wm.edu](mailto:jgiroux@wm.edu). Include
your W&M username, preferred email address, and a note that you need access
to the AID2E Code-Assist model. Do not share your key with anyone.

The model name used by every client is:

```text
code-assist-100b
```

## 1. Clone and install AID2E

Clone the AID2E repository provided by the project team, then install its MCP
extra in an isolated Python environment. Replace `<AID2E-REPOSITORY-URL>` with
the repository URL you were given.

```bash
git clone <AID2E-REPOSITORY-URL>
cd AID2E-framework

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[mcp]"
```

You can use Conda instead of `venv` if preferred. The important installation
command, run from the repository root, is:

```bash
python -m pip install -e ".[mcp]"
```

## 2. Connect to the LiteLLM gateway

LiteLLM is the gateway in front of the model. It authenticates your personal
key, routes the request to the 100B model, and records usage. You never need
the vLLM pod address or a Kubernetes command to use the service.

### Option A: direct shared endpoint

If the service administrator provides a reachable shared endpoint, use it as
your base URL:

```text
http://<LITELLM-HOST>:4000/v1
```

Use the full chat endpoint below when configuring VS Code:

```text
http://<LITELLM-HOST>:4000/v1/chat/completions
```

### Option B: SSH tunnel through SciClone

If you are given the tunnel-based route, run this command from the same
environment in which the VS Code Copilot extension runs. For example, if you
use VS Code in WSL, run it in your WSL terminal—not in a separate Windows
terminal.

```bash
ssh -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 4001:127.0.0.1:4000 \
  <your-wm-username>@cm.geo.sciclone.wm.edu
```

Keep this terminal open while using AID2E. With this tunnel, your local API
base URL is:

```text
http://127.0.0.1:4001/v1
```

If SciClone access requires the W&M VPN, connect to the VPN first. If the SSH
command is refused, contact the service administrator rather than attempting
to expose a Kubernetes service yourself.

## 3. Verify your key and connection

Set the endpoint that applies to your connection. For the SSH-tunnel example:

```bash
export AID2E_LLM_URL="http://127.0.0.1:4001/v1"
read -rsp "Paste your AID2E API key: " AID2E_LLM_API_KEY; echo
```

Check that the gateway recognizes the model:

```bash
curl -sS "$AID2E_LLM_URL/models" \
  -H "Authorization: Bearer $AID2E_LLM_API_KEY"
```

The response should list `code-assist-100b`. Then make a small test request:

```bash
curl -sS "$AID2E_LLM_URL/chat/completions" \
  -H "Authorization: Bearer $AID2E_LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "code-assist-100b",
    "messages": [{"role": "user", "content": "Reply with pong."}],
    "max_tokens": 16
  }'

unset AID2E_LLM_API_KEY
```

If this fails, send the error message to the administrator, but never send
your API key.

## 4. Configure VS Code Chat

1. In VS Code, open the Command Palette with `Ctrl+Shift+P`.
2. Run **Chat: Manage Language Models**.
3. Choose **Add Models** → **Custom Endpoint**.
4. Enter a group name such as `AID2E`.
5. Enter your personal API key when prompted and select **Chat
   Completions**.
6. Open `chatLanguageModels.json` from the Language Models editor.

Use the following configuration. Replace the two key placeholders with your
own key, and use the endpoint that applies to you. This tunnel example uses
port `4001`.

```json
[
  {
    "name": "AID2E",
    "vendor": "customendpoint",
    "apiKey": "sk-PASTE-YOUR-PERSONAL-KEY-HERE",
    "apiType": "chat-completions",
    "models": [
      {
        "id": "code-assist-100b",
        "name": "AID2E Code Assist 100B",
        "url": "http://127.0.0.1:4001/v1/chat/completions",
        "toolCalling": true,
        "vision": false,
        "maxInputTokens": 61440,
        "maxOutputTokens": 4096,
        "modelOptions": {
          "parallel_tool_calls": false
        },
        "requestHeaders": {
          "Authorization": "Bearer sk-PASTE-YOUR-PERSONAL-KEY-HERE"
        }
      }
    ]
  }
]
```

Important:

- Use the exact same personal key in both locations.
- Do not include `Bearer ` in the `apiKey` value.
- The `Authorization` header must include `Bearer ` followed by the key.
- Keep this configuration private. Do not commit it to a repository or share
  screenshots containing the key.
- Run **Developer: Reload Window** after saving if the model does not appear.

At the bottom of the Chat panel, open the model picker and select **AID2E Code Assist 100B**. Your current model selection likely says **Auto**. The service is a chat/agent model; do not configure a separate
inline-completion or Continue endpoint.

## 5. Enable AID2E MCP tools

The model can use AID2E MCP tools after the package is installed. In VS Code,
run **MCP: Open User Configuration** and add a server entry. Replace the path
with the absolute path to your clone:

```json
{
  "servers": {
    "aid2e": {
      "command": "/absolute/path/to/AID2E-framework/.venv/bin/aid2e",
      "args": ["mcp"]
    }
  }
}
```

Start the MCP server from the VS Code MCP view, then enable the desired tools
from the Chat interface. If you use Conda rather than `.venv`, point
`command` at that environment's `aid2e` executable, or use a shell wrapper
that activates the environment before running `aid2e mcp`.

Enable the AID2E tools shown below from the Chat interface.

![AID2E MCP tool selection](assets/tool_list.png)

The tool menu is two parallel lines next to the model selection.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `connect ECONNREFUSED` | The SSH tunnel is not running in the same environment as VS Code. Restart the tunnel and keep it open. |
| `Malformed API Key` | Ensure the header is `Authorization: Bearer sk-...`; do not use an `api-key` header with `Bearer`. |
| `model ... is not available for this API key` | Your key or its owner lacks access to `code-assist-100b`. Email [jgiroux@wm.edu](mailto:jgiroux@wm.edu). |
| Model does not appear in VS Code | Save the configuration and run **Developer: Reload Window**. Ensure GitHub Copilot Chat is current. |
| Old Continue/inline-completion error | That is not part of AID2E Code-Assist. Remove or disable the old completion endpoint configuration. |

## Security and support

Your LiteLLM key identifies your requests and is tracked for usage reporting.
Do not share it, commit it, or put it in a public issue. If you suspect that
your key was exposed, email [jgiroux@wm.edu](mailto:jgiroux@wm.edu) to have it
revoked and reissued.
