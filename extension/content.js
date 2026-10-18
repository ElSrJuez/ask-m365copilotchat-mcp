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

        ws.onerror = (event) => {
            console.error("M365 Copilot Chat Bridge websocket error:", event);
        };

        ws.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "SEND_PROMPT") {
                    console.log("User Code snip pasted...");
                    if (data.diagnostics === true) {
                        sendObservation({ phase: "prompt_received", diagnosticsEnabled: true });
                    }
                    await pasteAndSubmit(data.text, data.diagnostics === true);
                }
            } catch (err) {
                console.error("Error handling incoming ws message:", err);
            }
        };
    }

    function sendMessage(message) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(message));
        }
    }

    function sendObservation(observation) {
        sendMessage({ type: "DIAG", observation: observation });
    }

    async function pasteAndSubmit(promptText, diagnosticsEnabled) {
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

        const assistantBubbleSelector = '[data-testid="markdown-reply"][data-message-type="Chat"]';
        const baselineBubbleTexts = new Map(
            Array.from(document.querySelectorAll(assistantBubbleSelector), (bubble) => [bubble, bubble.innerText])
        );

        // Submit by pressing Enter — the send button only appears after React state
        // catches up, so dispatching a keypress is more reliable
        setTimeout(() => {
            inputEl.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                bubbles: true, cancelable: true
            }));
            console.log("Prompt submitted via Enter key. Starting response capture...");
            startResponseCapture(baselineBubbleTexts, diagnosticsEnabled);
        }, 300);
    }

    function startResponseCapture(baselineBubbleTexts, diagnosticsEnabled) {
        const assistantBubbleSelector = '[data-testid="markdown-reply"][data-message-type="Chat"]';
        const captureStartedAt = Date.now();
        const snapshotSamples = [];

        let targetBubble = null;
        let targetBaselineText = "";
        let lastLength = 0;
        let firstTextSnapshot = null;
        let snapshotCount = 0;
        let emittedChunkCount = 0;
        let emittedTextLength = 0;
        let hasReceivedContent = false;
        let doneDebounceTimer = null;
        const OBSERVER_TIMEOUT_MS = 90000;
        const MAX_SNAPSHOT_SAMPLES = 8;

        function resolveTargetBubble(assistantBubbles) {
            if (targetBubble && document.contains(targetBubble)) {
                return targetBubble;
            }

            let nextBubble = null;
            for (let index = assistantBubbles.length - 1; index >= 0; index -= 1) {
                const bubble = assistantBubbles[index];
                const baselineText = baselineBubbleTexts.get(bubble);
                if (baselineText === undefined || (bubble.innerText.length > baselineText.length && bubble.innerText.startsWith(baselineText))) {
                    nextBubble = bubble;
                    targetBaselineText = baselineText || "";
                    break;
                }
            }

            if (!nextBubble) {
                return null;
            }

            targetBubble = nextBubble;
            lastLength = targetBaselineText.length;
            return targetBubble;
        }

        const observer = new MutationObserver(() => {
            const assistantBubbles = Array.from(document.querySelectorAll(assistantBubbleSelector));
            if (assistantBubbles.length === 0) return;

            const activeBubble = resolveTargetBubble(assistantBubbles);
            if (!activeBubble) return;

            const currentFullText = activeBubble.innerText;

            if (diagnosticsEnabled) {
                snapshotCount += 1;
                if (firstTextSnapshot === null) {
                    firstTextSnapshot = currentFullText;
                }
                snapshotSamples.push({
                    elapsedMs: Date.now() - captureStartedAt,
                    textLength: currentFullText.length,
                    prefix: currentFullText.slice(0, 100),
                    suffix: currentFullText.slice(-100)
                });
                if (snapshotSamples.length > MAX_SNAPSHOT_SAMPLES) {
                    snapshotSamples.shift();
                }
            }

            if (currentFullText.startsWith(targetBaselineText) && currentFullText.length > lastLength) {
                const delta = currentFullText.substring(lastLength);
                lastLength = currentFullText.length;
                hasReceivedContent = true;
                emittedChunkCount += 1;
                emittedTextLength += delta.length;

                sendMessage({ type: "CHUNK", text: delta });
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
            if (diagnosticsEnabled) {
                const assistantBubbles = Array.from(document.querySelectorAll(assistantBubbleSelector));
                const finalText = targetBubble && document.contains(targetBubble) ? targetBubble.innerText : null;
                const attributes = targetBubble
                    ? Array.from(targetBubble.attributes, (attribute) => [attribute.name, attribute.value])
                    : [];
                sendObservation({
                    phase: "capture_summary",
                    reason: reason.indexOf("timed out") >= 0 ? "timeout" : "complete",
                    bubbleCount: assistantBubbles.length,
                    targetBubbleIndex: targetBubble ? assistantBubbles.indexOf(targetBubble) : -1,
                    targetAttributes: attributes,
                    baselineTextLength: targetBaselineText.length,
                    firstTextSnapshot: firstTextSnapshot,
                    finalText: finalText,
                    snapshotCount: snapshotCount,
                    snapshotSamples: snapshotSamples,
                    emittedChunkCount: emittedChunkCount,
                    emittedTextLength: emittedTextLength
                });
            }
            sendMessage({ type: "DONE" });
        }

        const timeoutHandle = setTimeout(() => {
            cleanup("Observer timed out after " + (OBSERVER_TIMEOUT_MS / 1000) + "s. Detaching.");
        }, OBSERVER_TIMEOUT_MS);

        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    }

    connect();
})();
