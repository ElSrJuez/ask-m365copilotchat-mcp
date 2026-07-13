# Ask M365 Copilot Chat MCP

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

A local bridge that lets you use Microsoft 365 Copilot Chat programmatically instead of manually copy-pasting between apps. It runs a single local HTTP listener that exposes an OpenAI-compatible endpoint, an MCP endpoint, and the browser bridge needed to drive the authenticated chat session.

## How It Works

The project has three components that form a pipeline:

```
API Client / MCP Tool
        |
        v
  Local FastAPI Server (localhost:8000)
        |  WebSocket
        v
  Browser Extension (Edge/Chrome)
        |  DOM automation + MutationObserver
        v
  M365 Copilot Chat UI
```

1. **`server.py`** -- The main runtime. Starts one FastAPI listener on `127.0.0.1:8000`, serves the OpenAI-compatible endpoint at `/v1/chat/completions`, mounts the MCP HTTP endpoint at `/mcp`, and accepts the browser bridge connection at `/ws`.

2. **`extension/`** -- A Manifest V3 browser extension that connects the Copilot Chat page to the local bridge. The content script receives prompts over the WebSocket, pastes them into the page editor, submits via Enter key, and captures the streamed response using a MutationObserver. The extension is vanilla JavaScript with no build step.

3. **`mcp_server.py`** -- Defines the MCP server and the `AskM365Copilot` tool that `server.py` mounts for HTTP use at `/mcp`.

**New here?** See the [Quick Start Guide](QUICKSTART.md) for step-by-step setup with common pitfalls.

## Prerequisites

- Python 3.10+
- Microsoft Edge or Google Chrome
- An M365 account with Copilot Chat access

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. Load the browser extension

1. Open `edge://extensions` or `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** and select the `extension/` folder
4. Navigate to M365 Copilot Chat -- the console should confirm the WebSocket connection

### 3. Start the bridge server

```bash
python -m server
```

The server listens on localhost port 8000.

Current surfaces:

- OpenAI-compatible HTTP: `/v1/chat/completions`
- MCP over HTTP: `/mcp`
- Browser WebSocket: `/ws`

## Usage

**Direct API call** -- Send a `POST` request to `/v1/chat/completions` in OpenAI chat completion format with `stream: true`. Any tool or library that supports a custom OpenAI base URL can point at the local server.

**MCP over HTTP** -- Point your MCP client at:

```text
http://127.0.0.1:8000/mcp
```

The server exposes one tool, `AskM365Copilot`.

## Architecture Notes

- **Single WebSocket reader** -- One coroutine reads all incoming browser messages into an `asyncio.Queue`, eliminating competing-reader race conditions.
- **Request serialization** -- An `asyncio.Lock` ensures only one prompt flows through the bridge at a time (returns HTTP 429 if busy).
- **Observer lifecycle** -- The MutationObserver includes a content-received guard (prevents premature completion), a 500ms debounce, and a 90-second safety timeout.
- **Single local listener** -- The OpenAI-compatible API, MCP HTTP endpoint, and browser WebSocket all share one local server.
- **Shared MCP definition** -- `mcp_server.py` defines the MCP server once, and `server.py` exposes that server over HTTP.

## Project Structure

```
server.py              Main FastAPI runtime (OpenAI HTTP + MCP HTTP + WebSocket)
mcp_server.py          MCP server definition (mounted by server.py)
listener_config.py     Shared local listener host/port/path constants
requirements.txt       Python dependencies
QUICKSTART.md          Step-by-step setup guide with common pitfalls
CONTRIBUTING.md        Contribution guidelines
CODE_OF_CONDUCT.md     Community standards
extension/
  manifest.json        Manifest V3 extension config
  rules.json           declarativeNetRequest header rules
  content.js           Content script (prompt automation + response capture)
.github/
  pull_request_template.md
```

## Troubleshooting

**Extension says "Disconnected. Will retry every 5s."** -- The bridge server is not running. Start it with `python -m server` and the extension will reconnect automatically.

**Server starts but browser never connects** -- Make sure the extension is loaded and you are on an M365 Copilot Chat page. Check the browser console for connection errors.

**Prompt is sent but response is empty** -- The DOM selectors may have changed if Microsoft updated the Copilot Chat UI. Open the browser console and check for errors from `content.js`.

**MCP tool returns "Cannot connect to bridge server"** -- The bridge server must be running before the tool can reach the browser session. Start `python -m server` first.

## Limitations

- One request at a time (serial, not parallel)
- DOM selectors may break if Microsoft changes the Copilot Chat UI
- Response text fidelity depends on MutationObserver timing -- occasional character drops on fast streams
- The bridge server and browser must be on the same machine

## Disclaimer

This tool automates your own authenticated M365 Copilot session locally. It does not access any Microsoft APIs or services beyond what your browser session already has access to. Use it in compliance with your organization's policies and Microsoft's Terms of Service. This project is not affiliated with or endorsed by Microsoft.

## License

Apache 2.0 -- see [LICENSE](LICENSE).
