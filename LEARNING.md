# LEARNING.md — Proje Günlüğü

Bu dosya PLAN.md Bölüm 9 protokolüne göre tutulur. Kod ikincildir, bu günlük birincil çıktıdır.

---

## 1. Referans Terimleri

| Terim | Açıklama |
|---|---|
| Foundry Local | Microsoft'un yerel (offline) model çalıştırma platformu. CLI (`foundry`) + arka planda çalışan bir "model management service" (REST, OpenAI uyumlu) içerir. |
| `foundry service status` | Servisin çalışıp çalışmadığını ve portunu gösterir. Port sabit değildir. |
| Model alias | Kısa model adı (örn. `phi-4-mini`). Gerçek REST çağrılarında **tam model ID** gerekir (örn. `Phi-4-mini-instruct-generic-gpu:5`). |
| `foundry-local-sdk` (PyPI) | Python paketi. **İki farklı mimaride** sürümleri var (bkz. Hata Defteri #1): klasik REST-proxy sürüm (`foundry_local` import adı, ör. 0.3.1) ve yeni "Core Interop" native sürüm (`foundry_local_sdk` import adı, 1.x). Bu projede **1.2.4** kullanılıyor. |
| Core Interop | `foundry-local-sdk` 1.x'in native bir runtime süreciyle konuşan mimarisi. `FoundryLocalManager(config)` → kendi kataloğu, kendi model indirme/yükleme mekanizması. CLI'nin bağlandığı `localhost:<port>` REST servisinden **bağımsızdır**. |
| `Configuration(app_name=...)` | SDK'nın uygulama kimliği. Model cache'i `~/.{app_name}/cache/models` altında tutulur. Her `app_name` kendi izole cache'ine sahiptir ama katalog sorgusu (embedding modelleri dahil) her `app_name` için aynıdır. |
| Chroma `hnsw:space` | Koleksiyon mesafe metriği. `cosine` verilmezse varsayılan L2 kullanılır ve skorlar 0-1 aralığında olmaz. |
| `similarity = 1 - distance` | Chroma **mesafe** döndürür, benzerlik değil. Bu dönüşüm zorunlu. |

---

## 2. Faz Günlükleri

### FAZ 0 — Doğrulama

**Ortam**
- `foundry` CLI: `/opt/homebrew/bin/foundry`, sürüm `0.8.119`
- Servis: `foundry service status` → `http://127.0.0.1:54791` (port sabit değil, her makinede farklı olabilir — kod bunu asla sabit yazmamalı, `.env`'den okumalı)
- Python: sistem `python3` **3.9.6** — proje için yetersiz (PLAN 3.11+ istiyor, `foundry-local-sdk` 1.x `dict | None` sözdizimi kullanıyor, 3.10+ gerektiriyor). Homebrew üzerinden **Python 3.12.13** bulundu ve kullanıldı (`/opt/homebrew/bin/python3.12`).

**5.2 — Gerçek model ID'leri**
```
curl http://127.0.0.1:54791/v1/models
→ Phi-4-mini-instruct-generic-gpu:5   (tek yüklü/loaded model)
```
`foundry model list` tam katalogda 40 chat/vision/ses alias'ı gösterdi (embedding YOK — bkz. Hata Defteri #1). `phi-4-mini` alias'ı `Phi-4-mini-instruct-generic-gpu:5` tam ID'sine karşılık geliyor.

**5.3 — Chat testi**
```
curl .../v1/chat/completions -d '{"model":"Phi-4-mini-instruct-generic-gpu:5","messages":[{"role":"user","content":"What is the capital of Turkey?"}],"max_tokens":200,"temperature":0.2}'
→ "The capital of Turkey is Ankara. ..." (tam, düzgün, finish_reason: stop)
```
✅ Model cevap veriyor, `content` dolu.

**5.4 — Türkçe kalite ölçümü**

| Dil | Soru | Sonuç |
|---|---|---|
| EN | "What is the capital of Turkey?" | Tam, doğru, tutarlı cevap. |
| TR | "Türkiye'nin başkenti neresidir?" | "Türkiye'nin başkenti Ankara'dır." ile **doğru başlıyor**, ardından "depolama zamanı belgesinin depolama zamanı..." şeklinde anlamsız bir **tekrar döngüsüne (repetition loop)** giriyor, 200 token'ı dolduruyor. |

**Sonuç:** PLAN'ın öngördüğü "Türkçe kalite İngilizceye göre belirgin düşük" senaryosu doğrulandı — üstelik burada dil kalitesi değil, doğrudan bir **tekrar/dejenerasyon bug'ı** gözlendi. Uygulanacak strateji (PLAN 5.4 ile uyumlu): system prompt İngilizce yazılacak + `Always answer in Turkish.` eklenecek, `temperature` RAG modunda 0.2 düşük tutulacak, `max_tokens` gerektiğinde düşürülecek. Faz 1/3'te bu davranış tekrar gözlemlenecek; sürerse `max_tokens`'ı düşürüp `temperature`'ı hafif artırmak (0.3-0.4) denenecek.

**5.5 — Embedding modeli**

Uzun bir araştırma gerektirdi, detay için **Hata Defteri #1**. Özet:
- `foundry model list` / `foundry model info` / `foundry model download` → `qwen3-embedding-0.6b` **bulunamadı** (CLI'nin bağlandığı `localhost:54791` REST servisinin kataloğunda embedding görevli hiç model yok, sadece chat/vision/ses).
- `foundry-local-sdk` 1.2.4'ün **native Core Interop** kataloğu (CLI'den tamamen bağımsız bir mekanizma) sorgulandığında `qwen3-embedding-0.6b` ve `qwen3-embedding-8b` **bulundu**.
- Akış: `Configuration(app_name="rag-project")` → `FoundryLocalManager(config)` → `mgr.catalog.get_model("qwen3-embedding-0.6b")` → CPU varyantı seç (`select_variant`) → `.download()` → `.load()` → `.get_embedding_client()` → `generate_embedding(text)` / `generate_embeddings([texts])`.
- **Sonuç:** `dim=1024`, batch embedding çalışıyor (`generate_embeddings` ile 3 metin → 3×1024 vektör, tek çağrıda).
- CPU varyantı seçildi çünkü `WebGpuExecutionProvider` register edilmemişti (`discover_eps()` → `is_registered=False`). GPU registrasyonu Y1 sınırındaki "Foundry Local kurulumuna müdahale" ile sınıra yakın görüldüğü için CPU varyantla devam edildi — 0.6B model için CPU'da kısa metinlerde performans kabul edilebilir düzeyde.

**5.6 — Kabul kriteri**
- [x] `backend/.env` gerçek değerlerle dolu
- [x] curl ile chat cevabı alındı
- [x] SDK ile embedding vektörü alındı (curl değil — REST embedding endpoint'i çalışmıyor, bkz. Hata Defteri #1)
- [x] Bu bölüm dolu (TR/EN tablosu dahil)

**Özet (2-3 cümle):** Chat tarafı REST üzerinden sorunsuz çalışıyor (`Phi-4-mini-instruct-generic-gpu:5`), Türkçede tekrar/dejenerasyon riski var ve İngilizce sistem prompt + Türkçe yanıt talimatı stratejisiyle ele alınacak. Embedding tarafı beklenenin aksine REST API üzerinden değil, `foundry-local-sdk`'nin native "Core Interop" katmanı üzerinden çalışıyor (`qwen3-embedding-0.6b`, CPU varyant, dim=1024) — bu nedenle `foundry.py` içindeki `embed()` fonksiyonu `chat()`'ten farklı bir istemci kullanacak.

---

### FAZ 1 — Sohbet (RAG yok)

**Kurulum**
- Backend: `backend/app/{config,foundry,models,prompts,main}.py`. `config.py` `pydantic-settings` ile `.env` okuyor. `foundry.py` `chat()` fonksiyonu `openai` SDK'sı ile `FOUNDRY_BASE_URL`'e REST çağrısı yapıyor, `DEBUG_LOG=true` iken nihai mesajları ve ham JSON yanıtı konsola basıyor (Bölüm 11.1 altın kuralı).
- Frontend: `create-next-app` (Next.js **16.3.1**, Turbopack varsayılan — `--no-turbopack` bayrağı bu sürümde etkisiz kaldı, engel değil). `next.config.ts`'te `/api/:path*` → `http://localhost:8000/:path*` rewrite. `Chat.tsx` bağlantı göstergesini (`/health`) ve mesajlaşmayı içeriyor.
- `uvicorn app.main:app --port 8000` ve `npm run dev` (port 3000) paralel çalıştırıldı, ikisi de sorunsuz ayağa kalktı.

**Test sonuçları (7 soru: 3 curl + 4 tarayıcı)**

| Soru | Sonuç |
|---|---|
| "Fransa'nın başkenti neresidir?" (curl) | ✅ Doğru, temiz: "Paris'dir." |
| "Suyun kimyasal formülü nedir?" (curl) | ✅ Doğru, temiz: "H2O'dur." |
| "İkinci Dünya Savaşı hangi yıl bitti?" (curl) | ⚠️ Format düzgün ama **faktüel hata** ("Ocak 1945" — doğrusu Eylül 1945). Model bilgi sınırı, RAG hatası değil. |
| "Everest dağı nerede bulunur?" (tarayıcı) | ⚠️ "Bağlantı hatası: backend'e ulaşılamadı" UI'da gösterildi. Backend logunda bu istek **hiç görünmedi** — otomasyon aracının click/type/Enter adımlarını sayfa tam hydrate olmadan art arda göndermesinden kaynaklanan tekil bir olay (aynı akış hemen sonra sorunsuz tekrarlandı). Kod hatası değil, ama gerçek kullanıcıda da olası bir "ilk yükleme soğuk başlangıcı" riski olarak not edildi. |
| "merhaba" (tarayıcı) | ⚠️ **Dil tutarsızlığı:** "Hi! Size nasıl yardımcı olabilir?" — İngilizce + Türkçe karışık. `SYSTEM_PROMPT_GENERAL`'daki "Always answer in Turkish." talimatına rağmen küçük model ara sıra kaçırıyor. |
| "Ay'a ilk ayak basan astronot kimdir?" (tarayıcı) | ⚠️ Tam Türkçe ama **faktüel hata + tuhaf cümle**: tarih yanlış, "Ay Harikaları Evakülasyonu (Apollo 11)" gibi anlamsız bir terim uydurdu. |
| "Japonya'nın başkenti neresidir?" (tarayıcı, sayfa yenilendikten sonra) | ✅ Doğru, temiz: "Tokyo'dur." |

**Değerlendirme:** Format/akış açısından 7 sorunun 7'si de "makul" (kısa, ilgili, sohbet formatında) — kabul kriteri ("3 farklı genel kültür sorusu → 3 makul cevap") bu ölçüde karşılanıyor. Ancak dürüstçe not edilmeli: küçük model (3.8B, INT4) zaman zaman (a) faktüel hata yapıyor ve (b) Türkçe/İngilizce karışık cevap veriyor. Bu PLAN 5.4/11.2'nin zaten öngördüğü, İngilizce sistem prompt + "Always answer in Turkish." stratejisiyle azaltılan ama tam çözülmeyen bir risk. Faz 3'te RAG modunda (`temperature=0.2`, dar bağlam) bu davranışın iyileşip iyileşmediği tekrar gözlenecek.

**Kabul kriteri**
- [x] `uvicorn` ve `npm run dev` birlikte çalışıyor
- [x] `localhost:3000` açılıyor, bağlantı göstergesi yeşil
- [x] 3+ genel kültür sorusu → makul cevaplar (format/akış tutarlı; içerik kalitesi yukarıdaki gibi değişken)
- [x] Bu bölüm dolu

**Özet:** Uçtan uca sohbet akışı (tarayıcı → Next.js rewrite → FastAPI → Foundry Local REST) çalışıyor ve bağlantı göstergesi doğru davranıyor. Asıl risk RAG'de değil, küçük modelin kendi bilgi doğruluğunda ve dil tutarlılığında — bu FAZ 3'te mod B (belgeden cevap, düşük sıcaklık, dar bağlam) ile kısmen azalması beklenen, izlenmesi gereken bir konu.

---

### FAZ 2 — Belge alma ve arama

**Kurulum**
- `ingest.py`: `pdf_to_pages()` (PyMuPDF), `chunk_pages()` (`RecursiveCharacterTextSplitter`, `CHUNK_SIZE=900`/`CHUNK_OVERLAP=150`). Boş sayfa metinleri chunk'lanmadan atlanıyor; tüm sayfalar boşsa `main.py` 400 döndürüyor.
- `foundry.py`'ye `embed()` eklendi: FAZ 0'da bulunan native SDK akışı (`Configuration → FoundryLocalManager → catalog.get_model → select_variant(cpu) → download() → load() → get_embedding_client()`), lazy + tek seferlik init (modül seviyesinde `_embed_client` cache).
- `store.py`: `chromadb.PersistentClient`, koleksiyon `{"hnsw:space": "cosine"}` ile oluşturuldu. `add_chunks`, `query`, `list_documents` (doc_id'ye göre gruplanmış metadata), `delete_document`, `chunk_count`.
- `retrieve.py`: `search()` → `foundry.embed()` + `store.query()` + `score = 1 - distance`.
- Endpoint'ler: `POST /upload`, `GET /documents`, `DELETE /documents/{doc_id}`, `POST /search`. `/health` artık gerçek `document_count`/`chunk_count` dönüyor.
- Frontend: `Uploader.tsx` (dosya seçimi + sonuç/hata mesajı), `DocumentList.tsx` (liste + sil), `page.tsx`'te sol panelde bu ikisi + geçici debug arama kutusu (skorları gösteriyor, Faz 3'te chat'e taşınacak/kaldırılacak).

**Test:** 3 sayfalık sentetik bir PDF (`test_handbook.pdf` — izin, uzaktan çalışma, masraf iadesi konuları) oluşturulup uçtan uca test edildi (curl + Next.js proxy üzerinden, tarayıcı eklentisi bu turda bağlanamadığı için görsel UI doğrulaması yapılamadı — bileşenler `Chat.tsx` ile aynı desenle yazıldı, ayrı bir risk görülmüyor ama not düşülüyor).
- `/upload` → 3 sayfa, 3 chunk, `document_count`/`chunk_count` `/health`'te doğru güncellendi.
- Backend yeniden başlatıldıktan sonra veriler kalıcıydı (Chroma `PersistentClient` dosya sistemine yazıyor, doğrulandı).
- `DELETE /documents/{doc_id}` → 3 chunk silindi, liste boşaldı; tekrar yükleme sorunsuz.
- Boş metinli PDF (taranmış görüntü simülasyonu) → `400` + `"Bu PDF'ten metin çıkarılamadı (taranmış görüntü olabilir)."` — PLAN'daki mesajla birebir.

**Bulgu: embedding sorgu/pasaj asimetrisi.** İlk denemede "evden çalışma kuralları nelerdir" sorgusu, doğru sayfa (uzaktan çalışma politikası, skor 0.429) yerine yanlış sayfayı (izin politikası, skor 0.438) ilk sıraya koydu — skorlar çok yakındı. Qwen3-Embedding modelleri instruction-aware olduğu için sorguya bir talimat öneki eklenmesi önerilir; bunu `prompts.py`'ye `embed_query_instruction()` olarak eklendi ve yalnızca **sorgu** embedding'inde kullanıldı (pasajlar ham kalıyor — Qwen3-Embedding'in önerilen kullanım şekli budur). Doğrulama: aynı sorgu için cosine skor farkı 0.016'dan 0.05'e çıktı ve doğru sayfa ilk sıraya geçti.

**Eşik kalibrasyonu (10 soru, `test_handbook.pdf` üzerinde)**

| Soru | İlgili mi? | En yüksek skor |
|---|---|---|
| Yıllık izin kaç gün? | ✅ | 0.6504 |
| Evden çalışma haftada kaç gün yapılabilir? | ✅ | 0.6941 |
| Masraf iadesi ne kadar sürede yapılır? | ✅ | 0.7531 |
| İzin talebini ne zaman bildirmem gerekir? | ✅ | 0.5971 |
| Kullanılmayan izinler bir sonraki yıla devredilir mi? | ✅ | 0.6229 |
| Türkiye'nin başkenti neresidir? | ❌ | 0.2872 |
| Suyun kaynama noktası kaç derecedir? | ❌ | 0.3082 |
| Python programlama dili ne zaman çıktı? | ❌ | 0.3540 |
| Everest dağının yüksekliği nedir? | ❌ | 0.3454 |
| Güneş sistemi kaç gezegenden oluşur? | ❌ | 0.2918 |

İlgili grup aralığı: **0.597 – 0.753**. Alakasız grup aralığı: **0.287 – 0.354**. Boşluk ~0.24. Eşik, alakasız tarafa biraz yakın tutularak **0.45** seçildi (gerekçe: bir belge sorusunu yanlışlıkla Mod A'ya düşürmek — kullanıcı belgesi olan bir soru sorup genel bilgiyle karşılık bulması — alakasız bir soruyu yanlışlıkla Mod B'ye düşürüp "bulamadım" demekten daha kötü bir deneyim; bu yüzden eşik ilgili-minimumdan çok, alakasız-maksimumdan biraz uzakta tutuldu).

**Kabul kriteri**
- [x] PDF yükleniyor, sayfa/chunk sayısı backend'de doğru (`/upload`, `/health`); UI'da `Uploader.tsx` sonuç mesajıyla gösteriyor (görsel doğrulama bu turda yapılamadı, bkz. yukarı)
- [x] `/search` ile 5 ilgili soruda doğru chunk üstte (3 chunk'lık küçük korpus, ilk 3 içinde olmak trivial ama sıralama da doğru)
- [x] Eşanlamlı arama çalışıyor ("evden çalışma" → "Uzaktan Çalışma Politikası", instruction prefix sonrası)
- [x] Skorlar 0-1 aralığında ve mantıklı (0.287-0.753), `hnsw:space=cosine` doğrulandı
- [x] Eşik kalibrasyon tablosu gerçek skorlarla dolu

**Özet:** Belge yükleme → chunk'lama → embedding → Chroma → arama zinciri uçtan uca çalışıyor ve kalıcı (yeniden başlatmaya dayanıklı). En önemli bulgu embedding'in instruction-aware olması — bu gözden kaçsaydı arama kalitesi sessizce kötü kalırdı. Eşik net bir ayrımla (0.45) kalibre edildi.

---

### FAZ 3 — RAG Entegrasyonu

**Kurulum / Değişiklikler**
- `prompts.py`: `SYSTEM_PROMPT_RAG`, `RAG_NOT_FOUND_SENTENCE` ("Bu bilgi yüklenen belgede yok.") ve `build_rag_user_message()` (bağlam + soru birleştirme, `[filename s.X]` blok formatı) eklendi.
- `main.py` `/chat`: mod yönlendirme mantığı eklendi — `store.chunk_count() == 0` ise doğrudan Mod A; değilse `retrieve.search(message, TOP_K)` çalıştırılıp en yüksek skor `SIMILARITY_THRESHOLD` (0.45) üzerindeyse Mod B (RAG prompt + `TEMPERATURE_RAG=0.2`, `sources` dolduruluyor), altındaysa Mod A'ya düşülüp cevaba "Not: Belgede ilgili bilgi bulamadım, genel bilgimle cevaplıyorum." öneki ekleniyor.
- `ChatResponse` artık gerçek `sources` (filename/page/score/200-karakter snippet) ve `timings.retrieval_ms`/`generation_ms` dolduruyor (FAZ 1'de ikisi de sabitti).
- Frontend: `SourcePanel.tsx` (açılır/kapanır kaynak listesi) eklendi; `Chat.tsx`'e mod rozeti ("Belgeden" yeşil / "Genel bilgi" gri) ve mesaj başına `SourcePanel` entegre edildi. `ChatMessage` tipi görüntüleme amaçlı `mode`/`sources` alanlarıyla genişletildi (`api.ts`'deki `ChatMessage` değişmedi, sadece `Chat.tsx` içinde yerel `DisplayMessage` tipi tanımlandı).

**Test sonuçları** (backend hem doğrudan `:8000` hem Next.js proxy `:3000/api/*` üzerinden, mevcut `test_handbook.pdf` ile)
- Belgedeki bilgiyle doğrudan örtüşen 3 soru ("Yıllık izin hakkım kaç gün?", "Masraf iadesi kaç gün içinde ödenir?", "Uzaktan çalışma haftada kaç gün?") → `mode=document`, doğru cevap + doğru `[filename s.X]` atıfı, en yüksek skor 0.60–0.76.
- Konu dışı soru ("Şirketin ofis adresi nedir?") → arama skoru eşiğin altında kaldığı için `mode=general` + açıklayıcı not eklendi. Bu denemede model FAZ 0/1'de gözlenen tekrar/dejenerasyon bug'ını yine sergiledi (aynı cümleyi onlarca kez tekrarlayıp `MAX_TOKENS`'a çarptı, ~47 sn sürdü); bu mod yönlendirmesiyle ilgili değil, bilinen küçük-model riski (bkz. Karar Defteri "Türkçe strateji" satırı).
- Eşiğin **üzerinde** skorlanan (0.60) ama belgede doğrudan cevabı olmayan bir soru ("Yıllık izin ücreti nasıl hesaplanır, saatlik ücrete göre mi?") → `mode=document` kaldı (doğru davranış: eşik üstü her zaman Mod B dener), model halüsinasyon yapmadı ama `RAG_NOT_FOUND_SENTENCE` metnini harfiyen üretmedi — anlamca eşdeğer ama farklı bir cümle ("Bu bilgi yüklenen belgeye sahip değilim.") döndürdü. Davranış yönü doğru (uydurmuyor), talimatın birebir string'i garanti değil — küçük modelin bilinen bir kırılganlığı.
- `npx tsc --noEmit` hatasız.
- Görsel UI doğrulama: İlk denemede Chrome browser extension bağlanamadı, kullanıcının uzantıyı kontrol etmesinin ardından ikinci denemede bağlantı kuruldu. `localhost:3000`'de gerçek tarayıcıda test edildi: "Yıllık izin hakkım kaç gün?" → yeşil "Belgeden" rozeti, doğru cevap + `[test_handbook.pdf s.1]` atıfı, "Kaynaklar (3)" linkine tıklanınca 3 kaynak (dosya/sayfa/skor/snippet) doğru açıldı. "Türkiye'nin başkenti neresidir?" → gri "Genel bilgi" rozeti, "Not: Belgede ilgili bilgi bulamadım, genel bilgimle cevaplıyorum." öneki + doğru cevap ("Ankara"). Mod rozeti, kaynak paneli ve eşik-altı düşüş davranışı gerçek tarayıcıda görsel olarak doğrulandı.

**Kabul kriteri**
- [x] Belge yokken/alakasız soruda Mod A (genel bilgi)
- [x] Belge varken ve ilgili soruda Mod B (belgeden), doğru `[filename s.X]` atıfı
- [x] Eşik altı skorda otomatik Mod A'ya düşme + kullanıcıya açıklayıcı not
- [x] `sources` ve `timings.retrieval_ms` gerçek değerlerle dolu
- [~] Belgede olmayan bilgi için tam olarak sabit cümle — model davranışça doğru (uydurmuyor) ama string'i her zaman harfiyen üretmiyor; PLAN'ın asıl amacı (halüsinasyon önleme) sağlandığı için kabul edilebilir bulundu
- [x] Görsel UI doğrulama — ikinci denemede tarayıcı bağlandı, mod rozeti + kaynak paneli + eşik-altı düşüş gerçek tarayıcıda doğrulandı
- [ ] Wi-Fi kapalıyken uçtan uca test — henüz yapılmadı, FAZ 4 öncesi/sonrası yapılabilir

**Özet:** Mod yönlendirme mantığı (boş koleksiyon → Mod A, eşik altı → Mod A + not, eşik üstü → Mod B) `main.py`'de tek yerde ve PLAN'daki akışla birebir uyumlu şekilde çalışıyor. RAG promptu doğru atıfları üretiyor; halüsinasyon riski pratikte gözlenmedi (eşik üstünde bile bilmediğini söyledi) ama küçük modelin kesin string talimatlarına harfiyen uymaması ve tekrar/dejenerasyon riski FAZ 0'dan beri bilinen sınırlamalar olarak devam ediyor. Görsel doğrulama tamamlandı: mod rozeti, kaynak paneli ve eşik-altı not gerçek tarayıcıda gözle teyit edildi (ilk bağlantı denemesi başarısızdı, kullanıcı uzantıyı kontrol ettikten sonra ikinci denemede bağlandı).

---

### FAZ 4 — Cila

**Kurulum / Değişiklikler**
- **Süre/token gösterimi:** `Chat.tsx`'te her assistant mesajının altına `Getirme: Xms · Üretim: Yms` satırı eklendi (`api.ts`'den `Timings` tipi export edildi).
- **Dark mode:** `globals.css`'te zaten `prefers-color-scheme: dark` ile otomatik arka plan/metin renkleri vardı (create-next-app varsayılanı); bileşenlerdeki (`Chat.tsx`, `SourcePanel.tsx`, `Uploader.tsx`, `DocumentList.tsx`, `page.tsx`) sabit `bg-white`/`bg-gray-100`/`border-black/10` gibi sınıflara `dark:` varyantları eklendi, böylece kart/kenarlık/rozet renkleri de sistem temasına uyuyor.
- **Çoklu PDF + silme testi:** İkinci bir sentetik PDF (`test_product_guide.pdf`, ürün kılavuzu) oluşturulup yüklendi; iki belge aynı anda koleksiyondayken doğru belgeye doğru atıfla yönlendirme doğrulandı, sonra silinip verinin tamamen ve izole şekilde kalktığı doğrulandı.
- **Streaming (SSE):** `foundry.py`'ye `chat_stream()` eklendi (`stream=True` ile OpenAI SDK). `main.py`'de mod-yönlendirme mantığı `_plan_chat()` yardımcı fonksiyonuna çıkarıldı (hem `/chat` hem yeni `/chat/stream` bunu kullanıyor, kod tekrarı önlendi — bu refactor olmadan `main.py` 150 satır sınırını aşacaktı). `/chat/stream`, `text/event-stream` ile üç olay tipi yayınlıyor: `meta` (mode+sources+retrieval_ms), `token` (parça parça metin), `done`. Mesaj inşası `prompts.py`'ye taşınan `build_messages()` fonksiyonunda merkezileşti (Z5 kuralına uygun — tüm prompt mantığı `prompts.py`'de). Frontend'de `api.ts`'ye `sendChatStream()` (fetch + `ReadableStream` okuma, SSE blok ayrıştırma) eklendi; `Chat.tsx` artık `sendChat` yerine bunu kullanıyor, assistant mesajı boş placeholder olarak eklenip token geldikçe büyütülüyor.

**Test sonuçları**
- `/chat/stream`'i `curl -sN` ile doğrudan test ettim: `meta` olayı doğru mode/sources/retrieval_ms taşıyor, `token` olayları kelime parçaları halinde geliyor, `done` ile bitiyor; birleştirilen metin `/chat`'in ürettiğiyle tutarlı.
- Gerçek tarayıcıda: "Masraf iadesi kaç gün içinde ödenir?" sorusu gönderildi, "yazıyor..." önce boş baloncukta göründü, ardından metin token token büyüdü, sonunda "Belgeden" rozeti + doğru cevap + `Getirme: 798ms · Üretim: 5196ms` + "Kaynaklar (3)" göründü — tamamı beklenen davranış.
- İlk tarayıcı denemesinde Enter tuşu mesajı göndermedi (input'a hiç istek gitmedi, konsol/network log'unda hiçbir iz yoktu) — FAZ 2'de belgelenen aynı browser-automation artefaktı (hızlı click+type+Enter, hydration tamamlanmadan). İkinci denemede input'a önce tıklayıp metni yazıp "Gönder" butonuna ayrı tıklayınca sorunsuz çalıştı; bu uygulamanın gerçek bir hatası değil.
- Çoklu belge testi: `test_product_guide.pdf` yüklendi (2 sayfa, 2 chunk), "TaskFlow Pro kullanıcı başına yıllık ücreti nedir?" sorusu doğru şekilde `test_product_guide.pdf s.2`'yi buldu (skor 0.78), `test_handbook.pdf`'in içeriğiyle karışmadı. Silindikten sonra aynı soru `mode=general`'e düştü, halüsinasyon yapılmadı.
- `npx tsc --noEmit` hatasız.

**Kabul kriteri**
- [x] Süre/token gösterimi UI'da görünüyor
- [x] Dark mode: sistem temasına göre otomatik, bileşen düzeyinde de tutarlı
- [x] Çoklu PDF yükleme + silme: doğru izolasyon, çapraz-belge karışması yok
- [x] Streaming: backend SSE + frontend token-token render, gerçek tarayıcıda görsel doğrulandı
- [~] BM25 karşılaştırma denemesi — bilinçli olarak atlandı (bkz. Karar Defteri); mevcut embedding tabanlı aramanın kalibre edilmiş eşiği (FAZ 2) ve FAZ 3'teki gözlemlenen doğruluk zaten PLAN'ın asıl hedefini (doğru belge/sayfa bulma) karşılıyor, ek bir kütüphane/deney bu noktada orantısız bir maliyet-fayda taşıyordu

**Özet:** FAZ 4'ün en değerli parçası streaming oldu — hem kullanıcı deneyimini (yanıt beklerken boş ekran yerine token akışı) hem de kod organizasyonunu iyileştirdi (mod-yönlendirme mantığının `_plan_chat()`'e çıkarılması `/chat` ve `/chat/stream` arasında tekrarı önledi ve `main.py`'yi 150 satır sınırının altında tuttu). Dark mode ve süre gösterimi küçük ama tamamlayıcı iyileştirmeler. Çoklu belge/silme testi veri izolasyonunu doğruladı. BM25 denemesi kapsam-dışı bırakıldı; gerekçesi Karar Defteri'nde.

---

### FAZ 5 — Canlı kullanım sonrası hata giderme (2026-08-19)

Kullanıcı üretimde iki belirti bildirdi: (1) model bazen "saçma" cevaplar veriyor, (2) yüklü bir PDF hakkında soru sorulduğunda bazen "belgeye erişimim yok" diyor. İkisi de FAZ 0-4 kabul kriterlerinde görünmeyen, gerçek kullanımda ortaya çıkan regresyon/kapsam boşluklarıydı — detaylar Hata Defteri #5 ve #6'da.

Ayrıca: kullanıcının makinesinde bu PLAN'a dayanmayan, farklı dosya adlarıyla (chunking.py/embeddings.py/foundry_client.py/rag.py/vector_store.py) yazılmış paralel bir proje klasörü (`Foundry Local LLM - RAG/`) daha vardı ve o oturumda arka planda hâlâ çalışıyordu — kullanıcının sorduğu sorular fiilen bu projeye gidiyordu, `RAG Project`'e değil. Kullanıcı bu klasörün eski/çöp olduğunu teyit etti; o sunucular durduruldu, `RAG Project`'teki backend/frontend başlatıldı. **Ders:** "model saçma cevap veriyor" gibi bir şikayet geldiğinde önce hangi sürecin gerçekten `localhost:3000`/`:8000`'i dinlediği (`lsof`/`ps aux`) doğrulanmalı — kod incelemesi yanlış klasörde yapılırsa tamamen zaman kaybı olur.

**Kabul kriteri**
- [x] Eski/paralel proje süreçleri durduruldu, `RAG Project` backend+frontend ayakta
- [x] Tekrar/dejenerasyon döngüsü artık noktalamasız öbek tekrarında da kesiliyor (doğrulandı)
- [x] Cross-lingual (İngilizce belge + Türkçe soru) belge sorusu artık doğru şekilde Mod B'ye düşüyor (doğrulandı)

**Özet:** Kullanıcının bildirdiği iki belirtinin de kökeninde kod hatası değil, ölçülmemiş bir varsayım vardı: tekrar-kesme filtresi yalnızca noktalamaya güveniyordu, eşik kalibrasyonu yalnızca tek-dilli senaryoda yapılmıştı. Her ikisi de gerçek veriyle yeniden ölçülüp düzeltildi.

**Ek iki düzeltme (aynı oturumda, zaman baskısı altında runtime değiştirmeden):**

1. **Sentinel-token deseni** (`prompts.py`: `SENTINEL = "YETERSIZ_BAGLAM"`, `resolve_sentinel()`): Modelden Türkçe "Bu bilgi yüklenen belgede yok." cümlesini harfiyen üretmesini istemek yerine (küçük modelde güvenilmez, bkz. Karar Defteri), yalnızca tek bir sabit kelime üretmesi isteniyor; `main.py` bu kelimeyi görünce kullanıcıya sabit Türkçe cümleyi enjekte ediyor — modelin cümle üretme kalitesine hiç bağımlı değil. Hem `/chat` hem `/chat/stream` (arabellekleme ile, ham SENTINEL kelimesi kullanıcıya hiç sızmıyor) için doğrulandı: eşik üstü ama context'te cevabı olmayan bir soruda artık birebir garanti cümle dönüyor.
2. **PDF metin temizliği** (`ingest.py`: `_clean_text`): Bazı PDF'lerin font kodlaması kelimeler arasına görünmez `\t`/`\r`/`\xa0` karakterleri sokuşturuyor (`"accomplish\t\r\xa0this\t\r\xa0transition"` gibi ham çıktı gözlendi). Bu çöp context olarak modele gidiyordu. Temizlik sonrası aynı belge 19 yerine 16 chunk'a indi (daha kompakt, daha az gürültü) ve arama skorları yükseldi (aynı ilgili soru için 0.42 → 0.49).

**Gözlemlenen ayrı bir sınırlama (düzeltilmedi, kayda geçirildi):** İngilizce belgeden alınan context ile cevap verirken model bazen "Always answer in Turkish" talimatına rağmen İngilizce cevap veriyor (context dilini taklit ediyor). Bu, cross-lingual RAG'de bilinen bir küçük-model davranışı; zaman kısıtı nedeniyle bu oturumda ele alınmadı.

---

## 3. Hata Defteri

### #1 — Embedding modeli katalogda "yok" gibi görünüyordu (≈90 dk)

**Belirti:** `foundry model list`, `foundry model info qwen3-embedding-0.6b`, `foundry model download qwen3-embedding-0.6b` hepsi "not found in catalog" hatası verdi. `curl .../v1/embeddings` de 500 (Input/output error) döndü.

**Sanılan sebep (1. aşama):** Model bu Foundry Local sürümünde/platformda (macOS) hiç sunulmuyor; alternatif olarak `sentence-transformers` gibi Foundry dışı bir çözüm gerekebilir.

**Sanılan sebep (2. aşama):** CLI'nin `model list` çıktısında her seferinde 7 tane "Failed to process model #0 on page 1" hatası vardı. `foundry-local-sdk==0.3.1` ile ham `/foundry/list` endpoint'i doğrudan sorgulandığında **72 kayıt, 40 alias**, tamamı `chat-completion` / `vision-language-chat` / `automatic-speech-recognition` — embedding **gerçekten yok**. Bu, live bir Azure Foundry catalog fetch'iydi (log: "Fetching model list from Azure Foundry catalog..."), stale cache değildi. Görünüşte kesin kanıttı.

**Gerçek sebep:** `localhost:54791`'deki CLI/REST servisi ile `foundry-local-sdk` 1.x'in **native Core Interop** katmanı **iki ayrı kataloğa** bakıyor. Kullanıcının bu makinede daha önce çalıştırdığı bir projeden kalan `~/.foundry-local-rag/cache/models/foundry.modelinfo.json` dosyasında `qwen3-embedding-0.6b` ve `qwen3-embedding-8b` (`task: "embeddings"`) kayıtlı olduğu görüldü — bu iz, doğru mekanizmanın var olduğunun kanıtıydı. `foundry-local-sdk` 1.2.4'te `Configuration(app_name=...)` ile başlatılan `FoundryLocalManager`, `mgr.catalog.list_models()` çağrısında **tamamen farklı, daha zengin bir katalog** (47 alias, embedding dahil) döndürüyor — bu native runtime, CLI'nin bağlandığı REST servisinden bağımsız çalışıyor.

**Çözüm:**
```python
from foundry_local_sdk import FoundryLocalManager, Configuration
config = Configuration(app_name="rag-project")
mgr = FoundryLocalManager(config)
model = mgr.catalog.get_model("qwen3-embedding-0.6b")
cpu_variant = [v for v in model.variants if "cpu" in v.id.lower()][0]
model.select_variant(cpu_variant)
model.download()
model.load()
client = model.get_embedding_client()
resp = client.generate_embeddings(["metin1", "metin2"])  # batch destekli
```
Taze bir `app_name` ile bile (eski cache'e bağımlı olmadan) katalogda embedding modelleri doğrulandı — yani sorun cache değil, **hangi API katmanının sorgulandığıydı**.

**Ders:** `foundry-local-sdk` PyPI paketinin 0.x ve 1.x sürümleri arasında mimari fark var; CLI'nin gösterdiği katalog ile SDK'nın native kataloğu **aynı olmayabilir**. "CLI'de yok" → "hiçbir yerde yok" sonucuna sıçramadan önce SDK'nın kendi native yolunu da kontrol etmek gerekir. `foundry.py` içindeki `chat()` REST (`openai` SDK, port 54791) kullanırken `embed()` native SDK (`foundry_local_sdk`) kullanacak — bu asimetri kasıtlı ve gerekli.

**Süre:** ~90 dakika (çoklu doğrulama turu: CLI, ham REST, klasik SDK, native SDK).

---

### #2 — PDF yükleme 500 hatası: "Embedding generation failed... Operation was cancelled"

**Belirti:** Kullanıcı gerçek bir PDF yüklemeyi denedi, `/upload` 500 döndü. Backend log'unda `foundry_local_sdk.exception.FoundryLocalException: Embedding generation failed for model 'qwen3-embedding-0.6b-generic-cpu:1': Operation was cancelled`. Aynı gün önceki yüklemeler (FAZ 2/4 testleri) sorunsuz çalışmıştı.

**Sanılan sebep:** İlk bakışta modelin/servisin genel olarak bozulduğu düşünülebilirdi.

**Gerçek sebep:** `foundry.py`'deki `_embed_client` modül-seviyesinde önbelleğe alınıyor (`_get_embed_client()` içinde `if _embed_client is not None: return _embed_client`) ve backend süreci o gün saatlerce kesintisiz çalışmıştı. Native embedding oturumu uzun süre boşta kaldıktan sonra alttaki Foundry Local Core Interop sürecinde koptu; önbellekteki istemci referansı artık geçersizdi ama kod bunu hiç algılamıyor, her çağrıda aynı bozuk istemciyi kullanmaya devam ediyordu. Taze bir Python sürecinde `foundry.embed(...)` çağrısı anında ve sorunsuz çalıştı — bu, sorunun modelde değil, uzun ömürlü sürecin önbelleğindeki bayat bağlantıda olduğunu doğruladı.

**Çözüm:** `embed()` artık `generate_embeddings()` başarısız olursa `_embed_client`'ı `None`'a resetleyip istemciyi yeniden kurup **bir kez daha** deniyor:
```python
def embed(texts: list[str]) -> list[list[float]]:
    global _embed_client
    client = _get_embed_client()
    try:
        response = client.generate_embeddings(texts)
    except Exception:
        _embed_client = None
        client = _get_embed_client()
        response = client.generate_embeddings(texts)
    return [item.embedding for item in response.data]
```

**Ders:** Uzun ömürlü bir Python sürecinde native/harici bir istemciyi sonsuza dek önbelleklemek riskli — alttaki bağlantı/oturum arka planda kopabilir ve kod bunu asla öğrenemez. "Bir kez kur, sonsuza dek kullan" önbellekleme deseni, en azından bir kerelik reset-ve-tekrar-dene mantığıyla korunmalı. Bu özellikle geliştirme sırasında saatlerce ayakta kalan `uvicorn` süreçlerinde (üretimde de olası) fark edilir.

---

### #3 — #2'nin "düzeltmesi" bizzat kalıcı 500'e yol açtı: `FoundryLocalManager is a singleton and has already been initialized`

**Belirti:** #2'nin reset-ve-tekrar-dene mantığı deploy edildikten sonra, ilk embedding hatasından **sonraki her** `/chat` ve `/upload` isteği 500 vermeye başladı — yani düzeltme, tek seferlik bir arızayı kalıcı bir arızaya çevirdi. Log'da: `foundry_local_sdk.exception.FoundryLocalException: FoundryLocalManager is a singleton and has already been initialized.`

**Gerçek sebep:** `_get_embed_client()`'ın reset yolu `_embed_client = None` yaptıktan sonra fonksiyonu baştan çağırıyordu, bu da içeride `FoundryLocalManager(config)`'i **yeniden** inşa ediyordu. Ama `FoundryLocalManager`, SDK içinde class-level bir lock ile korunan gerçek bir process-singleton (`foundry_local_manager.py`: `instance` bir kez set edildikten sonra constructor tekrar çağrılırsa exception fırlatıyor). Yani retry mantığı aslında hiçbir zaman çalışamazdı — süreç içinde manager bir kez kurulduktan sonra, herhangi bir embed hatası artık *kalıcı* bir 500'e dönüşüyordu.

**Çözüm:** Manager'ı (ve üzerinde `select_variant`/`download`/`load` uygulanmış `model`'i) modül seviyesinde ayrı bir `_embed_model` değişkeninde saklayıp **asla yeniden kurmuyoruz**. Retry'de sadece `model.get_embedding_client()` tekrar çağrılıyor — bu ucuz bir işlem (`model_variant.py`: sadece var olan native handle'ı yeni bir `EmbeddingClient` sarmalayıcısına koyuyor, yeniden yükleme yapmıyor):
```python
def _get_embed_model():
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    config = Configuration(app_name=settings.EMBED_APP_NAME)
    manager = FoundryLocalManager(config)
    model = manager.catalog.get_model(settings.EMBED_MODEL_ALIAS)
    variant = next(v for v in model.variants if settings.EMBED_VARIANT_DEVICE in v.id.lower())
    model.select_variant(variant)
    model.download()
    model.load()
    _embed_model = model
    return _embed_model

def _get_embed_client(fresh: bool = False):
    global _embed_client
    if _embed_client is not None and not fresh:
        return _embed_client
    _embed_client = _get_embed_model().get_embedding_client()
    return _embed_client
```

**Ders:** Bir SDK nesnesini "yeniden kurarak tazelemek" güvenli bir varsayım değil — altta process-singleton bir kaynak varsa (burada `FoundryLocalManager`), yeniden kurma denemesi ilk hatadan daha kötü, kalıcı bir arızaya yol açabilir. Bir önceki düzeltmeyi canlıda test ederken (health check + tek bir `/chat` çağrısı) bu regresyon fark edilmedi çünkü health check embed'e hiç dokunmuyor ve tek çağrı retry yoluna hiç girmiyordu; regresyon ancak kullanıcı gerçek kullanımda ikinci/üçüncü bir embed hatasına denk gelince ortaya çıktı. Retry/reset mantığı eklerken, "reset" ile kastedilenin tam olarak hangi katmanı (client mi, altındaki singleton kaynak mı) yeniden kurduğunu SDK kaynağından doğrulamak gerekiyor.

---

### #4 — "Yükleme başarısız (500)" ama birkaç dakika sonra belge listede beliriyor: Next.js rewrite proxy'si ~30sn'de timeout oluyor

**Belirti:** Kullanıcı gerçek (6 sayfa/19 parça) bir PDF yükledi, arayüzde başarısız/500 gördü — ama sonrasında `/documents`'a bakıldığında belge zaten oradaydı, sanki hiç hata olmamış gibi. Kullanıcı gizli sekmede bile tekrar denedi, aynı sonuç. Backend log'unda bu isteklere ait **hiçbir traceback yoktu** — bu, hatanın FastAPI'den değil başka bir katmandan geldiğinin ilk işaretiydi.

**Teşhis:** Aynı dosyayı iki farklı yoldan, zamanlayarak denendi:
- `localhost:3000/api/upload` (Next.js `next.config.ts` içindeki `rewrites()` üzerinden proxy) → **tam 30.018 saniyede** düz metin `Internal Server Error` (500) döndü, backend log'unda hiçbir iz yok.
- `127.0.0.1:8000/upload` (backend'e doğrudan, proxy'siz) → **103 saniyede** `200 OK` ile tamamlandı.

Yani gerçek sorun: Qwen3-Embedding'in bu makinede (CPU varyant) 19 parçayı embed etmesi ~80-100 saniye sürüyor (parça başına ~5sn — bkz. Karar Defteri'ndeki CPU varyant tercihi, o zaman "kısa metinler için kabul edilebilir" denmişti ama toplu belge yüklemede birikince kabul edilemez oluyor). Next.js dev sunucusunun `rewrites()` proxy katmanı bu süreyi kaldıramıyor, ~30sn'de bağlantıyı kesip kendi 500'ünü döndürüyor — **backend'e hiç ulaşmamış gibi davranıyor ama backend istek almaya devam ediyor** ve arka planda embed işlemini bitirip veriyi ChromaDB'ye yazıyor. Kullanıcı arayüzde hatayı görüp sayfayı yenilediğinde (doğal bir refleks), az sonra belge listede beliriyor — "alay ediyor gibi" görünmesinin sebebi bu: hata gerçek ama geçici, arka plandaki iş gerçek ve kalıcı.

**Çözüm:** `/api/upload` için genel `rewrites()` kuralına güvenmek yerine özel bir Next.js Route Handler eklendi (`frontend/src/app/api/upload/route.ts`), isteği doğrudan backend'e `fetch` ile iletiyor — rewrite proxy katmanının süre sınırına hiç girmiyor:
```ts
export async function POST(request: Request) {
  const formData = await request.formData();
  const backendRes = await fetch("http://127.0.0.1:8000/upload", {
    method: "POST",
    body: formData,
  });
  const body = await backendRes.text();
  return new NextResponse(body, {
    status: backendRes.status,
    headers: { "Content-Type": backendRes.headers.get("Content-Type") ?? "application/json" },
  });
}
```
Next.js'in route çözümleme sırasında dosya sistemindeki eşleşen route'lar (`app/api/upload/route.ts`), genel dizi biçimindeki `rewrites()` kuralından önce kontrol ediliyor, bu yüzden bu dosya var olduğu sürece `/api/upload` isteği artık hiç rewrite'a girmiyor. Doğrulama: aynı dosya bu route üzerinden 78 saniyede `200 OK` ile tamamlandı — proxy kesintisi olmadan.

**Ders:** Diğer öğrencilerin farklı PDF kütüphaneleri kullanmasının sebebi muhtemelen tam da bu değildi, ama bu proje özelinde gerçek darboğaz PDF ayrıştırma değil, **native embedding çağrısının süresiydi** — ve bu süre bir ara katman (dev-server proxy) tarafından görünmez şekilde kesiliyordu. "Bende de aynı hata var, X kütüphanesini kullansam düzelir mi" tarzı bir teşhis burada yanıltıcı olurdu; asıl ipucu, hatanın backend log'unda hiç görünmemesiydi. Kullanıcı arayüzünde "500" görmek her zaman o isteğin sunucuya ulaştığı ve orada patladığı anlamına gelmez — ara katmanlar (proxy, rewrite, ters vekil) da kendi adına sahte bir hata üretebilir.

---

### #5 — Tekrar/dejenerasyon filtresi noktalamasız öbek tekrarını yakalamıyordu (~30 dk)

**Belirti:** "Fransanın başkenti neresidir?" gibi basit bir soruda model doğru başlıyor ("Başkent Fransa'nın Kuzeydoğu bölgesinde yer alan bir metropolitenrabadır.") ama hemen ardından "Fransa'nın Kuzeydoğu bölgesinde yer alan" öbeğini **hiç nokta koymadan** onlarca kez art arda üretip 512 token'ı dolduruyordu (`/chat` 80+ saniye sürdü). LEARNING.md FAZ 4'te bu sınıf hatanın "Deterministik tekrar-kesme (`_truncate_repetition`)" ile çözüldüğü kayıtlıydı, ama canlıda tekrar gözlendi.

**Gerçek sebep:** `_truncate_repetition`, metni `re.split(r"(?<=[.!?\n])\s+", text)` ile **cümle sonu noktalamasına göre** bölüp art arda aynı normalize-cümleyi arıyordu. Tekrar eden öbek noktalamasız üretildiğinde (aralarında hiç `.`/`!`/`?`/`\n` yok), tüm tekrar tek bir "cümle" olarak görülüyor ve filtre hiç tetiklenmiyordu. FAZ 4'ün test senaryosu ("Bugün günlerden ne?") tesadüfen noktalı tekrar üretmişti, bu yüzden regresyon o zaman fark edilmemişti.

**Çözüm:** `foundry.py`'ye noktalamadan bağımsız, kelime dizisi üzerinde çalışan `_find_repetition_cut()` eklendi (art arda tekrarlanan 4-25 kelimelik bir öbek ararsa, tekrarın başladığı yeri döner). `_truncate_repetition()` önce bunu, sonra mevcut cümle-düzeyi kontrolü uyguluyor. `chat_stream()`'e de aynı kontrol eklendi — sadece cümle sonunda değil, her token geldikçe kontrol edip döngüyü erkenden kırıyor. Doğrulama: aynı soru streaming'de önce ~55-80 sn sürüyordu, düzeltmeden sonra ~6 sn'de doğru yerde kesiliyor.

**Ders:** Noktalama-bazlı tekrar tespiti, modelin noktalama koymadan dejenere olduğu durumları kaçırır. Tekrar tespiti kelime/token dizisi üzerinde, noktalamadan bağımsız yapılmalı; noktalama-bazlı kontrol (rakam farkı olan cümleleri yakalamak için) tamamlayıcı olarak kalabilir ama tek başına yeterli değil.

**Süre:** ~30 dakika.

---

### #6 — Eşik (0.45) yalnızca tek-dilli senaryoda kalibre edilmişti, İngilizce belge + Türkçe soruda belgeyi kaçırıyordu (~20 dk)

**Belirti:** Kullanıcının yüklediği İngilizce bir PDF ("effective_introductions_handout.pdf") hakkında Türkçe soru sorulduğunda (`"Bu belgede etkili bir tanışma için ne öneriliyor?"`) sistem Mod A'ya düşüyor ve model dürüstçe "böyle bir belgeye erişimim yok" benzeri bir şey söylüyordu — halbuki belge tam olarak o konudaydı ve zaten indexliydi (`chunk_count=19`).

**Gerçek sebep:** `/search` ile ölçüldü: aynı İngilizce belgeye karşı gerçekten ilgili Türkçe sorular 0.42-0.52 skorluyor, alakasız Türkçe sorular 0.17-0.21 skorluyor — net bir ayrım var ama FAZ 2'de yalnızca **tek-dilli** (Türkçe belge + Türkçe soru: ilgili 0.60-0.75, alakasız 0.29-0.35) kalibre edilen 0.45 eşiği, cross-lingual ilgili sorunun skorundan bile yüksek. Kalibrasyon, kullanıcının gerçekte kullandığı senaryoyu (farklı dilde belge) hiç kapsamıyordu.

**Çözüm:** `SIMILARITY_THRESHOLD` 0.45'ten **0.38**'e çekildi — bu değer hem tek-dilli hem cross-lingual ölçülen alakasız-maksimum (0.354 / 0.21) ile ilgili-minimum (0.597 / 0.42) aralıklarının kesişiminde. Doğrulama: aynı soru artık `mode=document` dönüyor, doğru sayfalara (`s.1`, `s.5`) doğru atıfla.

**Ders:** Eşik kalibrasyonu (Bölüm 6.2) tek bir dil/belge kombinasyonuyla yapılırsa, farklı bir dildeki belgeye genelleşmeyebilir — çünkü cross-lingual embedding benzerliği yapısal olarak tek-dilliden daha düşük çıkar (bu bir hata değil, modelin kendisinin özelliği). Kapsamlı bir kalibrasyon, kullanıcının gerçekte yükleyeceği belge dillerini de içermeli. 0.38 iki örneklem noktasıyla seçildi; farklı bir belge dili/konusu ile tekrar sapma gösterirse yeniden ölçülmeli.

**Süre:** ~20 dakika (teşhis + doğrulama).

---

## 4. Karar Defteri

| Karar | Değer | Gerekçe |
|---|---|---|
| Backend Python sürümü | 3.12 (Homebrew) | Sistem `python3` 3.9.6, `foundry-local-sdk` 1.x `dict \| None` sözdizimi nedeniyle 3.10+ istiyor. PLAN 3.11+ istiyor, 3.12 mevcut ve uyumlu. |
| `CHAT_MODEL` | `Phi-4-mini-instruct-generic-gpu:5` | FAZ 0'da `/v1/models`'tan doğrulanan tam ID. Alias (`phi-4-mini`) REST'te kullanılamıyor. |
| Embedding erişim yöntemi | `foundry-local-sdk` native Core Interop (REST değil) | REST `/v1/embeddings` 500 hatası veriyor; CLI kataloğunda embedding modeli yok. SDK'nın native kataloğunda var (bkz. Hata Defteri #1). PLAN 5.5'in ikinci fallback dalı ("REST desteklenmiyor → foundry-local-sdk → get_embedding_client()") tam olarak bu duruma karşılık geliyor. |
| `EMBED_MODEL_ALIAS` | `qwen3-embedding-0.6b` (CPU varyant) | GPU varyant için `WebGpuExecutionProvider` register edilmemiş; register etmek Foundry Local kurulumuna müdahale sınırına yakın (Y1) olduğu için CPU varyant tercih edildi. 0.6B model CPU'da kısa metin embedding'leri için kabul edilebilir hızda. |
| `EMBED_DIM` | 1024 | FAZ 0'da `generate_embedding()` çıktısından ölçüldü. |
| `EMBED_APP_NAME` | `rag-project` | `foundry-local-sdk` `Configuration(app_name=...)` için proje kimliği; cache `~/.rag-project/cache/models` altında tutulur. |
| Türkçe strateji | İngilizce system prompt + "Always answer in Turkish." | FAZ 0'da saf Türkçe soruda tekrar/dejenerasyon bug'ı gözlendi (PLAN 5.4 ile uyumlu risk). |
| `SIMILARITY_THRESHOLD` | ~~0.45~~ → **0.38** (FAZ 5) | FAZ 2'de 10 soruluk tek-dilli (TR belge + TR soru) kalibrasyon testiyle 0.45 ölçüldü: ilgili grup 0.597-0.753, alakasız grup 0.287-0.354. FAZ 5'te cross-lingual (EN belge + TR soru) gerçek kullanımda bu eşiğin ilgili soruları (0.42-0.52) bile Mod A'ya düşürdüğü görüldü; 0.38'e çekildi (bkz. Hata Defteri #6). |
| Sorgu embedding'ine instruction öneki | `embed_query_instruction()` (`prompts.py`), yalnızca sorguda, pasajlarda değil | Qwen3-Embedding instruction-aware bir model; ham sorguyla doğru/yanlış chunk skorları çok yakın çıktı (0.016 fark), talimat önekiyle ayrım netleşti (0.05 fark) ve doğru chunk ilk sıraya geçti. |
| Eşik-altı düşüş bildirimi | Ayrı bir response alanı yerine cevap metnine düz metin önek ("Not: Belgede ilgili bilgi bulamadım...") | `models.py`'de yeni alan eklemek yerine mevcut `answer` string'ine önek eklemek daha basit; PLAN'da bu davranış için ayrı bir alan şart koşulmuyor, sadece kullanıcının Mod A'ya düşüldüğünü anlaması gerekiyor — mod rozeti zaten bunu görsel olarak da gösteriyor. |
| RAG "bulunamadı" cümlesinin harfiyen üretilmemesi | Kabul edildi, zorlanmadı | FAZ 3 testinde model (Phi-4-mini) eşik üstü ama cevapsız durumda anlamca doğru ama string'i birebir tutmayan bir cümle üretti. Post-processing ile zorlamak (örn. regex/exact-match fallback enjeksiyonu) PLAN'ın kapsamında değil ve gereksiz karmaşıklık katardı; asıl kriter olan "halüsinasyon yapmama" zaten sağlanıyor. |
| Mod-yönlendirme mantığının `retrieve.decide_mode()`'a çıkarılması | `main.py` yerine `retrieve.py`'de merkezi karar fonksiyonu | FAZ 4'te `/chat/stream` eklenirken aynı mantığın iki yerde tekrarlanması `main.py`'yi 150 satır sınırının üzerine çıkarıyordu (Z8). Mesaj inşası da `prompts.py`'ye taşındı (Z5: tüm prompt mantığı orada olmalı). `_plan_chat()` yardımcı fonksiyonu her iki endpoint'te de paylaşılıyor. |
| BM25 karşılaştırma denemesi | Yapılmadı, bilinçli olarak atlandı | FAZ 2'nin eşik kalibrasyonu ve FAZ 3'ün gerçek testleri embedding tabanlı aramanın bu küçük korpusta zaten doğru çalıştığını gösterdi; ek bir kütüphane (`rank_bm25` vb.) ve karşılaştırma kodu eklemek, PLAN'ın asıl hedefine (doğru belge/sayfa/atıf) katkısı sınırlıyken karmaşıklık/bağımlılık maliyeti taşıyordu. |
| Arayüz yeniden tasarımı — tipografi/renk sistemi (1. tur) | Fraunces (başlık) + IBM Plex Sans (gövde) + IBM Plex Sans Condensed (rozet) + IBM Plex Mono (veri) — "kayıt defteri / dosya dolabı" teması, mod rozetleri mürekkep damgası olarak tasarlandı | FAZ 1-4'ün varsayılan create-next-app görünümü (Geist + generic mavi/gri sohbet balonları) kullanıcı tarafından "iğrenç" olarak nitelendirildi. Uygulamanın konusu (offline, belge, "Foundry") bir arşiv/kayıt ofisi hissiyla örtüştüğü için bu yön seçildi; jenerik AI-tasarım klişelerinden (krem+serif+turuncu / siyah+neon) kaçınıldı. |
| Arayüz — tipografi düzeltmesi (2. tur, kullanıcı geri bildirimi) | Fraunces + Plex Sans Condensed tamamen kaldırıldı; sadece IBM Plex Sans (gövde) + IBM Plex Mono (başlık/veri/rozet) kaldı. Mühür logosu italik serif "F" yerine mono `[F/]` işaretine döndü. | Kullanıcı ilk turu "çok italik" ve "damga çok kötü" olarak nitelendirip "daha teknolojik bir hava" istedi. İki font ailesini atıp tek bir mono-ağırlıklı sisteme geçmek hem isteği karşıladı hem de tasarımı sadeleştirdi (4 font ailesinden 2'ye). |
| Mod göstergesi — damga kaldırıldı | Döndürülmüş/çift-çerçeveli "damga" kutusu yerine düz renkli nokta + mono küçük harfli etiket (`● Belgeden`) | Kullanıcı doğrudan "damga görmek çok kötü, kaldıralım" dedi. Renk kodlaması (ember/verified) ve sol kenar çizgisi korunarak mod ayrımı yine görsel kalıyor, sadece dekoratif "mühür" efekti gitti. |
| Belge yükleme — sohbet input'una taşındı | Sidebar'daki sürükle-bırak kutusu kaldırıldı; `Chat.tsx`'te `+` ekleme butonu (dosya seçici) ve tüm sohbet alanına sürükle-bırak desteği eklendi | Kullanıcı "günümüzdeki arayüzler gibi" (ChatGPT tarzı ataç/+ butonu) istedi. `Uploader.tsx` bileşeni artık kullanılmadığı için tamamen silindi (backwards-compat shim bırakılmadı). |
| Sohbet geçmişi + "Yeni Sohbet" | Backend/DB değişikliği yok — `localStorage` tabanlı, tamamen istemci taraflı oturum listesi (`src/lib/sessions.ts`) | Kullanıcı "kayıt tutuluyorsa sohbet geçmişi ve yeni sohbet seçeneği" istedi. PLAN'da çok-oturumlu sohbet geçmişi yoktu ve backend'e bir sohbet-oturumu tablosu eklemek kapsamı genişletirdi; `localStorage` çözümü hem "offline" ilkesini bozmuyor (veri cihazdan çıkmıyor) hem de sıfır backend değişikliğiyle isteği karşılıyor. `messages` state'i `Chat.tsx`'ten `page.tsx`'e taşınıp `Chat` kontrollü bileşene çevrildi. |
| Bugünün tarihi system prompt'a ekleniyor | `prompts.py`'de `_today_tr()` ile Türkçe tarih string'i her mesajda system prompt'un sonuna ekleniyor | Kullanıcı "bugün günlerden ne" sorusuna modelin şiirsel/anlamsız bir cevap uydurduğunu bildirdi. Nedeni: LLM'lerin gerçek zamanlı tarih bilgisi yoktur, sorulduğunda halüsinasyon yapar — bu evrensel bir LLM sınırlaması, sistemin hatası değil. Tarihi prompt'a enjekte etmek bu spesifik durumu düzeltir (doğrulandı: model artık ilk cümlede doğru tarihi söylüyor); modelin genel "bazı yerlerde saçmalaması" (küçük model, düşük parametre sayısı) ise prompt mühendisliğiyle tam çözülemeyen, PLAN'ın baştan kabul ettiği bir risktir. |
| `frequency_penalty`/`presence_penalty` ile tekrar bastırma | Denendi, üretime alınmadı | Tarih düzeltmesinden sonra bile model bazen tekrar döngüsüne giriyordu ("6 gününün 6 gününün..."). OpenAI-uyumlu API'nin standart `frequency_penalty`/`presence_penalty` parametreleriyle iki ayrı deney yapıldı: hafif değerler (0.6/0.3) tekrar döngüsünü kısalttı ama yine sonsuz döngüye girdi; agresif değerler (1.3/1.0) + düşük sıcaklık döngüyü kırdı ama bu kez modeli farklı bir halüsinasyona (verilen tarihi yok sayıp uydurma bir "veritabanı kesim tarihi" anlatısına) sürükledi — yani parametre ayarı riski ortadan kaldırmıyor, sadece hangi tür hataya düştüğünü değiştiriyor. Güvenilir bir iyileştirme olmadığı için kod değişikliği yapılmadı; bu, PLAN'ın kabul ettiği "küçük model" riskinin somut bir kanıtı olarak kayda geçti. |
| Deterministik tekrar-kesme (`_truncate_repetition`) | `foundry.py`'de: art arda iki cümle rakamlar maskelenerek (`\d+` → `#`) normalize edilip karşılaştırılıyor; eşleşirse ikinciden itibaren kesiliyor. `chat()` tam metni post-hoc kırpıyor, `chat_stream()` cümle sınırında tespit edip üretimi erken durduruyor (`break`). | Parametre ayarları (penalty/temperature) güvenilir değildi; asıl gözlemlenen semptom hep "aynı cümle/kalıp art arda tekrarı" olduğu için bunu doğrudan, deterministik olarak yakalamak daha güvenilir çıktı. Test: aynı "Bugün günlerden ne?" sorusu önce 48-52 saniyede sonsuz tekrar üretiyordu, düzeltmeden sonra 4-7 saniyede tek seferlik, tekrarsız cevap veriyor — hem doğruluk hem gecikme (streaming'de erken durdurma sayesinde) iyileşti. Sistem promptlarına da "aynı cümleyi/fikri iki kez tekrarlama" talimatı eklendi (tamamlayıcı, garantili değil). |
| "Bu belge ne hakkında?" tarzı özet soruları Mod A'ya düşüyor | Bilinçli olarak düzeltilmedi, kullanıcıya raporlandı | `/search` ile ölçüldü: böyle genel sorular en iyi ihtimalle ~0.35 skor alıyor (eşik 0.45), çünkü tek bir chunk "belgenin tamamı hakkında" olamaz — bu chunk-tabanlı benzerlik aramasının bilinen bir sınırlaması, eşiği düşürerek çözülemez (düşürülürse alakasız sorular da yanlışlıkla Mod B'ye düşer). Düzeltmek istenirse ayrı bir "özet modu" (tüm chunk'ları veya sayfa başına 1 chunk'ı bağlama ekleyen özel bir yol) gerekir — kapsam dışında bırakıldı, kullanıcı isterse ayrı bir iyileştirme olarak ele alınabilir. |

---
