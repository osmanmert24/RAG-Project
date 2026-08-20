from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class Source(BaseModel):
    filename: str
    page: int
    score: float
    snippet: str


class Timings(BaseModel):
    retrieval_ms: int
    generation_ms: int


class ChatResponse(BaseModel):
    mode: str
    answer: str
    sources: list[Source] = []
    timings: Timings


class HealthResponse(BaseModel):
    ok: bool
    chat_model: str
    embed_model: str
    endpoint: str
    document_count: int
    chunk_count: int


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    pages: int
    chunks: int


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    pages: int
    chunks: int
    uploaded_at: str


class DocumentsResponse(BaseModel):
    documents: list[DocumentInfo]


class DeleteResponse(BaseModel):
    ok: bool
    deleted_chunks: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = 3


class SearchResult(BaseModel):
    text: str
    filename: str
    page: int
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
