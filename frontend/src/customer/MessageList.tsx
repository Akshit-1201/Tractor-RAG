import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { ChatMessage } from "./types";

// Grounded in the manuals the demo corpus actually covers.
const EXAMPLES = [
  "What does a flashing red battery light mean?",
  "How do I change the transmission fluid?",
  "What is the engine oil service interval?",
  "What does error code E-047 mean?",
];

export default function MessageList({
  messages,
  onAsk,
  busy,
}: {
  messages: ChatMessage[];
  onAsk: (question: string) => void;
  busy: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="stream">
      {messages.length === 0 ? (
        <div className="stream__empty">
          <h2>What can we help you fix today?</h2>
          <p>Ask in plain language — describe the symptom, part, or warning light.</p>
          <div className="chips">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                className="chip"
                disabled={busy}
                onClick={() => onAsk(example)}
              >
                <span className="lamp lamp--warn" />
                {example}
              </button>
            ))}
          </div>
        </div>
      ) : (
        messages.map((message, index) => <MessageBubble key={index} message={message} />)
      )}
      <div ref={bottomRef} />
    </div>
  );
}
