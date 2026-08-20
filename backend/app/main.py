import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from . import foundry, ingest, retrieve, store
from .config import settings
from .models import (
    ChatRequest,
    ChatResponse,
    DeleteResponse,
    DocumentsResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    Source,
    Timings,
    UploadResponse,
)
from .prompts import RAG_NOT_FOUND_SENTENCE, build_messages, contains_sentinel, resolve_sentinel

app = FastAPI(title="Foundry Local RAG")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    documents = store.list_documents()
    return HealthResponse(
        ok=True,
        chat_model=settings.CHAT_MODEL,
        embed_model=settings.EMBED_MODEL_ALIAS,
        endpoint=settings.FOUNDRY_BASE_URL,
        document_count=len(documents),
        chunk_count=store.chunk_count(),
    )


def _plan_chat(req: ChatRequest) -> tuple[str, list[Source], list[dict], float, str, int, bool]:
    t_retrieval = time.perf_counter()
    mode, results, note, is_summary = retrieve.decide_mode(req.message)
    retrieval_ms = int((time.perf_counter() - t_retrieval) * 1000)

    sources = [
        Source(filename=r.filename, page=r.page, score=r.score, snippet=r.text[:200])
        for r in results
    ] if mode == "document" else []
    rag_chunks = [(r.text, r.filename, r.page) for r in results] if mode == "document" else []

    history = [{"role": h.role, "content": h.content} for h in req.history]
    messages = build_messages(mode, req.message, history, rag_chunks, is_summary)
    temperature = settings.TEMPERATURE_RAG if mode == "document" else settings.TEMPERATURE_GENERAL

    return mode, sources, messages, temperature, note, retrieval_ms, is_summary


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    t0 = time.perf_counter()
    mode, sources, messages, temperature, note, retrieval_ms, is_summary = _plan_chat(req)

    content = foundry.chat(messages, temperature=temperature, max_tokens=settings.MAX_TOKENS)
    if mode == "document" and not is_summary and contains_sentinel(content):
        content = RAG_NOT_FOUND_SENTENCE
    answer = note + content
    generation_ms = int((time.perf_counter() - t0) * 1000) - retrieval_ms

    return ChatResponse(
        mode=mode,
        answer=answer,
        sources=sources,
        timings=Timings(retrieval_ms=retrieval_ms, generation_ms=generation_ms),
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    mode, sources, messages, temperature, note, retrieval_ms, is_summary = _plan_chat(req)

    def events():
        meta = {"mode": mode, "sources": [s.model_dump() for s in sources], "retrieval_ms": retrieval_ms}
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        if note:
            yield f"event: token\ndata: {json.dumps(note, ensure_ascii=False)}\n\n"
        raw_tokens = foundry.chat_stream(messages, temperature=temperature, max_tokens=settings.MAX_TOKENS)
        tokens = resolve_sentinel(raw_tokens) if mode == "document" and not is_summary else raw_tokens
        for token in tokens:
            yield f"event: token\ndata: {json.dumps(token, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/upload", response_model=UploadResponse)
def upload(file: UploadFile = File(...)) -> UploadResponse:
    doc_id = uuid.uuid4().hex
    dest = settings.upload_path / f"{doc_id}_{file.filename}"
    dest.write_bytes(file.file.read())

    pages = ingest.pdf_to_pages(dest)
    uploaded_at = datetime.now(timezone.utc).isoformat()
    chunks = ingest.chunk_pages(pages, doc_id, file.filename, uploaded_at)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="Bu PDF'ten metin çıkarılamadı (taranmış görüntü olabilir).",
        )

    embeddings = foundry.embed([c.text for c in chunks])
    store.add_chunks(chunks, embeddings)

    return UploadResponse(
        doc_id=doc_id, filename=file.filename, pages=len(pages), chunks=len(chunks)
    )


@app.get("/documents", response_model=DocumentsResponse)
def documents() -> DocumentsResponse:
    return DocumentsResponse(documents=store.list_documents())


@app.delete("/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(doc_id: str) -> DeleteResponse:
    deleted = store.delete_document(doc_id)
    return DeleteResponse(ok=True, deleted_chunks=deleted)


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    results = retrieve.search(req.query, req.top_k)
    return SearchResponse(
        results=[
            SearchResult(text=r.text, filename=r.filename, page=r.page, score=r.score)
            for r in results
        ]
    )
