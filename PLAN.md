# PLAN.md — Agent Talimat Dosyası

**Proje:** Foundry Local + Phi-4-mini ile tamamen offline çalışan RAG uygulaması
**Bu dosyanın okuyucusu:** Kodu yazan AI agent (Claude Code / Cursor / Codex)

---

## 0. AGENT KURALLARI

Bu bölüm diğer tüm bölümlerden önceliklidir. Her oturumun başında yeniden oku.

### 0.1 ZORUNLU

| # | Kural |
|---|---|
| Z1 | Fazları **sırayla** uygula. Bir faz kabul kriterlerini geçmeden sonraki faza geçme. |
| Z2 | Her faz sonunda `LEARNING.md`'yi güncelle (Bölüm 9). Bu adım atlanamaz. |
| Z3 | Kod yazmadan önce **FAZ 0**'ı çalıştır ve `.env` değerlerini gerçek çıktılardan doldur. |
| Z4 | Model adı, port gibi değerleri **koda gömme**. Tamamı `.env` + `config.py` üzerinden gelir. |
| Z5 | Foundry Local'a giden tüm çağrılar **yalnızca** `backend/app/foundry.py` içinden yapılır. |
| Z6 | Her prompt metni **yalnızca** `backend/app/prompts.py` içinde tanımlanır. |
| Z7 | Her fazın sonunda commit at. Mesaj formatı: `faz-N: kısa açıklama`. `LEARNING.md` aynı commit'te olmalı. |
| Z8 | Bir dosya 150 satırı geçiyorsa dur ve böl. |
| Z9 | Hata durumunda kod değiştirmeden önce Bölüm 10'daki 3 logu ekranda göster. |

### 0.2 YASAK

| # | Yasak | Sebep |
|---|---|---|
| Y1 | **Foundry Local kurmak / güncellemek** | Kullanıcının makinesinde zaten kurulu. Çakışma yaratır. |
| Y2 | **`foundry model download/run phi-4-mini` çalıştırmak** | Model zaten indirilmiş ve yüklü. |
| Y3 | Docker, docker-compose, Kubernetes | Uygulama lokal çalışacak. |
| Y4 | Chroma'yı sunucu/HTTP modunda çalıştırmak | Yalnızca `PersistentClient` (gömülü mod) kullanılacak. |
| Y5 | PostgreSQL, Redis, pgvector, Qdrant, Weaviate | Kapsam dışı. |
| Y6 | Kullanıcı hesabı, auth, oturum yönetimi | Tek kullanıcı, tek makine. |
| Y7 | LangChain `Chain` / `Agent` / `RetrievalQA` sınıfları | Bkz. Bölüm 3.3. Yalnızca `langchain-text-splitters` paketi serbest. |
| Y8 | Faz 1-3 bitmeden streaming (SSE) eklemek | En sık "cevap gelmiyor" sebebi. Faz 4'te. |
| Y9 | Cloud API'ye (OpenAI, Azure, Anthropic) giden herhangi bir çağrı | Proje tamamen offline olmalı. |
| Y10 | Kabul kriterini "muhtemelen çalışıyor" diyerek geçmek | Kriter fiilen test edilip çıktı gösterilecek. |

### 0.3 Belirsizlik protokolü

Bir karar noktasında bu dosyada net talimat yoksa:
1. **Uydurma.** Kullanıcıya sor.
2. Sorunun yanına **iki somut seçenek** ve her birinin sonucunu yaz.
3. Cevap gelene kadar o kısmı `TODO(karar): ...` yorumuyla işaretle, ilerlemeye devam etme.

---

## 1. HEDEF

Tarayıcıdan kullanılan, internet bağlantısı olmadan çalışan bir soru-cevap uygulaması.

**Mod A — Genel bilgi:** "Türkiye'nin başkenti nedir?" → model kendi bilgisinden cevaplar.
**Mod B — Belge tabanlı:** PDF yüklenmiş ve soru o belgeyle ilgiliyse → yalnızca belgeden cevaplar, kaynak gösterir.

Mod seçimi otomatik yapılır (Bölüm 6.3).

---

## 2. MİMARİ

```
┌──────────────────────────────────────────────────────────┐
│ Tarayıcı — http://localhost:3000                         │
│ Next.js (App Router, TypeScript, Tailwind)               │
└───────────────────────┬──────────────────────────────────┘
                        │ fetch("/api/...")
                        │ next.config.ts → rewrites (CORS YOK)
┌───────────────────────▼──────────────────────────────────┐
│ FastAPI — http://localhost:8000                          │
│   /health  /upload  /documents  /search  /chat           │
│                                                          │
│   ingest.py  : PDF → metin → chunk                       │
│   foundry.py : chat() + embed()                          │
│   store.py   : ChromaDB (PersistentClient)               │
│   retrieve.py: arama + eşik kararı                       │
└──────────┬─────────────────────────┬─────────────────────┘
           │                         │
┌──────────▼──────────────┐  ┌───────▼──────────────────────┐
│ ChromaDB (gömülü)       │  │ Foundry Local                │
│ backend/data/chroma/    │  │ http://localhost:<PORT>/v1   │
│ (dosya sistemi, sunucu  │  │  • phi-4-mini                │
│  süreci yok)            │  │  • qwen3-embedding-0.6b      │
└─────────────────────────┘  └──────────────────────────────┘
```

**CORS notu:** Frontend'de mutlak URL kullanılmaz. `next.config.ts` içinde rewrite tanımlanır:

```ts
async rewrites() {
  return [{ source: "/api/:path*", destination: "http://localhost:8000/:path*" }];
}
```

Böylece tarayıcı her şeyi `localhost:3000` origin'inde görür, CORS katmanı hiç devreye girmez.

---

## 3. TECH STACK VE GEREKÇELER

### 3.1 Seçimler

| Katman | Seçim | Gerekçe |
|---|---|---|
| Backend | **Python 3.11+ / FastAPI / uvicorn** | AI ekosisteminin ana dili. Foundry Local, Chroma, PyMuPDF, LangChain — hepsinin birincil ve en iyi dokümante edilmiş SDK'sı Python. Async destekli, otomatik `/docs` (Swagger) üretir. |
| Paket yönetimi | **venv + pip** (`requirements.txt`) | Standart ve tahmin edilebilir. `uv` daha hızlı ama zorunlu değil. |
| PDF → metin | **PyMuPDF (`pymupdf`)** | Türkçe karakter ve sütunlu düzende en doğru metin çıkarımı. Sayfa numarasını verir. **Lisans: AGPL** — kapalı kaynak dağıtım gerekirse `pypdf` (BSD) kullanılır, kalite biraz düşer. |
| Chunking | **`langchain-text-splitters`** → `RecursiveCharacterTextSplitter` | Tek başına kurulan küçük paket. Paragraf → cümle → karakter sırasıyla bölme ve overlap mantığı iyi test edilmiş. Yeniden yazmanın getirisi yok. |
| LLM erişimi | **`openai` SDK**, `base_url` = Foundry Local | Foundry Local OpenAI uyumlu API sunar. Aynı kod buluta taşınabilir. |
| Embedding | **qwen3-embedding-0.6b** (Foundry Local) | Aynı servis, ek bağımlılık yok, offline. |
| Vektör DB | **ChromaDB — `PersistentClient`** | Bkz. 3.2. |
| Frontend | **Next.js 15 + TypeScript + Tailwind** | Kullanıcı tercihi. Rewrites ile proxy. |

### 3.2 Vektör DB: neden ChromaDB (karar revizyonu)

Bu kararın önceki taslakta farklı olmasının sebebi stack'in JavaScript olmasıydı. JS tarafında gömülü, olgun bir vektör DB yok; Chroma/Qdrant kullanmak ayrı bir sunucu süreci başlatmak demekti — o yüzden elle cosine yazmak daha az karmaşıklıktı.

**Python'da bu denklem tersine dönüyor.** ChromaDB'nin `PersistentClient` modu bir sunucu değil; SQLite üzerine oturan gömülü bir kütüphane. Docker yok, port yok, ayrı süreç yok — sadece bir klasör.

```python
import chromadb
client = chromadb.PersistentClient(path="./data/chroma")
col = client.get_or_create_collection("docs", metadata={"hnsw:space": "cosine"})
```

Elle JSON deposu + cosine yazmaya kıyasla: **daha az kod**, kalıcılık bedava, metadata filtreleme bedava, silme/güncelleme bedava. Yani burada Chroma over-engineering değil, aksine daha az iş.

Ek olarak: bu bir Microsoft staj projesi. Standart RAG mimarisini kullanmak sunumda savunması daha kolay bir tercihtir.

> ⚠️ **Kritik:** Koleksiyon `metadata={"hnsw:space": "cosine"}` ile oluşturulmalı.
> Varsayılan L2 mesafedir ve eşik değerlerin tamamen farklı çıkar.
> Chroma **mesafe** döndürür, benzerlik değil: `similarity = 1 - distance`.
> Bu dönüşümü unutmak, eşik mantığının sessizce ters çalışmasına yol açar.

> ⚠️ Embedding'leri Chroma'ya **biz üretip veriyoruz** (`embeddings=[...]`).
> Chroma'nın kendi `embedding_function`'ı kullanılmayacak — o varsayılan olarak
> internetten model indirmeye çalışır ve offline gereksinimini bozar.

### 3.3 LangChain: kısmi kullanım

| Kullanılacak | Kullanılmayacak |
|---|---|
| `langchain-text-splitters` (`RecursiveCharacterTextSplitter`) | `RetrievalQA`, `LLMChain`, `Agent`, LCEL zincirleri, `VectorStore` sarmalayıcıları |

**Gerekçe:** Splitter saf bir yardımcı fonksiyon — girdi metin, çıktı liste. Şeffaf, test edilmiş, kazandırıyor.

Zincir soyutlamaları ise modele giden **nihai prompt'u gözden saklıyor.** Bu projenin bilinen problemi "alakasız cevap geliyor" ve bunu çözmenin tek yolu prompt'u ham haliyle görmek. Retrieval → prompt → LLM adımları açıkta kalacak ki Bölüm 10'daki 3 log her zaman erişilebilir olsun.

---

## 4. DİZİN YAPISI

Agent bu yapıya **birebir** uyacak. Dosya eklemek gerekirse önce sor.

```
foundry-rag/
├── PLAN.md
├── LEARNING.md
├── README.md
├── .gitignore                  # backend/data/, .env, node_modules/, .venv/
│
├── backend/
│   ├── .env                    # FAZ 0 çıktılarıyla doldurulur
│   ├── .env.example
│   ├── requirements.txt
│   ├── data/
│   │   ├── chroma/             # ChromaDB kalıcı deposu (git'e girmez)
│   │   └── uploads/            # yüklenen PDF'ler (git'e girmez)
│   └── app/
│       ├── __init__.py
│       ├── main.py             # FastAPI app + route tanımları
│       ├── config.py           # .env okuma + tüm sabitler
│       ├── models.py           # Pydantic request/response şemaları
│       ├── foundry.py          # chat() + embed()  ← Foundry'e giden TEK yer
│       ├── ingest.py           # PDF → metin → chunk
│       ├── store.py            # Chroma sarmalayıcı
│       ├── retrieve.py         # arama + eşik kararı
│       └── prompts.py          # tüm prompt metinleri ← TEK yer
│
└── frontend/
    ├── next.config.ts          # /api/* → localhost:8000 rewrite
    └── src/
        ├── app/page.tsx
        ├── components/
        │   ├── Chat.tsx
        │   ├── Uploader.tsx
        │   ├── DocumentList.tsx
        │   └── SourcePanel.tsx
        └── lib/api.ts          # backend çağrıları ← TEK yer
```

---

## 5. FAZ 0 — DOĞRULAMA (kod yazma yok)

**Amaç:** Kod yazmadan önce Foundry Local'ın gerçek davranışını tespit etmek.
Bu fazın atlanması, önceki denemede yaşanan tanısız hata döngüsünün temel sebebidir.

Agent bu komutları çalıştırır (veya çalıştıramıyorsa kullanıcıdan çıktıları ister) ve
sonuçları `LEARNING.md` → Faz 0 bölümüne yazar.

### 5.1 Port

```bash
foundry service status
```
→ Endpoint'i not et. **Port sabit değil** (5272 / 5273 / ...).

### 5.2 Gerçek model ID'leri

```bash
curl http://localhost:<PORT>/v1/models
```

> ⚠️ `phi-4-mini` bir **alias**'tır. REST API bazı sürümlerde yalnızca tam ID kabul eder
> (`Phi-4-mini-instruct-generic-gpu` gibi). Yanlış model adı → boş `content` veya 404 →
> "model cevap vermiyor". **Bu, bilinen semptomun 1 numaralı şüphelisi.**
> `.env`'e bu çıktıdan **kopyala-yapıştır** yap.

### 5.3 Chat testi

```bash
curl http://localhost:<PORT>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"<TAM_ID>","messages":[{"role":"user","content":"What is the capital of Turkey?"}],"max_tokens":200,"temperature":0.2}'
```

`choices[0].message.content` dolu değilse **kod yazmaya başlama**, önce bunu çöz.

### 5.4 Türkçe kalite ölçümü ⚠️

Aynı soruyu Türkçe sor ve iki cevabı karşılaştır.

Phi-4-mini 3.8B parametreli, ağırlıklı İngilizce eğitilmiş ve INT4 quantize edilmiş bir
modeldir. Türkçe üretim kalitesi İngilizceye göre gözle görülür şekilde düşüktür.
**Şikayet edilen "alakasız cevapların" bir kısmı RAG hatası değil, modelin dil sınırı olabilir.**

Fark belirginse uygulanacak strateji: system prompt **İngilizce** yazılır, sonuna
`Always answer in Turkish.` eklenir. Küçük modellerde bu, tamamen Türkçe prompt'a göre
ölçülebilir şekilde daha iyi sonuç verir.

Sonucu `LEARNING.md`'deki karşılaştırma tablosuna yaz.

### 5.5 Embedding modeli

```bash
foundry model list | grep -i embed
curl http://localhost:<PORT>/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"<EMBED_ID>","input":"deneme metni"}'
```

| Durum | Yapılacak |
|---|---|
| `data[0].embedding` dizi dönüyor | REST kullan. Uzunluğu (`dim`) not et. |
| REST 404 / desteklenmiyor | `pip install foundry-local-sdk` → `model.get_embedding_client()` |
| Model catalog'da yok | **DUR, kullanıcıya sor.** Kendi başına model indirme (Y2). |

### 5.6 Kabul kriteri

- [ ] `backend/.env` gerçek değerlerle dolu:
  ```
  FOUNDRY_BASE_URL=http://localhost:5273/v1
  CHAT_MODEL=<5.2'den tam ID>
  EMBED_MODEL=<5.5'ten tam ID>
  EMBED_DIM=<5.5'ten uzunluk>
  ```
- [ ] curl ile chat cevabı alındı
- [ ] curl ile embedding vektörü alındı
- [ ] `LEARNING.md` Faz 0 bölümü dolu (TR/EN tablosu dahil)

---

## 6. UYGULAMA FAZLARI

### FAZ 1 — Sohbet (RAG yok)

**Hedef:** Tarayıcıdan genel bilgi sorusu sor, doğru cevap gel.

**Yapılacaklar**
1. `backend/` iskeleti: venv, `requirements.txt`, `config.py` (.env okur, sabitleri tutar).
2. `foundry.py` → tek fonksiyon:
   ```python
   def chat(messages: list[dict], temperature: float, max_tokens: int) -> str
   ```
   `openai` SDK, `base_url=settings.FOUNDRY_BASE_URL`, `api_key="not-needed"`.
3. `main.py` → `GET /health`, `POST /chat` (şimdilik yalnızca Mod A).
4. `frontend/` → `create-next-app`, `next.config.ts` rewrite, `Chat.tsx`, `lib/api.ts`.
5. UI'da bağlantı göstergesi (`/health` sonucuna göre yeşil/kırmızı).

**Kabul kriteri**
- [ ] `uvicorn app.main:app --reload` ve `npm run dev` birlikte çalışıyor
- [ ] `localhost:3000` açılıyor, bağlantı göstergesi yeşil
- [ ] 3 farklı genel kültür sorusu → 3 makul cevap
- [ ] `LEARNING.md` Faz 1 dolu → **commit**

---

### FAZ 2 — Belge alma ve arama (chat'e bağlanmadan)

**Hedef:** PDF yüklenip aranabilir hale gelmesi. Chat'e **henüz bağlanmıyor.**

Bu ayrım bilinçlidir: retrieval katmanı tek başına doğrulanır. Böylece Faz 3'te alakasız
cevap gelirse sorunun retrieval'da **olmadığı** kesin bilinir ve arama alanı yarıya iner.

**Yapılacaklar**
1. `ingest.py`:
   - `pdf_to_pages(path) -> list[tuple[int, str]]` (PyMuPDF, sayfa no + metin)
   - `chunk_pages(pages) -> list[Chunk]` (`RecursiveCharacterTextSplitter`)
   - Chunk metadata: `doc_id`, `filename`, `page`, `chunk_index`
   - **Boş metin kontrolü:** PDF taranmış görüntüyse metin boş gelir → kullanıcıya
     `"Bu PDF'ten metin çıkarılamadı (taranmış görüntü olabilir)"` hatası dön. Sessizce geçme.
2. `foundry.py` → `embed(texts: list[str]) -> list[list[float]]`. **Toplu gönder**, tek tek değil.
3. `store.py` → Chroma sarmalayıcı: `add_chunks`, `query`, `list_documents`, `delete_document`.
   Koleksiyon `{"hnsw:space": "cosine"}` ile oluşturulur.
4. `retrieve.py` → `search(query, top_k) -> list[Result]`, `score = 1 - distance`.
5. Endpoint'ler: `POST /upload`, `GET /documents`, `DELETE /documents/{doc_id}`, `POST /search`.
6. Frontend: `Uploader.tsx`, `DocumentList.tsx` ve geçici bir arama kutusu (skorları gösterir).

**Eşik kalibrasyonu (zorunlu)**
Eşiği tahmin etme. 10 soru sor — 5'i belgeyle ilgili, 5'i alakasız. Her birinin en yüksek
skorunu `LEARNING.md`'deki tabloya yaz. İki grubun arasındaki boşluğu bul, eşiği oraya koy.

**Kabul kriteri**
- [ ] PDF yükleniyor, kaç sayfa / kaç chunk çıktığı UI'da görünüyor
- [ ] `/search` ile sorulan 5 soruda doğru chunk ilk 3'te geliyor
- [ ] Eşanlamlıyla arama çalışıyor (örn. belgede "gider" → sorguda "maliyet")
- [ ] Skorlar 0-1 aralığında ve mantıklı (değilse `hnsw:space` ayarını kontrol et)
- [ ] Eşik kalibrasyon tablosu `LEARNING.md`'de dolu → **commit**

---

### FAZ 3 — RAG entegrasyonu

**Hedef:** İki modu birleştirmek.

**Mod yönlendirme mantığı**

```
Soru geldi
   │
   ├─ koleksiyon boş? ──────── evet ──→ MOD A (genel sohbet)
   │
   └─ hayır → search(query, top_k=3)
              │
              ├─ en yüksek skor < THRESHOLD ──→ MOD A
              │                                 + not: "Belgede bulamadım,
              │                                   genel bilgimle cevaplıyorum."
              │
              └─ skor >= THRESHOLD ──────────→ MOD B (belgeden cevapla)
```

**Yapılacaklar**
1. `prompts.py` → Bölüm 7'deki iki şablon.
2. `POST /chat` → yönlendirme + prompt kurulumu + `chat()` çağrısı.
3. Yanıtta `mode`, `sources`, `timings` alanları dönsün (Bölüm 8).
4. `SourcePanel.tsx` → cevabın altında açılır-kapanır kaynak listesi (dosya, sayfa, skor).
5. Mod rozeti: cevabın üstünde "Belgeden" / "Genel bilgi" etiketi.

**Kabul kriteri**
- [ ] Belgeyle ilgili 5 soru → doğru cevap + doğru kaynak gösterimi
- [ ] Belgede olmayan bir bilgi sorulduğunda uydurmuyor, tanımlı cümleyi dönüyor
- [ ] Belgeyle alakasız soru → Mod A'ya düşüyor, mod rozeti doğru
- [ ] Wi-Fi kapalıyken tüm akış çalışıyor
- [ ] `LEARNING.md` Faz 3 dolu → **commit**

---

### FAZ 4 — Cila (yalnızca 1-3 sağlamsa)

Öncelik sırasıyla:
1. Streaming cevap (SSE) — non-streaming kusursuz çalıştıktan **sonra**
2. Cevap süresi + token sayısı göstergesi
3. Çoklu PDF, belge silme
4. **Deney:** BM25 anahtar kelime araması ekleyip embedding ile karşılaştır.
   Sonucu `LEARNING.md`'ye somut skorlarla yaz — sunumun en güçlü bulgusu bu olur.
5. Karanlık mod

---

## 7. PROMPT ŞABLONLARI

Tamamı `backend/app/prompts.py` içinde sabit olarak durur.

### Mod A — Genel sohbet
```
You are a helpful assistant running fully offline on the user's device.
Answer concisely and accurately. If you are not sure about something, say so.
Always answer in Turkish.
```

### Mod B — Belge tabanlı
```
You are a document question-answering assistant.
Answer ONLY using the CONTEXT below. Do not use outside knowledge.
If the context does not contain the answer, reply exactly with:
"Bu bilgi yüklenen belgede yok."
Cite sources in brackets, e.g. [rapor.pdf s.3].
Always answer in Turkish.

CONTEXT:
---
[{filename} s.{page}] {chunk_text}
---
[{filename} s.{page}] {chunk_text}
---

QUESTION: {user_question}
```

**Kurallar**
- Context'e en fazla **3** chunk konur. Fazlası küçük modelde dikkati dağıtır ve kaliteyi *düşürür*.
- "Sadece context'ten cevapla" talimatı zorunludur; yoksa model uydurur.
- Bilinmeyen durumda dönülecek cümle **birebir** yazılır, yoksa her seferinde farklı bir şey söyler.

---

## 8. API SÖZLEŞMELERİ

Frontend ve backend bu şemalara uyar. Değişiklik gerekirse önce bu bölüm güncellenir.

```
GET /health
→ 200 { ok: bool, chat_model: str, embed_model: str,
        endpoint: str, document_count: int, chunk_count: int }

POST /upload            (multipart/form-data, alan adı: "file")
→ 200 { doc_id: str, filename: str, pages: int, chunks: int }
→ 400 { detail: "Bu PDF'ten metin çıkarılamadı (taranmış görüntü olabilir)" }

GET /documents
→ 200 { documents: [{ doc_id, filename, pages, chunks, uploaded_at }] }

DELETE /documents/{doc_id}
→ 200 { ok: true, deleted_chunks: int }

POST /search            { query: str, top_k?: int = 3 }        # hata ayıklama amaçlı
→ 200 { results: [{ text, filename, page, score }] }

POST /chat              { message: str, history?: [{role, content}] }
→ 200 { mode: "general" | "document",
        answer: str,
        sources: [{ filename, page, score, snippet }],
        timings: { retrieval_ms: int, generation_ms: int } }
```

---

## 9. LEARNING.md PROTOKOLÜ

`LEARNING.md` bu projenin **birincil çıktısıdır**; kod ikincildir.

| Kural | İçerik |
|---|---|
| L1 | Faz günlüğü doldurulmadan sonraki faza geçilmez. Boş alan varsa "denemedim" yazılır. |
| L2 | Proje sırasında ilk kez karşılaşılan her terim referans bölümüne (1-7) eklenir. |
| L3 | 20 dakikadan uzun süren her hata "Hata defteri"ne yazılır: belirti / sanılan sebep / gerçek sebep / çözüm / süre. |
| L4 | Ölçüm olmadan gözlem yazılmaz. ❌ "Daha iyi oldu" → ✅ "900 karakterde top-1 skor 0.71, 1500'de 0.58" |
| L5 | Seçilen her sayı (`TOP_K`, `CHUNK_SIZE`, eşik, `temperature`) "Karar defteri"ne gerekçesiyle girer. |
| L6 | Her faz günlüğü 2-3 cümlelik düz özetle biter. Bu özetler üst üste geldiğinde sunumun iskeleti çıkar. |

---

## 10. PARAMETRELER

Tamamı `backend/app/config.py` içinde tek yerde durur.

| Parametre | Başlangıç | Not |
|---|---|---|
| `CHUNK_SIZE` | 900 karakter | Küçükse bağlam kopar, büyükse alakasız metin girer |
| `CHUNK_OVERLAP` | 150 karakter | Sınırda kesilen cümleler için |
| `TOP_K` | 3 | Küçük modelde daha fazlası kaliteyi düşürür |
| `SIMILARITY_THRESHOLD` | Faz 2'de **ölç** | Tahmin edilmez. `similarity = 1 - chroma_distance` |
| `TEMPERATURE_GENERAL` | 0.7 | Doğal sohbet |
| `TEMPERATURE_RAG` | 0.2 | Belgeye sadakat |
| `MAX_TOKENS` | 512 | **Asla boş bırakılmaz** — bazı sürümlerde varsayılan çok düşük, cevap boş gelir |

---

## 11. HATA AYIKLAMA

### 11.1 Altın kural

Bir şey bozulduğunda **kodu değiştirmeden önce logla.** Şu üçü ekranda görünmeden düzeltme denenmez:

1. Modele giden **nihai prompt'un tam metni**
2. Seçilen chunk'lar ve **skorları**
3. Foundry'den gelen **ham JSON yanıtı**

Bu üçü elde olmadan hangi katmanın bozuk olduğu bilinemez ve yapılan her düzeltme tahmindir.
`config.py` içinde `DEBUG_LOG: bool` bayrağı bulunur; açıkken bu üçü konsola basılır.

### 11.2 Semptom tablosu

| Belirti | En olası sebep | Kontrol |
|---|---|---|
| Cevap boş geliyor | Model adı alias, tam ID değil | `/v1/models` çıktısıyla `.env`'i karşılaştır |
| Cevap boş geliyor | `max_tokens` verilmemiş | İsteğe `max_tokens=512` ekle |
| Bağlantı hatası | Port değişmiş | `foundry service status` |
| Bağlantı hatası | Model belleğe yüklü değil | Kullanıcıdan `foundry model run` istemesini iste (Y2) |
| Cevap kesik | Context çok uzun | `TOP_K`'yı 2'ye düşür |
| Türkçe bozuk / konu dışı | Modelin dil sınırı | İngilizce system prompt + `Always answer in Turkish.` (5.4) |
| Skorlar 1'den büyük / negatif | `hnsw:space` cosine değil | Koleksiyonu sil, doğru metadata ile yeniden oluştur |
| Eşik hep yanlış tarafta | `distance` / `similarity` karıştırılmış | `score = 1 - distance` dönüşümünü doğrula |
| Alakasız chunk'lar | PDF metni bozuk çıkmış | Çıkarılan ham metni yazdır ve **gözle oku** |
| Belgeye rağmen uyduruyor | Prompt talimatı zayıf | Bölüm 7 şablonunu birebir uygula, `temperature=0.2` |
| İlk istek çok yavaş | Model belleğe yükleniyor | Normal. Açılışta `/health` ile ısıtma isteği at |
| Chroma indirme denemesi | Kendi `embedding_function`'ı devrede | `embeddings=[...]` parametresini elle ver (3.2) |

---

## 12. BİTİŞ KONTROL LİSTESİ

**Fonksiyonel**
- [ ] Backend ve frontend tek komutla ayağa kalkıyor, README'de yazılı
- [ ] Bağlantı göstergesi doğru çalışıyor
- [ ] 3 genel kültür sorusu → makul cevaplar (Mod A)
- [ ] PDF yükleniyor, sayfa/chunk sayısı görünüyor
- [ ] Belge soruları → doğru cevap + doğru kaynak (Mod B)
- [ ] Belgede olmayan bilgi soruldu → uydurmuyor
- [ ] Alakasız soru → Mod A'ya düşüyor
- [ ] **Wi-Fi kapalı, tüm akış çalışıyor** ← demoda mutlaka göster, projenin ana fikri bu

**Dokümantasyon**
- [ ] Faz 0-3 günlükleri dolu, boş alan yok
- [ ] TR/EN kalite karşılaştırması yazılı
- [ ] Eşik kalibrasyon tablosu gerçek skorlarla dolu
- [ ] Karar defteri: her parametrenin gerekçesi var
- [ ] Hata defteri: 20 dk+ süren her sorun kayıtlı
- [ ] Her fazın 2-3 cümlelik özeti yazılı
- [ ] `README.md`: kurulum, çalıştırma, mimari şeması

---



