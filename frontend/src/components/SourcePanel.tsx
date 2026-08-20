"use client";

import { useState } from "react";
import type { Source } from "@/lib/api";

export default function SourcePanel({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="mt-2 text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className="font-mono text-mute hover:text-ink transition-colors"
      >
        {open ? "▾" : "▸"} {sources.length} kaynak
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5">
          {sources.map((s, i) => (
            <li
              key={i}
              className="border border-line rounded-md p-2.5 bg-surface"
            >
              <div className="flex justify-between items-baseline gap-2 font-mono text-[10.5px] text-mute">
                <span className="truncate">
                  {s.filename} · s.{s.page}
                </span>
                <span className="shrink-0">{s.score.toFixed(3)}</span>
              </div>
              <p className="mt-1 text-ink/80 leading-snug">{s.snippet}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
