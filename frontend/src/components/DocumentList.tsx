"use client";

import { deleteDocument, type DocumentInfo } from "@/lib/api";

export default function DocumentList({
  documents,
  onChanged,
}: {
  documents: DocumentInfo[];
  onChanged: () => void;
}) {
  async function handleDelete(docId: string) {
    await deleteDocument(docId);
    onChanged();
  }

  if (documents.length === 0) {
    return (
      <p className="text-xs text-mute leading-relaxed">
        Henüz belge yok. Bir PDF ekleyin, sohbette içeriğinden alıntı yapayım.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {documents.map((doc) => (
        <li
          key={doc.doc_id}
          className="group flex items-start justify-between gap-2 rounded-md border border-line px-2.5 py-2 bg-surface"
        >
          <div className="min-w-0">
            <p className="text-[13px] truncate">{doc.filename}</p>
            <p className="text-[10.5px] font-mono text-mute mt-0.5">
              {doc.pages} sayfa · {doc.chunks} parça
            </p>
          </div>
          <button
            onClick={() => handleDelete(doc.doc_id)}
            aria-label={`${doc.filename} belgesini sil`}
            className="shrink-0 text-mute hover:text-danger transition-colors opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-xs"
          >
            Sil
          </button>
        </li>
      ))}
    </ul>
  );
}
