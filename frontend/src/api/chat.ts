// Customer chat client (spec §10.5): SSE via fetch + ReadableStream — EventSource
// cannot POST — with a plain-JSON fallback when the server doesn't stream.

export interface Source {
  type: string;
  name: string;
  chunk_id: number;
}

export interface ImageRef {
  url: string;
  caption: string | null;
}

export interface ChatResponse {
  answer: string;
  is_answered: boolean;
  sources: Source[];
  image: ImageRef | null;
}

// Recent turns replayed for follow-up understanding. The server uses them only to
// rewrite the new question into a standalone one — never as an answer source.
export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
}

// Single source of truth is MAX_QUESTION_CHARS in .env — compose passes it in as
// VITE_MAX_QUESTION_CHARS (frontend restart required to pick up changes).
export const MAX_QUESTION_CHARS = Number(import.meta.env.VITE_MAX_QUESTION_CHARS ?? 1000);

export async function sendMessage(
  question: string,
  onToken: (text: string) => void,
  history: HistoryTurn[] = [],
  timeoutMs = 60_000,
): Promise<ChatResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, history }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`API ${response.status}: ${await response.text()}`);
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("text/event-stream") || !response.body) {
      return (await response.json()) as ChatResponse; // JSON fallback
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let final: ChatResponse | null = null;

    const handleBlock = (block: string) => {
      const lines = block.split("\n");
      const eventLine = lines.find((line) => line.startsWith("event: "));
      const dataLine = lines.find((line) => line.startsWith("data: "));
      if (!eventLine || !dataLine) return;
      const name = eventLine.slice(7).trim();
      const data = JSON.parse(dataLine.slice(6));
      if (name === "token") onToken(data.text as string);
      else if (name === "final") final = data as ChatResponse;
      else if (name === "error") throw new Error(data.detail as string);
    };

    const drainBuffer = () => {
      let separator;
      while ((separator = buffer.indexOf("\n\n")) !== -1) {
        handleBlock(buffer.slice(0, separator));
        buffer = buffer.slice(separator + 2);
      }
    };

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        drainBuffer();
      }
      buffer += decoder.decode(); // flush any bytes held by the decoder
      drainBuffer();
    } finally {
      reader.cancel().catch(() => {}); // no-op when already done; frees the stream on error
    }

    if (!final) {
      throw new Error("Stream ended without a final event");
    }
    return final;
  } finally {
    clearTimeout(timer);
  }
}
