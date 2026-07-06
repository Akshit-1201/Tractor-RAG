import { useState } from "react";
import { Link } from "react-router-dom";
import { sendMessage, type HistoryTurn } from "../api/chat";
import { BrandMark, LockIcon } from "../components/icons";
import ThemeToggle from "../components/ThemeToggle";
import ChatInput from "./ChatInput";
import MessageList from "./MessageList";
import type { ChatMessage } from "./types";

// Recent completed turns the client replays so follow-ups ("what fluid type?")
// resolve against earlier context. Capped to stay within the server's limit.
const HISTORY_TURNS = 6;

function buildHistory(messages: ChatMessage[]): HistoryTurn[] {
  return messages
    .filter((m) => !m.streaming && m.text.trim().length > 0)
    .slice(-HISTORY_TURNS)
    .map((m) => ({ role: m.role, content: m.text }));
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  async function handleSend(question: string) {
    if (busy) return;
    setBusy(true);
    // Snapshot the prior conversation before appending this turn's placeholder.
    const history = buildHistory(messages);
    setMessages((current) => [
      ...current,
      { role: "user", text: question },
      { role: "assistant", text: "", streaming: true },
    ]);

    const appendToken = (text: string) =>
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, text: last.text + text };
        return next;
      });

    try {
      const final = await sendMessage(question, appendToken, history);
      // the final event is authoritative — canonical answer text, gated image, sources
      setMessages((current) => {
        const next = [...current];
        next[next.length - 1] = {
          role: "assistant",
          text: final.answer,
          is_answered: final.is_answered,
          sources: final.sources,
          image: final.image,
          streaming: false,
        };
        return next;
      });
    } catch (e) {
      const friendly =
        e instanceof Error && e.message.startsWith("API 429")
          ? "You're asking questions a bit too quickly — please wait a moment and try again."
          : e instanceof Error && e.message.startsWith("API 422")
            ? "That question is too long — please shorten it and try again."
            : e instanceof DOMException && e.name === "AbortError"
              ? "The request timed out — please try again."
              : "Sorry — the assistant is temporarily unavailable. Please try again.";
      setMessages((current) => {
        const next = [...current];
        next[next.length - 1] = { role: "assistant", text: friendly, streaming: false };
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="console">
      <header className="console__header">
        <Link to="/" className="brand" aria-label="Tractor Maintenance Assistant home">
          <span className="brand__mark">
            <BrandMark />
          </span>
          <span>
            <span className="brand__name">Tractor Maintenance Assistant</span>
            <br />
            <span className="brand__kicker">Service Console</span>
          </span>
        </Link>
        <div className="console__actions">
          <ThemeToggle />
          {/* Route navigation only — no admin component is imported here (role separation) */}
          <Link to="/admin/login" className="btn btn--ghost">
            <LockIcon style={{ width: 16, height: 16 }} />
            Admin
          </Link>
        </div>
      </header>

      <p className="console__status">
        <span className="lamp lamp--ok" />
        Answers come <b>only</b> from the uploaded manuals and reference images — never guessed.
      </p>

      <MessageList messages={messages} onAsk={handleSend} busy={busy} />
      <ChatInput disabled={busy} onSend={handleSend} />
    </main>
  );
}
