# Quick Start Guide

Get up and running in under 5 minutes. This covers the happy path and the common mistakes that trip people up.

## Step 1: Python environment

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

**Common mistake:** Running `pip install` outside the virtual environment. If you see `ModuleNotFoundError: No module named 'fastapi'` later, you installed into the wrong Python. Activate the venv first.

**Common mistake:** Missing `websockets`. Uvicorn needs it for WebSocket support. If you see `No supported WebSocket library detected`, run `pip install -r requirements.txt` again — it's in there.

## Step 2: Load the browser extension

1. Open `edge://extensions` or `chrome://extensions`
2. Enable **Developer mode** (toggle in the top corner)
3. Click **Load unpacked** and select the `extension/` folder
4. Navigate to M365 Copilot Chat in the same browser

**Common mistake:** Loading the extension but not navigating to a Copilot Chat page. The content script only activates on pages with "chat" in the URL.

**Common mistake:** The extension loads but the console shows repeated `WebSocket connection failed` errors. This means the bridge server is not running yet — that's Step 3. The extension will auto-reconnect once the server starts.

## Step 3: Start the bridge server

```bash
python -m server
```

You should see:

```
M365 Copilot Chat Bridge starting up...
Endpoint URL: http://127.0.0.1:8000/v1/chat/completions
WebSocket Listener: ws://127.0.0.1:8000/ws
```

Then within a few seconds, the browser console should show the green message: **"M365 Copilot Chat Bridge: Connected to local proxy server."**

**Common mistake:** Running `python server.py` instead of `python -m server`. Both work, but using `-m` ensures the correct module resolution.

**Common mistake:** Port 8000 is already in use by another service. Check with `netstat -ano | findstr :8000` (Windows) or `lsof -i :8000` (macOS/Linux) and stop the conflicting process.

## Step 4: Test it

Send a test prompt. From PowerShell:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/chat/completions" -Method Post -ContentType "application/json" -Body '{"messages":[{"role":"user","content":"Hello"}],"stream":true}'
```

Or from bash:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"stream":true}'
```

You should see SSE chunks streaming back with the Copilot Chat response.

**Common mistake:** The first response after loading a page with an existing conversation may echo the previous answer. This is a known issue — the second request onwards works correctly.

## Step 5: Register the MCP tool (optional)

If you're using Claude Code:

```bash
claude mcp add m365copilot -- python mcp_server.py
```

Then restart your Claude Code session. The `AskM365Copilot` tool becomes available.

**Common mistake:** Forgetting to restart Claude Code after registering. MCP servers only load at session startup.

**Common mistake:** The MCP server can't reach the bridge. Make sure `server.py` is running before using the MCP tool.

## Order matters

The startup sequence matters:

1. **Server first** — `python -m server`
2. **Browser second** — Navigate to M365 Copilot Chat (extension auto-connects)
3. **Client last** — Send requests via API or MCP tool

If the extension connects before the server is ready, it retries every 5 seconds automatically. But the server must be running before any API or MCP requests will work.

## Something not working?

See the [Troubleshooting](README.md#troubleshooting) section in the README.
