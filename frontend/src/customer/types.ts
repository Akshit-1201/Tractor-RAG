import type { ImageRef, Source } from "../api/chat";

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  is_answered?: boolean;
  sources?: Source[];
  image?: ImageRef | null;
  streaming?: boolean;
}
