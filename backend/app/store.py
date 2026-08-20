import chromadb

from .config import settings
from .ingest import Chunk

_client = chromadb.PersistentClient(path=str(settings.chroma_path))
_collection = _client.get_or_create_collection(
    "docs", metadata={"hnsw:space": "cosine"}
)


def add_chunks(chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    _collection.add(
        ids=[f"{c.doc_id}-{c.chunk_index}" for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "doc_id": c.doc_id,
                "filename": c.filename,
                "page": c.page,
                "chunk_index": c.chunk_index,
                "total_pages": c.total_pages,
                "uploaded_at": c.uploaded_at,
            }
            for c in chunks
        ],
    )


def query(embedding: list[float], top_k: int) -> dict:
    return _collection.query(query_embeddings=[embedding], n_results=top_k)


def chunk_count() -> int:
    return _collection.count()


def overview_chunks(limit: int) -> list[dict]:
    """Sayfa başına bir chunk alarak belgenin genelini temsil eden bir örnek
    döner. "Bu belge ne hakkında?" gibi özet sorularında saf benzerlik araması
    şansa göre tek bir (ör. boş bir alıştırma sayfası) chunk'a takılabiliyor;
    bu, sayfalara yayılan daha temsili bir örnekleme sağlıyor."""
    data = _collection.get(include=["documents", "metadatas"])
    best_per_page: dict[tuple[str, int], dict] = {}
    for text, meta in zip(data["documents"], data["metadatas"]):
        key = (meta["doc_id"], meta["page"])
        if key not in best_per_page or meta["chunk_index"] < best_per_page[key]["chunk_index"]:
            best_per_page[key] = {
                "text": text,
                "filename": meta["filename"],
                "page": meta["page"],
                "chunk_index": meta["chunk_index"],
            }
    ordered = sorted(best_per_page.values(), key=lambda r: (r["filename"], r["page"]))
    return ordered[:limit]


def list_documents() -> list[dict]:
    data = _collection.get(include=["metadatas"])
    by_doc: dict[str, dict] = {}
    for meta in data["metadatas"]:
        doc_id = meta["doc_id"]
        entry = by_doc.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "filename": meta["filename"],
                "pages": meta["total_pages"],
                "chunks": 0,
                "uploaded_at": meta["uploaded_at"],
            },
        )
        entry["chunks"] += 1
    return list(by_doc.values())


def delete_document(doc_id: str) -> int:
    existing = _collection.get(where={"doc_id": doc_id}, include=[])
    count = len(existing["ids"])
    if count:
        _collection.delete(where={"doc_id": doc_id})
    return count
