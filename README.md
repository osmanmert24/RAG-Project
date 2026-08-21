# Foundry Local RAG

Foundry Local (Phi-4-mini) ve yerel embedding modeliyle tamamen çevrimdışı çalışan, PDF tabanlı bir RAG (Retrieval-Augmented Generation) soru-cevap uygulaması. Sohbet, embedding ve vektör arama dahil hiçbir bileşen internete veya bulut API'lerine bağımlı değildir — tüm işlem yerel makinede yapılır.

Geliştirme sürecinin ayrıntılı günlüğü, alınan kararlar ve karşılaşılan hatalar için bkz. [`LEARNING.md`](./LEARNING.md). Orijinal teknik şartname için bkz. [`PLAN.md`](./PLAN.md).

## Mimari

```
Next.js (3000) --/api/*--> FastAPI (8000) --REST--> Foundry Local (sohbet, Phi-4-mini)
                                |
                                +--native SDK--> Foundry Local Core Interop (embedding, Qwen3-Embedding)
                                |
                                +--> ChromaDB (yerel, dosya tabanlı vektör deposu)
```

- **Frontend:** Next.js 16 (App Router, TypeScript, Tailwind). `next.config.ts`'teki `rewrites()` ile `/api/*` istekleri backend'e proxy'lenir — tarayıcı sadece `localhost:3000` ile konuşur, CORS sorunu yoktur.
- **Backend:** FastAPI. Tek sorumluluklu modüller: `foundry.py` (tüm Foundry Local çağrıları), `prompts.py` (tüm LLM promptları), `ingest.py` (PDF → chunk), `store.py` (ChromaDB), `retrieve.py` (arama + mod kararı), `models.py` (Pydantic şemaları).
- **Sohbet modeli:** Phi-4-mini, Foundry Local'in OpenAI-uyumlu REST endpoint'i (`/v1/chat/completions`) üzerinden.
- **Embedding modeli:** Qwen3-Embedding-0.6B (CPU varyant), Foundry Local'in native "Core Interop" SDK katmanı üzerinden — bu model REST endpoint'inde sunulmaz, ayrıntı için `LEARNING.md` Hata Defteri #1'e bakınız.
- **Vektör deposu:** ChromaDB, `PersistentClient` ile embedded modda (ayrı bir sunucu süreci yok), cosine similarity.

## Ön Koşullar

1. **macOS**, Python **3.10+** (proje 3.12 ile geliştirildi/test edildi — sistem Python'ı 3.9 ise Homebrew ile 3.12 kurun).
2. **Node.js 20+** ve npm.
3. **Foundry Local** kurulu ve arka planda çalışıyor olmalı (`foundry service status`). Bu proje Foundry Local'i kurmaz/güncellemez — önceden kurulu olduğu varsayılır.
4. Foundry Local kataloğunda şu modeller indirilmiş olmalı:
   - Bir sohbet modeli (örn. `Phi-4-mini-instruct-generic-gpu`) — `foundry model list` ile tam ID'yi doğrulayın.
   - `qwen3-embedding-0.6b` embedding modeli — bu proje ilk `embed()` çağrısında modeli `foundry-local-sdk` üzerinden otomatik indirir/yükler (internet sadece bu tek seferlik indirme için gereklidir, sonrası tamamen offline'dır).

## Kurulum

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # gerekirse CHAT_MODEL'i `foundry model list` çıktısına göre güncelleyin
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`.env` içindeki tüm ayarlar (model isimleri, chunk boyutu, benzerlik eşiği, sıcaklık vb.) için `backend/.env.example` dosyasına bakınız; hiçbir değer kodda sabitlenmemiştir.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Uygulama `http://localhost:3000` adresinde açılır. Backend'in `:8000`'de ayakta olması gerekir.

## Kullanım

1. Sol panelden bir PDF yükleyin (`+` butonu / sürükle-bırak).
2. Sohbet kutusuna sorunuzu yazın:
   - Belgeyle ilgiliyse ve benzerlik skoru eşiği (`SIMILARITY_THRESHOLD`, varsayılan 0.38) geçerse → **Belgeden** modunda, kaynak atıflı (`[dosya s.X]`) cevap.
   - "Bu belge ne hakkında?" gibi genel/özet sorularında sistem belgenin her sayfasından bir örnek alıp özetler (tek chunk'a bağlı kalmaz).
   - Belgeyle ilgisizse veya belge yüklenmemişse → **Genel bilgi** modunda, modelin kendi bilgisiyle cevap.
3. Cevabın altındaki "Kaynaklar" linkine tıklayarak hangi chunk'ların kullanıldığını görebilirsiniz.
4. Belgeler listesinden istediğiniz belgeyi silebilirsiniz.
5. Sol menüden "Yeni Sohbet" açabilir, üstüne gelip "Sil" ile eski sohbetleri tarayıcı hafızasından tamamen silebilirsiniz (sohbet geçmişi yalnızca tarayıcıda `localStorage`'da tutulur, sunucuya hiç gönderilmez).

## API Uç Noktaları

| Method | Yol | Açıklama |
|---|---|---|
| GET | `/health` | Servis durumu, model isimleri, belge/chunk sayısı |
| POST | `/chat` | Tek seferde tam cevap döner |
| POST | `/chat/stream` | Server-Sent Events ile token-token yanıt akışı (`meta` → `token`* → `done`) |
| POST | `/upload` | PDF yükle, chunk'la, embed'le, ChromaDB'ye ekle |
| GET | `/documents` | Yüklü belgelerin listesi |
| DELETE | `/documents/{doc_id}` | Belgeyi ve tüm chunk'larını sil |
| POST | `/search` | Ham vektör arama sonuçları (debug amaçlı) |

## Küçük modelin bilinen zayıflıklarına karşı alınan önlemler

Phi-4-mini (3.8B, INT4) küçük bir model olduğundan RAG'de tipik olarak görülen birkaç zayıflığı var; bunlara karşı uygulama katmanında (prompt gerektirmeden, deterministik) önlemler alındı:

- **Tekrar/dejenerasyon** (aynı cümleyi/öbeği sonsuza kadar tekrarlama): `foundry.py`'de noktalamadan bağımsız, kelime dizisi üzerinde çalışan bir tekrar tespiti üretimi erken durduruyor.
- **"Bulamadım" cevabını harfiyen üretmemesi**: Modelden uzun bir Türkçe cümleyi birebir tekrar üretmesini istemek yerine tek bir sabit "sentinel" kelime (`YETERSIZ_BAGLAM`) isteniyor; uygulama bu kelimeyi görünce kullanıcıya sabit, garanti bir cümle gösteriyor (`prompts.py: resolve_sentinel`).
- **Cross-lingual belgede düşük benzerlik skoru**: Türkçe soru + farklı dilde belge kombinasyonunda embedding benzerliği yapısal olarak daha düşük çıkıyor; eşik bunu kapsayacak şekilde kalibre edildi.
- **Özet sorularının chunk-bazlı aramada başarısız olması**: "Bu belge ne hakkında?" gibi sorular tek bir chunk'a iyi eşleşmiyor; bu soru tipi ayrıca tespit edilip sayfa-çeşitli bir örnekleme + ayrı bir özet prompt'uyla cevaplanıyor (`retrieve.py: _is_summary_intent`, `prompts.py: SYSTEM_PROMPT_SUMMARY`).
- **PDF'ten gelen görünmez karakter çöpü**: Bazı PDF'lerin font kodlaması kelime aralarına `\t`/`\r`/`\xa0` sokuşturuyor; `ingest.py` bunu temizliyor.

Bunların hiçbiri "her soruya özel bir yama" değil — yalnızca iki soru türü (nokta-atışı vs. genel/özet) ve genel geçerli veri/çıktı temizliği. Ayrıntılı teşhis süreci ve ölçümler için `LEARNING.md` Hata Defteri'ne bakınız.

## Bilinen Sınırlamalar

- Embedding modeli CPU varyantında çalışır (GPU varyantı için ek çalışma-zamanı yapılandırması gerekir, bu projenin kapsamı dışında bırakılmıştır).
- Foundry Local'ın dinlediği port sabit değildir (`foundry service status` ile değişebilir); değişirse `backend/.env`'deki `FOUNDRY_BASE_URL` elle güncellenmelidir.
- Aynı anda birden fazla belge yüklüyse ve konular örtüşüyorsa, özellikle genel/özet sorularında arama yanlış belgeden örnek getirebilir — tek belgeyle çalışmak önerilir (istenmeyen belgeyi "Sil" ile kaldırın).


