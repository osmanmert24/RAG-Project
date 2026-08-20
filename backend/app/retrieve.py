from dataclasses import dataclass

from . import foundry, store
from .config import settings
from .prompts import embed_query_instruction

NOTE_BELOW_THRESHOLD = "Not: Belgede ilgili bilgi bulamadım, genel bilgimle cevaplıyorum.\n\n"

# "Belge içeriği nedir" / "Bu ne anlatıyor" gibi geniş/özet soruları tek bir
# chunk'a güçlü şekilde benzemez (bkz. LEARNING.md Karar Defteri) — embedding
# skoru yapısal olarak eşiğin altında kalır. Belge zaten yüklüyken bu tür
# sorularda eşiği hiç kontrol etmeden doğrudan Mod B'yi zorluyoruz; en yakın
# chunk'lar mükemmel olmasa da hiç context vermemekten kesinlikle iyidir.
_SUMMARY_KEYWORDS = (
    "belge", "doküman", "dokuman", "dosya", "pdf",
    "içerik", "icerik", "özet", "ozet", "hakkında", "hakkinda",
)


def _is_summary_intent(query_text: str) -> bool:
    lowered = query_text.lower()
    return any(keyword in lowered for keyword in _SUMMARY_KEYWORDS)


@dataclass
class Result:
    text: str
    filename: str
    page: int
    score: float


def decide_mode(query_text: str) -> tuple[str, list[Result], str, bool]:
    """Boş koleksiyon -> general; özet niyeti -> sayfa-çeşitli genel bakış;
    eşik altı -> general + not; eşik üstü -> document. Son eleman, özet
    niyetiyle mi Mod B'ye girildiğini (farklı prompt için) bildirir."""
    if store.chunk_count() == 0:
        return "general", [], "", False

    if _is_summary_intent(query_text):
        results = overview(settings.TOP_K + 2)
        if results:
            return "document", results, "", True

    results = search(query_text, settings.TOP_K)
    if results and results[0].score >= settings.SIMILARITY_THRESHOLD:
        return "document", results, "", False
    return "general", [], NOTE_BELOW_THRESHOLD, False


def overview(limit: int) -> list[Result]:
    """Saf benzerlik aramasının özet sorularında şansa göre tek bir (ör. boş
    bir sayfa) chunk'a takılmasını önlemek için sayfa başına bir chunk alan
    temsili bir örnek döner (bkz. store.overview_chunks)."""
    rows = store.overview_chunks(limit)
    return [Result(text=r["text"], filename=r["filename"], page=r["page"], score=0.0) for r in rows]


def search(query_text: str, top_k: int) -> list[Result]:
    embedding = foundry.embed([embed_query_instruction(query_text)])[0]
    raw = store.query(embedding, top_k)

    documents = raw["documents"][0]
    metadatas = raw["metadatas"][0]
    distances = raw["distances"][0]

    return [
        Result(
            text=doc,
            filename=meta["filename"],
            page=meta["page"],
            score=1 - dist,
        )
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]
