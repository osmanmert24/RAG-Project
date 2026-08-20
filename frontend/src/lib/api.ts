export type ChatMessage = { role: "user" | "assistant"; content: string };

export type Source = {
  filename: string;
  page: number;
  score: number;
  snippet: string;
};

export type Timings = { retrieval_ms: number; generation_ms: number };

export type ChatResponse = {
  mode: "general" | "document";
  answer: string;
  sources: Source[];
  timings: Timings;
};

export async function sendChat(
  message: string,
  history: ChatMessage[]
): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) throw new Error(`Chat isteği başarısız: ${res.status}`);
  return res.json();
}

export type ChatMeta = {
  mode: "general" | "document";
  sources: Source[];
  retrieval_ms: number;
};

export async function sendChatStream(
  message: string,
  history: ChatMessage[],
  handlers: {
    onMeta: (meta: ChatMeta) => void;
    onToken: (text: string) => void;
    onDone: () => void;
  }
): Promise<void> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok || !res.body) throw new Error(`Chat stream başarısız: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);

      const eventLine = block.split("\n").find((l) => l.startsWith("event: "));
      const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
      if (!eventLine || !dataLine) continue;
      const event = eventLine.slice("event: ".length);
      const data = dataLine.slice("data: ".length);

      if (event === "meta") handlers.onMeta(JSON.parse(data));
      else if (event === "token") handlers.onToken(JSON.parse(data));
      else if (event === "done") handlers.onDone();
    }
  }
}

export type HealthResponse = {
  ok: boolean;
  chat_model: string;
  embed_model: string;
  endpoint: string;
  document_count: number;
  chunk_count: number;
};

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`Health check başarısız: ${res.status}`);
  return res.json();
}

export type UploadResponse = {
  doc_id: string;
  filename: string;
  pages: number;
  chunks: number;
};

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: formData });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Yükleme başarısız: ${res.status}`);
  }
  return res.json();
}

export type DocumentInfo = {
  doc_id: string;
  filename: string;
  pages: number;
  chunks: number;
  uploaded_at: string;
};

export async function getDocuments(): Promise<DocumentInfo[]> {
  const res = await fetch("/api/documents");
  if (!res.ok) throw new Error(`Belge listesi alınamadı: ${res.status}`);
  const data = await res.json();
  return data.documents;
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`/api/documents/${docId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Silme başarısız: ${res.status}`);
}

export type SearchResult = {
  text: string;
  filename: string;
  page: number;
  score: number;
};

export async function searchDocuments(
  query: string,
  topK = 3
): Promise<SearchResult[]> {
  const res = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) throw new Error(`Arama başarısız: ${res.status}`);
  const data = await res.json();
  return data.results;
}
