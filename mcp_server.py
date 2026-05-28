import json
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("AskM365Copilot")

BRIDGE_URL = "http://127.0.0.1:8000/v1/chat/completions"
REQUEST_TIMEOUT = 120.0


@mcp.tool()
async def AskM365Copilot(question: str) -> str:
    """Ask a question to Microsoft 365 Copilot Chat via the browser bridge.

    The question is sent to M365 Copilot Chat within your authenticated session through
    a browser extension that pastes prompts and sends back the responses. Requires
    server.py to be running and the browser extension to be connected.

    Args:
        question: The question or prompt to send to M365 Copilot Chat.

    Returns:
        The complete text response from M365 Copilot Chat.
    """
    payload = {
        "messages": [{"role": "user", "content": question}],
        "stream": True
    }

    collected_text = []

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST", BRIDGE_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT
            ) as response:
                if response.status_code == 503:
                    return "Error: M365 Copilot Chat browser tab is not connected. Please ensure the browser extension is active and connected."
                if response.status_code == 429:
                    return "Error: Another request is already in progress. Please wait and try again."
                if response.status_code != 200:
                    body = await response.aread()
                    return f"Error: Bridge returned HTTP {response.status_code}: {body.decode()}"

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta_content = chunk["choices"][0]["delta"].get("content", "")
                        if delta_content:
                            collected_text.append(delta_content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except httpx.ConnectError:
            return "Error: Cannot connect to the bridge server at localhost:8000. Please ensure server.py is running."
        except httpx.ReadTimeout:
            return "Error: Request timed out waiting for M365 Copilot Chat response."

    if not collected_text:
        return "Error: Received empty response from M365 Copilot Chat."

    return "".join(collected_text)


if __name__ == "__main__":
    mcp.run()
