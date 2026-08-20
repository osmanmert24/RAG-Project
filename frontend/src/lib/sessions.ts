import type { ChatMessage, Source, Timings } from "@/lib/api";

export type DisplayMessage = ChatMessage & {
  mode?: "general" | "document";
  sources?: Source[];
  timings?: Timings;
};

export type ChatSession = {
  id: string;
  title: string;
  messages: DisplayMessage[];
  updatedAt: number;
};

const STORAGE_KEY = "foundry-rag-sessions";

export function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions: ChatSession[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function newSession(): ChatSession {
  return {
    id: crypto.randomUUID(),
    title: "Yeni sohbet",
    messages: [],
    updatedAt: Date.now(),
  };
}

export function titleFromMessages(messages: DisplayMessage[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return "Yeni sohbet";
  const text = firstUser.content.trim();
  return text.length > 42 ? text.slice(0, 42) + "…" : text;
}
