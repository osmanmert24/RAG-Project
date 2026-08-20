import json
import re

from foundry_local_sdk import Configuration, FoundryLocalManager
from openai import OpenAI

from .config import settings

_client = OpenAI(base_url=settings.FOUNDRY_BASE_URL, api_key="not-needed")

_embed_model = None
_embed_client = None

_SENTENCE_END = re.compile(r"[.!?\n]\s*$")
_WORD = re.compile(r"\S+")


def _normalize_sentence(text: str) -> str:
    """Rakamları maskeleyerek "6 gün kalmış" / "14 gün kalmış" gibi kalıp-aynı
    tekrarları da yakalar, sadece birebir aynı cümleleri değil."""
    return re.sub(r"\d+", "#", text.strip().lower())


def _find_repetition_cut(text: str, min_words: int = 4, max_words: int = 25) -> int | None:
    """Art arda tekrarlanan bir kelime öbeği bulursa tekrarın başladığı karakter
    pozisyonunu döner. Küçük, quantize modeller bazen aynı ifadeyi hiç noktalama
    koymadan onlarca kez art arda üretiyor (bkz. LEARNING.md Hata Defteri);
    cümle-sonu noktalamasına dayanan bir kontrol bunu hiç fark edemez çünkü tüm
    tekrar tek bir "cümle" olarak görünür. Bu yüzden noktalamadan bağımsız,
    doğrudan kelime dizisi üzerinde çalışır."""
    matches = list(_WORD.finditer(text))
    words = [m.group().lower() for m in matches]
    n = len(words)
    for i in range(min_words, n):
        for length in range(min_words, min(max_words, i) + 1):
            if words[i - length : i] == words[i : i + length]:
                return matches[i].start()
    return None


def _truncate_repetition(text: str) -> str:
    """Küçük, quantize modeller bazen aynı cümleyi/öbeği art arda tekrarlayarak
    dejenere oluyor. Önce noktalamadan bağımsız kelime-öbeği tekrarını, ardından
    (rakam farkı olabilecek) tam cümle tekrarını keser."""
    cut = _find_repetition_cut(text)
    if cut is not None:
        text = text[:cut].strip()

    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    prev_norm = None
    for i, sentence in enumerate(sentences):
        norm = _normalize_sentence(sentence)
        if norm and norm == prev_norm:
            return " ".join(sentences[:i]).strip()
        if norm:
            prev_norm = norm
    return text


def chat(messages: list[dict], temperature: float, max_tokens: int) -> str:
    if settings.DEBUG_LOG:
        print("\n[DEBUG] ==== Modele giden nihai mesajlar ====")
        for m in messages:
            print(f"[{m['role']}] {m['content']}")
        print("[DEBUG] =====================================\n")

    response = _client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if settings.DEBUG_LOG:
        print("[DEBUG] ==== Foundry ham yanıtı ====")
        print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2))
        print("[DEBUG] =============================\n")

    content = response.choices[0].message.content or ""
    return _truncate_repetition(content)


def chat_stream(messages: list[dict], temperature: float, max_tokens: int):
    if settings.DEBUG_LOG:
        print("\n[DEBUG] ==== Modele giden nihai mesajlar (stream) ====")
        for m in messages:
            print(f"[{m['role']}] {m['content']}")
        print("[DEBUG] ===============================================\n")

    stream = _client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    accumulated = ""
    last_boundary = 0
    prev_norm = None
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        accumulated += delta
        yield delta

        if _find_repetition_cut(accumulated) is not None:
            break  # tekrar döngüsü: noktalamasız kelime-öbeği tekrarı

        if _SENTENCE_END.search(accumulated):
            sentence = accumulated[last_boundary:]
            last_boundary = len(accumulated)
            norm = _normalize_sentence(sentence)
            if norm and norm == prev_norm:
                break  # tekrar döngüsü: cümle düzeyinde (rakam farkı olabilir)
            if norm:
                prev_norm = norm


def _get_embed_model():
    # FoundryLocalManager, SDK içinde process-genelinde bir singleton: constructor
    # ikinci kez çağrılırsa "already initialized" hatası fırlatıyor. Bu yüzden
    # manager'ı (ve seçilen model/variant'ı) bir kez kurup burada saklıyoruz;
    # asla yeniden oluşturmuyoruz.
    global _embed_model
    if _embed_model is not None:
        return _embed_model

    config = Configuration(app_name=settings.EMBED_APP_NAME)
    manager = FoundryLocalManager(config)
    model = manager.catalog.get_model(settings.EMBED_MODEL_ALIAS)
    variant = next(
        v for v in model.variants if settings.EMBED_VARIANT_DEVICE in v.id.lower()
    )
    model.select_variant(variant)
    model.download()
    model.load()

    _embed_model = model
    return _embed_model


def _get_embed_client(fresh: bool = False):
    global _embed_client
    if _embed_client is not None and not fresh:
        return _embed_client

    model = _get_embed_model()
    _embed_client = model.get_embedding_client()
    return _embed_client


def embed(texts: list[str]) -> list[list[float]]:
    client = _get_embed_client()
    try:
        response = client.generate_embeddings(texts)
    except Exception:
        # Uzun süre boşta kalan native embedding oturumu kopabiliyor
        # ("Operation was cancelled"); manager'ı koruyup sadece client'ı tazeleyerek
        # bir kez daha dene (manager'ı yeniden kurmak singleton hatası verir).
        client = _get_embed_client(fresh=True)
        response = client.generate_embeddings(texts)
    return [item.embedding for item in response.data]
