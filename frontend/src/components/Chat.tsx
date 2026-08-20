"use client";

import { useEffect, useRef, useState } from "react";
import { sendChatStream, uploadDocument, type ChatMessage } from "@/lib/api";
import type { DisplayMessage } from "@/lib/sessions";
import SourcePanel from "@/components/SourcePanel";
import Seal from "@/components/Seal";

const EXAMPLES = [
  "Yıllık izin hakkım kaç gün?",
  "Uzaktan çalışma haftada kaç gün?",
  "Masraf iadesi kaç gün içinde ödenir?",
];

export default function Chat({
  messages,
  onMessagesChange,
  onDocumentUploaded,
}: {
  messages: DisplayMessage[];
  onMessagesChange: (messages: DisplayMessage[]) => void;
  onDocumentUploaded: () => void;
}) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef(messages);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleFile(file: File) {
    setUploadError(null);
    setUploadStatus(`${file.name} ekleniyor...`);
    try {
      const res = await uploadDocument(file);
      setUploadStatus(`${res.filename} eklendi — ${res.pages} sayfa, ${res.chunks} parça`);
      onDocumentUploaded();
    } catch (e) {
      setUploadStatus(null);
      setUploadError(e instanceof Error ? e.message : "Belge yüklenemedi");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    const history: ChatMessage[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));
    const nextHistory = [...messages, { role: "user", content: text } as DisplayMessage];
    const assistantIndex = nextHistory.length;
    const seeded = [...nextHistory, { role: "assistant", content: "" } as DisplayMessage];
    messagesRef.current = seeded;
    onMessagesChange(seeded);
    setInput("");
    setLoading(true);

    let retrievalMs = 0;
    // eslint-disable-next-line react-hooks/purity -- runs only inside this click/enter handler, never during render
    const t0 = performance.now();

    // Synchronously tracks the latest messages within this send, independent of
    // React's render cycle — onToken can fire many times before a re-render lands.
    function updateAssistant(patch: Partial<DisplayMessage>) {
      const copy = [...messagesRef.current];
      copy[assistantIndex] = { ...copy[assistantIndex], ...patch };
      messagesRef.current = copy;
      onMessagesChange(copy);
    }

    try {
      await sendChatStream(text, history, {
        onMeta: (meta) => {
          retrievalMs = meta.retrieval_ms;
          updateAssistant({ mode: meta.mode, sources: meta.sources });
        },
        onToken: (token) => {
          const current = messagesRef.current[assistantIndex];
          updateAssistant({ content: current.content + token });
        },
        onDone: () => {
          const generation_ms = Math.round(performance.now() - t0);
          updateAssistant({ timings: { retrieval_ms: retrievalMs, generation_ms } });
        },
      });
    } catch {
      updateAssistant({ content: "Bağlantı hatası: backend'e ulaşılamadı." });
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  return (
    <div
      className="flex flex-col h-full relative"
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
      }}
    >
      {dragOver && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-paper/90 border-2 border-dashed border-ember m-3 rounded-lg pointer-events-none">
          <p className="text-sm text-ember font-mono">{"PDF'i buraya bırakın"}</p>
        </div>
      )}

      {messages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <Seal size={40} />
          <h2 className="mt-4 font-mono text-xl font-semibold tracking-tight">
            Sorun, belgeniz cevaplasın.
          </h2>
          <p className="mt-2 max-w-sm text-sm text-mute">
            Bir PDF ekleyin ve içeriğiyle ilgili soru sorun. Belge yoksa da genel
            sorularınızı yanıtlarım — her iki durumda da hiçbir şey bu cihazın
            dışına çıkmaz.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-md">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => handleSend(ex)}
                className="text-[13px] border border-line rounded-full px-3.5 py-1.5 text-mute hover:text-ink hover:border-line-strong transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="max-w-2xl mx-auto space-y-5">
            {messages.map((m, i) => {
              const isLast = i === messages.length - 1;
              if (m.role === "user") {
                return (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-ink text-paper px-3.5 py-2 text-[14.5px] whitespace-pre-wrap">
                      {m.content}
                    </div>
                  </div>
                );
              }
              const accent = m.mode === "document" ? "var(--verified)" : "var(--ember)";
              const isEmpty = m.content === "" && loading && isLast;
              return (
                <div
                  key={i}
                  className="max-w-[85%] border-l-2 pl-3.5"
                  style={{ borderColor: m.mode ? accent : "var(--line)" }}
                >
                  {m.mode && (
                    <span
                      className="inline-flex items-center gap-1.5 mb-1.5 text-[10.5px] font-mono uppercase tracking-wider"
                      style={{ color: accent }}
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-current" />
                      {m.mode === "document" ? "Belgeden" : "Genel bilgi"}
                    </span>
                  )}
                  <div className="text-[14.5px] leading-relaxed whitespace-pre-wrap">
                    {isEmpty ? (
                      <span className="inline-flex gap-1 py-1">
                        <span className="h-1.5 w-1.5 rounded-full bg-mute animate-bounce [animation-delay:-0.3s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-mute animate-bounce [animation-delay:-0.15s]" />
                        <span className="h-1.5 w-1.5 rounded-full bg-mute animate-bounce" />
                      </span>
                    ) : (
                      m.content
                    )}
                  </div>
                  {m.timings && (
                    <p className="mt-1.5 text-[10.5px] font-mono text-mute">
                      {m.timings.retrieval_ms}ms getirme · {m.timings.generation_ms}ms üretim
                    </p>
                  )}
                  {m.sources && m.sources.length > 0 && <SourcePanel sources={m.sources} />}
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
        </div>
      )}

      <div className="border-t border-line p-4">
        <div className="max-w-2xl mx-auto">
          {(uploadStatus || uploadError) && (
            <p
              className={`mb-2 text-xs font-mono ${uploadError ? "text-danger" : "text-verified"}`}
            >
              {uploadError ?? uploadStatus}
            </p>
          )}
          <div className="flex gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              aria-label="Belge ekle"
              title="Belge ekle (PDF)"
              className="shrink-0 h-[42px] w-[42px] rounded-full border border-line flex items-center justify-center text-mute hover:text-ink hover:border-line-strong transition-colors text-lg leading-none"
            >
              +
            </button>
            <input
              ref={inputRef}
              className="flex-1 border border-line rounded-full px-4 py-2.5 text-sm bg-surface focus-visible:outline-2 focus-visible:outline-focus"
              placeholder="Bir soru sorun..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
            />
            <button
              className="bg-ink text-paper text-sm font-medium rounded-full px-5 py-2.5 disabled:opacity-40 transition-opacity"
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
            >
              Gönder
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
