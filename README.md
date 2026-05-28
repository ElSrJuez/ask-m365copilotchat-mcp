# Ask M365 Copilot Chat MCP

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-yellow.svg)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)

A local bridge that exposes Microsoft 365 Copilot Chat as an OpenAI-compatible API endpoint and MCP tool. Useful for piping prompts (e.g. code snippets for review) into M365 Copilot Chat programmatically, avoiding manual copy-paste between apps.

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

1. **`server.py`** -- A FastAPI backend that accepts OpenAI-format chat completion requests and streams responses back as Server-Sent Events (SSE). Communicates with the browser via a persistent WebSocket using a single-reader/queue pattern to avoid contention.

2. **`extension/`** -- A Manifest V3 browser extension that connects the Copilot Chat page to the local bridge. The content script receives prompts over the WebSocket, pastes them into the Copilot Lexical editor, submits via Enter key, and captures the streamed response using a MutationObserver. The extension is vanilla JavaScript with no build step.

3. **`mcp_server.py`** -- An MCP (Model Context Protocol) server exposing a single `AskM365Copilot` tool. Runs over stdio and acts as a thin HTTP client to the local bridge. Designed for use with Claude Code or any MCP-compatible client.

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

## Usage

**Direct API call** -- Send a POST request to the `/v1/chat/completions` endpoint in OpenAI chat completion format with `stream: true`. Any tool or library that supports a custom OpenAI base URL can point at the local server.

**MCP tool** -- Register the MCP server in your client (e.g. Claude Code):

```bash
claude mcp add m365copilot -- python mcp_server.py
```

The `AskM365Copilot` tool then becomes available in your session.

## Architecture Notes

- **Single WebSocket reader** -- One coroutine reads all incoming browser messages into an `asyncio.Queue`, eliminating competing-reader race conditions.
- **Request serialization** -- An `asyncio.Lock` ensures only one prompt flows through the bridge at a time (returns HTTP 429 if busy).
- **Observer lifecycle** -- The MutationObserver includes a content-received guard (prevents premature completion), a 500ms debounce, and a 90-second safety timeout.
- **Decoupled MCP layer** -- The MCP server communicates with the bridge exclusively over HTTP, keeping it independent of WebSocket internals.

## Project Structure

```
server.py              FastAPI bridge server (WebSocket + HTTP)
mcp_server.py          MCP stdio server (AskM365Copilot tool)
requirements.txt       Python dependencies
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

**MCP tool returns "Cannot connect to bridge server"** -- The bridge server must be running before the MCP tool can be used. Start `server.py` first.

## Limitations

- One request at a time (serial, not parallel)
- DOM selectors may break if Microsoft changes the Copilot Chat UI
- Response text fidelity depends on MutationObserver timing -- occasional character drops on fast streams
- The bridge server and browser must be on the same machine

## Disclaimer

This tool automates your own authenticated M365 Copilot session locally. It does not access any Microsoft APIs or services beyond what your browser session already has access to. Use it in compliance with your organization's policies and Microsoft's Terms of Service. This project is not affiliated with or endorsed by Microsoft.

## License

Apache 2.0 -- see [LICENSE](LICENSE).
