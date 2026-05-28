import asyncio
import json
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
browser_ws = None  # Holds our active browser tab connection
msg_queue = asyncio.Queue()  # Single queue fed by the one reader coroutine
request_lock = asyncio.Lock()  # Serialize requests through the single browser WS

@app.websocket("/ws")
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

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    global browser_ws

    ws = browser_ws
    if not ws:
        return JSONResponse(
            {"error": "M365 Copilot Chat browser tab is not connected."},
            status_code=503
        )

    if request_lock.locked():
        return JSONResponse(
            {"error": "Another request is already in progress. Please wait."},
            status_code=429
        )

    async with request_lock:
        body = await request.json()
        prompt = body["messages"][-1]["content"] if "messages" in body else ""
        print(f"\nReceived incoming API prompt: {prompt[:50]}...")

        # Drain any stale messages left in the queue from a previous request
        while not msg_queue.empty():
            try:
                msg_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        async def event_stream():
            try:
                await ws.send_json({"type": "SEND_PROMPT", "text": prompt})
            except Exception as e:
                print(f"Error sending prompt to browser: {str(e)}")
                yield "data: [DONE]\n\n"
                return

            # Consume messages from the queue (fed by the single WS reader)
            while True:
                try:
                    msg = await msg_queue.get()
                    if msg["type"] == "CHUNK":
                        chunk_payload = {
                            "choices": [{
                                "delta": {
                                    "content": msg["text"]
                                }
                            }]
                        }
                        yield f"data: {json.dumps(chunk_payload)}\n\n"
                    elif msg["type"] == "DONE":
                        yield "data: [DONE]\n\n"
                        print("Completed response streaming successfully.")
                        break
                    elif msg["type"] == "DISCONNECTED":
                        print("Browser disconnected during streaming.")
                        yield "data: [DONE]\n\n"
                        break
                except Exception as e:
                    print(f"Error during streaming loop: {str(e)}")
                    yield "data: [DONE]\n\n"
                    break

        return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    print("M365 Copilot Chat Bridge starting up...")
    print("Endpoint URL: http://127.0.0.1:8000/v1/chat/completions")
    print("WebSocket Listener: ws://127.0.0.1:8000/ws")
    uvicorn.run(app, host="127.0.0.1", port=8000)
