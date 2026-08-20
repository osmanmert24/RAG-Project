"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Chat from "@/components/Chat";
import DocumentList from "@/components/DocumentList";
import Seal from "@/components/Seal";
import {
  getDocuments,
  getHealth,
  searchDocuments,
  type DocumentInfo,
  type SearchResult,
} from "@/lib/api";
import {
  loadSessions,
  saveSessions,
  newSession,
  titleFromMessages,
  type ChatSession,
  type DisplayMessage,
} from "@/lib/sessions";

export default function Home() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugQuery, setDebugQuery] = useState("");
  const [debugResults, setDebugResults] = useState<SearchResult[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const refreshDocuments = useCallback(() => {
    getDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, []);

  useEffect(() => {
    refreshDocuments();
    getHealth()
      .then((h) => setConnected(h.ok))
      .catch(() => setConnected(false));

    // One-time hydration from localStorage: must run post-mount (SSR has no
    // window), so the empty-state first paint matches the server and this
    // effect syncs in the persisted sessions right after, like reading any
    // other external store.
    const stored = loadSessions();
    if (stored.length > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- see comment above
      setSessions(stored);
      setActiveId(stored[0].id);
    } else {
      const first = newSession();
      setSessions([first]);
      setActiveId(first.id);
    }
  }, [refreshDocuments]);

  const active = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId]
  );

  function persist(next: ChatSession[]) {
    setSessions(next);
    saveSessions(next);
  }

  function handleMessagesChange(messages: DisplayMessage[]) {
    if (!activeId) return;
    const next = sessions.map((s) =>
      s.id === activeId
        ? { ...s, messages, title: titleFromMessages(messages), updatedAt: Date.now() }
        : s
    );
    persist(next);
  }

  function handleNewSession() {
    const created = newSession();
    persist([created, ...sessions]);
    setActiveId(created.id);
    setDrawerOpen(false);
  }

  function handleSelectSession(id: string) {
    setActiveId(id);
    setDrawerOpen(false);
  }

  function handleDeleteSession(id: string) {
    const remaining = sessions.filter((s) => s.id !== id);
    const next = remaining.length > 0 ? remaining : [newSession()];
    persist(next);
    if (activeId === id) {
      setActiveId(next[0].id);
    }
  }

  async function handleDebugSearch() {
    if (!debugQuery.trim()) return;
    const results = await searchDocuments(debugQuery, 3);
    setDebugResults(results);
  }

  const orderedSessions = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <div className="flex h-screen flex-col bg-paper text-ink">
      <header className="flex items-center gap-3 border-b border-line px-4 sm:px-5 py-3.5 shrink-0">
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Menüyü aç"
          className="md:hidden shrink-0 border border-line rounded-md w-8 h-8 flex items-center justify-center text-mute hover:text-ink"
        >
          <span className="sr-only">Menü</span>
          ☰
        </button>
        <Seal />
        <div className="leading-tight min-w-0">
          <h1 className="font-mono text-[15px] font-semibold tracking-tight">
            Foundry Local
          </h1>
          <p className="text-[11px] text-mute font-mono hidden sm:block">
            çevrimdışı belge asistanı
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[11px] font-mono text-mute shrink-0">
          <span
            className={`status-dot h-1.5 w-1.5 rounded-full ${
              connected === null
                ? "bg-mute"
                : connected
                  ? "status-dot--live text-verified bg-verified"
                  : "text-danger bg-danger"
            }`}
          />
          <span className="hidden sm:inline">
            {connected === null
              ? "kontrol ediliyor"
              : connected
                ? "cihazda çalışıyor"
                : "bağlantı yok"}
          </span>
        </div>
      </header>

      <div className="flex flex-1 min-h-0 relative">
        {drawerOpen && (
          <div
            onClick={() => setDrawerOpen(false)}
            className="fixed inset-0 bg-black/40 z-30 md:hidden"
          />
        )}
        <aside
          className={`fixed inset-y-0 left-0 z-40 w-[280px] bg-paper border-r border-line flex flex-col overflow-y-auto transition-transform duration-200 md:static md:z-auto md:w-[280px] md:shrink-0 md:translate-x-0 ${
            drawerOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="p-3">
            <button
              onClick={() => setDrawerOpen(false)}
              className="md:hidden text-mute hover:text-ink text-xs mb-2"
            >
              ✕ Kapat
            </button>
            <button
              onClick={handleNewSession}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-line-strong px-3 py-2 text-sm hover:bg-surface-sunken transition-colors"
            >
              <span className="text-base leading-none">+</span> Yeni Sohbet
            </button>
          </div>

          <nav className="px-3 space-y-0.5">
            {orderedSessions.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded-md transition-colors ${
                  s.id === activeId ? "bg-surface-sunken" : "hover:bg-surface-sunken"
                }`}
              >
                <button
                  onClick={() => handleSelectSession(s.id)}
                  className={`flex-1 min-w-0 text-left truncate text-[13px] px-2.5 py-1.5 ${
                    s.id === activeId ? "text-ink" : "text-mute hover:text-ink"
                  }`}
                >
                  {s.title}
                </button>
                <button
                  onClick={() => handleDeleteSession(s.id)}
                  aria-label={`"${s.title}" sohbetini sil`}
                  className="shrink-0 mr-1.5 text-mute hover:text-danger transition-colors opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-xs"
                >
                  Sil
                </button>
              </div>
            ))}
          </nav>

          <div className="p-4 space-y-2">
            <h2 className="text-[11px] font-mono uppercase tracking-wider text-mute">
              Belgeler <span className="text-mute/70">({documents.length})</span>
            </h2>
            <DocumentList documents={documents} onChanged={refreshDocuments} />
          </div>

          <div className="mt-auto border-t border-line p-4">
            <button
              onClick={() => setDebugOpen((v) => !v)}
              className="text-[11px] font-mono uppercase tracking-wider text-mute hover:text-ink transition-colors"
            >
              {debugOpen ? "▾" : "▸"} Gelişmiş: ham arama
            </button>
            {debugOpen && (
              <div className="mt-2.5 space-y-2">
                <div className="flex gap-1.5">
                  <input
                    className="flex-1 min-w-0 border border-line rounded px-2 py-1 text-xs bg-surface"
                    placeholder="sorgu..."
                    value={debugQuery}
                    onChange={(e) => setDebugQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleDebugSearch()}
                  />
                  <button
                    onClick={handleDebugSearch}
                    className="text-xs border border-line rounded px-2.5 hover:bg-surface-sunken transition-colors shrink-0"
                  >
                    Ara
                  </button>
                </div>
                <ul className="space-y-1.5 text-xs">
                  {debugResults.map((r, i) => (
                    <li key={i} className="border border-line rounded p-1.5 bg-surface">
                      <div className="flex justify-between text-mute font-mono text-[10px]">
                        <span>
                          {r.filename} s.{r.page}
                        </span>
                        <span>{r.score.toFixed(3)}</span>
                      </div>
                      <p className="truncate">{r.text}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </aside>

        <main className="flex-1 min-w-0">
          {active && (
            <Chat
              key={active.id}
              messages={active.messages}
              onMessagesChange={handleMessagesChange}
              onDocumentUploaded={refreshDocuments}
            />
          )}
        </main>
      </div>
    </div>
  );
}
