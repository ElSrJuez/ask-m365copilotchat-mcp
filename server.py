import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from listener_config import HOST, MCP_PATH, MCP_URL, OPENAI_PATH, OPENAI_URL, PORT, WS_PATH, WS_URL
from mcp_server import mcp


class BridgeRequestError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class BridgeRequestSession:
    def __init__(self, prompt: str):
        self.prompt = prompt
        self.ws = None
        self.lock_acquired = False

    async def open(self):
        global browser_ws

        self.ws = browser_ws
        if not self.ws:
            raise BridgeRequestError(503, "M365 Copilot Chat browser tab is not connected.")

        if request_lock.locked():
            raise BridgeRequestError(429, "Another request is already in progress. Please wait.")

        await request_lock.acquire()
        self.lock_acquired = True

        while not msg_queue.empty():
            try:
                msg_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        try:
            await self.ws.send_json({"type": "SEND_PROMPT", "text": self.prompt})
        except Exception as exc:
            raise BridgeRequestError(503, "M365 Copilot Chat browser tab is not connected.") from exc

    async def close(self):
        if self.lock_acquired:
            request_lock.release()
            self.lock_acquired = False

    async def iter_chunks(self):
        try:
            while True:
                msg = await msg_queue.get()
                msg_type = msg.get("type")

                if msg_type == "CHUNK":
                    yield msg.get("text", "")
                elif msg_type == "DONE":
                    print("Completed response streaming successfully.")
                    break
                elif msg_type == "DISCONNECTED":
                    print("Browser disconnected during streaming.")
                    break
        except Exception as exc:
            print(f"Error during streaming loop: {str(exc)}")


def create_bridge_session(prompt: str) -> BridgeRequestSession:
    return BridgeRequestSession(prompt)


def bridge_error_response(exc: BridgeRequestError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status_code)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
app.mount(MCP_PATH, mcp.streamable_http_app())
browser_ws = None  # Holds our active browser tab connection
msg_queue = asyncio.Queue()  # Single queue fed by the one reader coroutine
request_lock = asyncio.Lock()  # Serialize requests through the single browser WS

@app.websocket(WS_PATH)
async def websocket_endpoint(websocket: WebSocket):
    global browser_ws
    await websocket.accept()
    browser_ws = websocket
    print("\nBrowser tab successfully connected to local proxy!")
    try:
        while True:
            # Single reader: all incoming WS messages go into the queue
            raw = await websocket.receive_text()
            try:
                parsed = json.loads(raw)
                await msg_queue.put(parsed)
            except json.JSONDecodeError:
                pass  # Ignore non-JSON keepalive frames
    except Exception:
        browser_ws = None
        # Signal any in-flight stream that the connection is gone
        await msg_queue.put({"type": "DISCONNECTED"})
        print("\nBrowser tab disconnected.")

@app.post(OPENAI_PATH)
async def chat_completions(request: Request):
    body = await request.json()
    prompt = body["messages"][-1]["content"] if "messages" in body else ""
    print(f"\nReceived incoming API prompt: {prompt[:50]}...")

    try:
        session = create_bridge_session(prompt)
        await session.open()
    except BridgeRequestError as exc:
        return bridge_error_response(exc)

    async def event_stream():
        try:
            async for chunk in session.iter_chunks():
                chunk_payload = {
                    "choices": [{
                        "delta": {
                            "content": chunk
                        }
                    }]
                }
                yield f"data: {json.dumps(chunk_payload)}\n\n"
        finally:
            await session.close()

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    print("M365 Copilot Chat Bridge starting up...")
    print(f"OpenAI Endpoint: {OPENAI_URL}")
    print(f"Browser WebSocket: {WS_URL}")
    print(f"MCP HTTP Endpoint: {MCP_URL}")
    uvicorn.run(app, host=HOST, port=PORT)
