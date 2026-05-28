(function() {
    // Only activate on Copilot chat pages
    if (!window.location.href.includes("chat")) return;

    const WS_URL = "ws://127.0.0.1:8000/ws";
    let ws = null;
    let reconnectTimer = null;

    function connect() {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log("%cM365 Copilot Chat Bridge: Connected to local proxy server.", "color: #00ff00; font-weight: bold; font-size: 12px;");
            if (reconnectTimer) {
                clearInterval(reconnectTimer);
                reconnectTimer = null;
            }
        };

        ws.onclose = () => {
            console.log("%cM365 Copilot Chat Bridge: Disconnected. Will retry every 5s.", "color: #ff0000; font-weight: bold; font-size: 12px;");
            if (!reconnectTimer) {
                reconnectTimer = setInterval(() => {
                    if (!ws || ws.readyState === WebSocket.CLOSED) {
                        connect();
                    }
                }, 5000);
            }
        };

        ws.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "SEND_PROMPT") {
                    console.log("User Code snip pasted...");
                    await pasteAndSubmit(data.text);
                }
            } catch (err) {
                console.error("Error handling incoming ws message:", err);
            }
        };
    }

    async function pasteAndSubmit(promptText) {
        const inputEl = document.querySelector('#m365-chat-editor-target-element, span[contenteditable="true"][data-lexical-editor="true"]');
        if (!inputEl) {
            console.error("Could not find the prompt input text element.");
            return;
        }

        inputEl.focus();

        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, promptText);

        inputEl.dispatchEvent(new Event('input', { bubbles: true }));

        // Submit by pressing Enter — the send button only appears after React state
        // catches up, so dispatching a keypress is more reliable
        setTimeout(() => {
            inputEl.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                bubbles: true, cancelable: true
            }));
            console.log("Prompt submitted via Enter key. Starting response capture...");
            startResponseCapture();
        }, 300);
    }

    function startResponseCapture() {
        let lastLength = 0;
        let hasReceivedContent = false;
        let doneDebounceTimer = null;
        const OBSERVER_TIMEOUT_MS = 90000;

        const observer = new MutationObserver(() => {
            const assistantBubbles = document.querySelectorAll('[data-testid="markdown-reply"][data-message-type="Chat"]');
            if (assistantBubbles.length === 0) return;

            const targetBubble = assistantBubbles[assistantBubbles.length - 1];
            const currentFullText = targetBubble.innerText;

            if (currentFullText.length > lastLength) {
                const delta = currentFullText.substring(lastLength);
                lastLength = currentFullText.length;
                hasReceivedContent = true;

                ws.send(JSON.stringify({ type: "CHUNK", text: delta }));
            }

            if (!hasReceivedContent) return;

            const stopBtn = document.querySelector('button[aria-label="Stop generating"]');
            if (!stopBtn) {
                if (!doneDebounceTimer) {
                    doneDebounceTimer = setTimeout(() => {
                        cleanup("Stream complete. Detached listener.");
                    }, 500);
                }
            } else {
                if (doneDebounceTimer) {
                    clearTimeout(doneDebounceTimer);
                    doneDebounceTimer = null;
                }
            }
        });

        function cleanup(reason) {
            clearTimeout(doneDebounceTimer);
            clearTimeout(timeoutHandle);
            observer.disconnect();
            console.log(reason);
            ws.send(JSON.stringify({ type: "DONE" }));
        }

        const timeoutHandle = setTimeout(() => {
            cleanup("Observer timed out after " + (OBSERVER_TIMEOUT_MS / 1000) + "s. Detaching.");
        }, OBSERVER_TIMEOUT_MS);

        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }

    connect();
})();
