import { useState, type FormEvent, type KeyboardEvent } from "react";
import { MAX_QUESTION_CHARS } from "../api/chat";
import { SendIcon } from "../components/icons";

export default function ChatInput({
  disabled,
  onSend,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const [value, setValue] = useState("");

  function submit() {
    const question = value.trim();
    if (!question || disabled) return;
    setValue("");
    onSend(question);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  // Enter sends; Shift+Enter inserts a newline.
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const remaining = MAX_QUESTION_CHARS - value.length;
  const nearLimit = remaining <= 100;

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer__wrap">
        <label htmlFor="chat-input" className="sr-only" style={{ position: "absolute", left: -9999 }}>
          Ask a maintenance question
        </label>
        <textarea
          id="chat-input"
          className="composer__field"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your tractor…"
          maxLength={MAX_QUESTION_CHARS}
          rows={1}
          autoComplete="off"
        />
        <div className="composer__meta">
          {nearLimit && <span className="composer__count mono">{remaining}</span>}
          <button
            type="submit"
            className="send"
            disabled={disabled || !value.trim()}
            aria-label="Send question"
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </form>
  );
}
