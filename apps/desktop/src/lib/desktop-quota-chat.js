import { chatMessageText } from '@/lib/chat-messages';
/** Active AbortControllers keyed by runtime session id. */
const activeStreams = new Map();
/** Register an in-flight stream so cancelRun can abort it. */
export function setDesktopQuotaAbort(sessionId, controller) {
    const prev = activeStreams.get(sessionId);
    // Best-effort abort a stray controller (e.g. a re-entrant send) without
    // throwing — it may already be settled.
    prev?.abort();
    activeStreams.set(sessionId, controller);
}
/** Abort + clear the in-flight desktop-quota stream for a session (if any). */
export function abortDesktopQuota(sessionId) {
    const controller = activeStreams.get(sessionId);
    if (controller) {
        controller.abort();
        activeStreams.delete(sessionId);
    }
}
/**
 * Build the OpenAI messages array for aigw from the live transcript + the new
 * user text. Visible user/assistant messages are mapped to their text content;
 * hidden, errored, pending, and tool-only messages are skipped. The latest
 * user message (already seeded optimistically by the submit pipeline) carries
 * the new prompt text, so it is included as-is.
 */
export function buildDesktopQuotaMessages(transcript, newUserText) {
    const out = [];
    for (const message of transcript) {
        if (message.hidden || message.error) {
            continue;
        }
        if (message.role !== 'user' && message.role !== 'assistant') {
            continue;
        }
        // Skip a pending assistant placeholder (no content yet).
        if (message.role === 'assistant' && message.pending && !chatMessageText(message).trim()) {
            continue;
        }
        const text = chatMessageText(message).trim();
        if (!text) {
            continue;
        }
        out.push({ content: text, role: message.role });
    }
    // If the optimistic user message didn't make it into the transcript snapshot
    // (e.g. a brand-new session whose state hasn't flushed to $messages yet),
    // append the new text as the final user turn so aigw always sees the prompt.
    const last = out.at(-1);
    if (!last || last.role !== 'user' || last.content !== newUserText.trim()) {
        out.push({ content: newUserText.trim(), role: 'user' });
    }
    return out;
}
/**
 * Stream a desktop-quota chat completion from the aigw hub. Resolves once the
 * stream finishes (the assistant message has been finalized via the handlers).
 * Rejects only on a non-abort network/parse failure (the handlers' fail path
 * already runs, so the caller's catch is for bookkeeping like releasing the
 * busy lock).
 */
export async function streamDesktopQuotaChat(req) {
    const { baseUrl, apiKey, model, messages, sessionId, signal, handlers } = req;
    const url = `${baseUrl.replace(/\/+$/, '')}/chat/completions`;
    let response;
    try {
        response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${apiKey}`
            },
            body: JSON.stringify({ model, messages, stream: true }),
            signal
        });
    }
    catch (err) {
        if (signal.aborted) {
            return;
        }
        handlers.failAssistantMessage(sessionId, friendlyAigwError(err, 'Could not reach the local quota hub.'));
        return;
    }
    if (!response.ok) {
        const body = await response.text().catch(() => '');
        handlers.failAssistantMessage(sessionId, `Quota hub returned ${response.status} ${response.statusText}${body ? `: ${body.slice(0, 300)}` : ''}`);
        return;
    }
    if (!response.body) {
        handlers.failAssistantMessage(sessionId, 'Quota hub returned an empty stream.');
        return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let assistantText = '';
    let reasoningText = '';
    let sawAnyChunk = false;
    try {
        // eslint-disable-next-line no-constant-condition
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            // SSE frames are separated by a blank line. Process complete frames only
            // so a delta split across chunks isn't parsed prematurely.
            const frames = buffer.split('\n\n');
            buffer = frames.pop() ?? '';
            for (const frame of frames) {
                const delta = parseSseFrame(frame);
                if (delta === null) {
                    // [DONE] sentinel — stream is finished.
                    handlers.completeAssistantMessage(sessionId, assistantText);
                    return;
                }
                // The aigw hub forwards upstream failures (e.g. Google Code Assist's
                // "User location is not supported" region lock) as a
                // `data: {"error": {"message": ...}}` SSE frame with HTTP 200 — the
                // generator raised inside the stream, so the server can't change the
                // status code. Surface it instead of silently completing an empty turn.
                if (delta.error) {
                    handlers.failAssistantMessage(sessionId, delta.error);
                    return;
                }
                if (delta.content) {
                    sawAnyChunk = true;
                    assistantText += delta.content;
                    handlers.appendAssistantDelta(sessionId, delta.content);
                }
                if (delta.reasoning) {
                    sawAnyChunk = true;
                    reasoningText += delta.reasoning;
                    handlers.appendReasoningDelta(sessionId, delta.reasoning);
                }
            }
        }
        // Stream ended without an explicit [DONE] (some gateways close the body
        // instead). Finalize with whatever text we accumulated.
        if (sawAnyChunk || assistantText) {
            handlers.completeAssistantMessage(sessionId, assistantText);
        }
        else {
            handlers.failAssistantMessage(sessionId, 'Quota hub stream ended with no content.');
        }
    }
    catch (err) {
        if (signal.aborted) {
            // Abort mid-stream: finalize the partial text so the bubble keeps what
            // arrived (mirrors cancelRun's finalize for backend turns).
            handlers.completeAssistantMessage(sessionId, assistantText);
            return;
        }
        handlers.failAssistantMessage(sessionId, friendlyAigwError(err, 'Quota hub stream failed.'));
    }
}
/** Returns null for the [DONE] sentinel, otherwise the concatenated delta. */
function parseSseFrame(frame) {
    const lines = frame.split('\n');
    let dataLine = '';
    for (const line of lines) {
        const trimmed = line.trimStart();
        if (trimmed.startsWith('data:')) {
            dataLine += trimmed.slice(5).trimStart();
        }
    }
    if (!dataLine) {
        return { content: '', reasoning: '' };
    }
    if (dataLine.trim() === '[DONE]') {
        return null;
    }
    try {
        const parsed = JSON.parse(dataLine);
        // Upstream error envelope forwarded by the aigw hub (see main.py:_sse).
        if (parsed.error && typeof parsed.error.message === 'string') {
            return { content: '', reasoning: '', error: parsed.error.message };
        }
        const delta = parsed.choices?.[0]?.delta ?? {};
        return {
            content: typeof delta.content === 'string' ? delta.content : '',
            reasoning: typeof delta.reasoning === 'string'
                ? delta.reasoning
                : typeof delta.reasoning_content === 'string'
                    ? delta.reasoning_content
                    : ''
        };
    }
    catch {
        // A malformed JSON chunk (rare; some gateways emit keepalive comments).
        // Skip it rather than failing the whole stream.
        return { content: '', reasoning: '' };
    }
}
function friendlyAigwError(err, fallback) {
    if (err instanceof Error && err.message) {
        return `${fallback} (${err.message})`;
    }
    return fallback;
}
