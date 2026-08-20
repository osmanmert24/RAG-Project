from datetime import datetime

SYSTEM_PROMPT_GENERAL = (
    "You are a helpful assistant running fully offline on the user's device.\n"
    "Answer concisely and accurately. If you are not sure about something, say so.\n"
    "Never repeat the same sentence or idea twice.\n"
    "Always answer in Turkish."
)

_TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def _today_tr() -> str:
    now = datetime.now()
    return f"{now.day} {_TR_MONTHS[now.month - 1]} {now.year}, {_TR_DAYS[now.weekday()]}"


def embed_query_instruction(query: str) -> str:
    """Qwen3-Embedding sorgu/pasaj ayrımını netleştirmek için önerilen instruction formatı."""
    return (
        "Instruct: Given a question, retrieve relevant passages that answer the question\n"
        f"Query: {query}"
    )


RAG_NOT_FOUND_SENTENCE = "Bu bilgi yüklenen belgede yok."

# Küçük, quantize modeller (Phi-4-mini) uzun bir Türkçe cümleyi harfiyen tekrar
# üretmekte güvenilir değil (bkz. LEARNING.md Karar Defteri) — bazen anlamca
# yakın ama farklı bir cümle kuruyor, bazen de context'i kullanmak yerine
# doğrudan bilmediğini uydurarak anlatıyor. Bunun yerine modelden yalnızca tek,
# belirgin bir SENTINEL kelime istiyoruz; gerçek kullanıcıya gösterilecek
# cümleyi (RAG_NOT_FOUND_SENTENCE) uygulama katmanı (main.py) deterministik
# olarak enjekte ediyor. Küçük modeller tek bir sabit kelimeyi üretmekte uzun
# bir cümleye göre çok daha tutarlı.
SENTINEL = "YETERSIZ_BAGLAM"

SYSTEM_PROMPT_RAG = (
    "You are a helpful assistant running fully offline on the user's device.\n"
    "Answer the user's question using ONLY the document excerpts given in the context below.\n"
    "Rules:\n"
    "- Do not use any knowledge outside the provided context.\n"
    f'- If the context does not contain the answer, respond with exactly this single word and nothing else: {SENTINEL}\n'
    "- When you use information from an excerpt, cite it inline like [filename s.X].\n"
    "- Never repeat the same sentence or idea twice.\n"
    "- Always answer in Turkish."
)


def contains_sentinel(text: str) -> bool:
    """Küçük model bazen "yalnızca bu kelimeyi yaz" talimatına tam uymayıp
    SENTINEL'in başına/sonuna başka metin ekliyor (gözlendi). Bu yüzden tam
    eşleşme yerine kelimenin herhangi bir yerde geçip geçmediğine bakıyoruz —
    geçiyorsa modelin tüm cevabı güvenilmez sayılır, RAG_NOT_FOUND_SENTENCE ile
    değiştirilir."""
    return SENTINEL in text


def resolve_sentinel(tokens):
    """Streaming token akışını arabelleğe alıp modelin SENTINEL kelimesini
    ürettiği durumu yakalar ve kullanıcıya SENTINEL yerine RAG_NOT_FOUND_SENTENCE
    akıtır. Model talimata tam uymayıp SENTINEL'in etrafına başka metin
    ekleyebildiği için (gözlendi) tüm cevap tamamlanana kadar arabellekte
    tutulup sonunda tek seferde kontrol edilir; SENTINEL yoksa arabellek olduğu
    gibi akıtılır."""
    buffer = "".join(tokens)
    if contains_sentinel(buffer):
        yield RAG_NOT_FOUND_SENTENCE
    else:
        yield buffer


# "Bu belge ne hakkında?" gibi özet sorularında SYSTEM_PROMPT_RAG'ın "ya kesin
# bir cevap bul ya da YETERSIZ de" katılığı ters tepiyor: özetlenecek tek bir
# "cevap" yok, model de context'i görmezden gelip YETERSIZ diyor (gözlendi).
# Bu sorular için ayrı, sentinel talep etmeyen, açıkça "reddetme, anlat" diyen
# bir prompt kullanıyoruz.
SYSTEM_PROMPT_SUMMARY = (
    "You are a helpful assistant running fully offline on the user's device.\n"
    "The user wants to know, in general terms, what this document is about.\n"
    "Below are excerpts from different pages of the document.\n"
    "Write a short, general description of what topics/content the document covers, based on "
    "these excerpts.\n"
    "Do not refuse and do not say the information is missing — describe the document using what "
    "is visible in the excerpts, even if they do not cover every detail.\n"
    "Never repeat the same sentence or idea twice.\n"
    "Always answer in Turkish."
)


def build_rag_user_message(query: str, chunks: list[tuple[str, str, int]]) -> str:
    """chunks: (text, filename, page) üçlüleri, en fazla TOP_K adet."""
    context = "\n\n".join(f"[{filename} s.{page}]\n{text}" for text, filename, page in chunks)
    return f"Bağlam:\n{context}\n\nSoru: {query}"


def build_messages(
    mode: str,
    message: str,
    history: list[dict],
    rag_chunks: list[tuple[str, str, int]],
    is_summary: bool = False,
) -> list[dict]:
    if mode == "document":
        system = SYSTEM_PROMPT_SUMMARY if is_summary else SYSTEM_PROMPT_RAG
        user_content = build_rag_user_message(message, rag_chunks)
    else:
        system = SYSTEM_PROMPT_GENERAL
        user_content = message

    system += f"\nBugünün tarihi: {_today_tr()}."

    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages
