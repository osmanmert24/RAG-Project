# Sunum Notları — Foundry Local RAG

Bu dosya video anlatımı için hazırlandı: projeyi kısaca tanıtıp, geliştirme sürecinde karşılaşılan gerçek sorunları ve bunları nasıl çözdüğümüzü basit dille anlatır. Ayrıntılı, ölçümlü versiyon için `LEARNING.md`.

---

## 1. Proje nedir

İnternete hiç bağlanmadan çalışan bir soru-cevap uygulaması. İki modu var:

- **Genel sohbet:** "Fransa'nın başkenti nedir?" gibi sorularda model kendi bilgisiyle cevap verir.
- **Belge modu:** Bir PDF yüklendiğinde, o belgeyle ilgili sorularda cevabı **yalnızca belgenin içeriğinden** üretir ve hangi sayfadan aldığını gösterir.

Kullanılan araçlar: Microsoft'un **Foundry Local**'i (modeli bilgisayarda çalıştırıyor, veri hiç dışarı çıkmıyor), sohbet için **Phi-4-mini**, belge aramak için bir **embedding modeli** (Qwen3-Embedding) ve chunk'ları saklayan **ChromaDB**.

## 2. Mimari, kısaca

```
Tarayıcı (Next.js) → Backend (FastAPI) → Foundry Local (Phi-4-mini + embedding)
                                        → ChromaDB (belge parçaları)
```

Bir PDF yüklendiğinde: metni çıkarıyoruz → küçük parçalara (chunk) bölüyoruz → her parçayı bir vektöre (embedding) çeviriyoruz → ChromaDB'ye kaydediyoruz. Soru sorulduğunda: soruyu da vektöre çevirip en yakın parçaları buluyoruz, onları modele "işte context, buna göre cevap ver" diye veriyoruz.

Kulağa basit geliyor — ama küçük bir modelle (3.8 milyar parametre) bunu **güvenilir** çalıştırmak asıl zor kısım oldu. Aşağıda karşılaştığımız gerçek sorunlar ve çözümleri var.

---

## 3. Karşılaşılan sorunlar ve çözümleri

### Sorun 1: Embedding modeli hiçbir yerde bulunamıyor gibi görünüyordu

Foundry Local normalde OpenAI ile aynı formatta bir REST API sunuyor (`/v1/embeddings`). Ama bu endpoint'e istek attığımızda **500 hatası** alıyorduk — model "yok" gibiydi.

**Gerçek sebep:** Foundry Local'ın iki ayrı kataloğu var. CLI'nin ve REST servisinin gösterdiği katalogda embedding modeli hiç yok; ama SDK'nın kendi "native" katmanında (`foundry-local-sdk` paketi) var. Yani model gerçekten kuruluydu, sadece yanlış kapıdan soruyorduk.

**Çözüm:** Sohbet için REST API'yi (OpenAI uyumlu), embedding için ise SDK'nın native yolunu kullanıyoruz — ikisi aynı Foundry Local'e farklı iki "kapıdan" bağlanıyor.

### Sorun 2: Model bazen aynı cümleyi/kelimeyi sonsuza kadar tekrarlıyordu

"Fransa'nın başkenti neresidir?" gibi basit bir soruda model doğru cevaba başlıyor, sonra aynı kelime grubunu (bazen hiç noktalama koymadan) onlarca kez art arda üretip 50-80 saniye sürüyordu.

**Neden oluyor:** Küçük, quantize edilmiş (sıkıştırılmış) modellerde bilinen bir davranış — üretim bir kelime kalıbına "takılıp" çıkamıyor.

**Çözüm:** Modelin ürettiği metni gerçek zamanlı izleyip, aynı kelime öbeği art arda tekrar etmeye başladığı anda üretimi kendimiz durduruyoruz. Bu, modeli "düzeltmiyor", sadece bozulduğu anı yakalayıp kesiyor — hem cevap kalitesi hem hız (80 saniyeden ~6 saniyeye) iyileşti.

### Sorun 3: PDF'ten çıkan metin, görünmez karakterlerle doluydu

Bazı PDF'lerin iç kodlaması yüzünden, sayfadan metni çıkardığımızda kelimelerin arasına gözle görünmeyen karakterler (tab, satır başı, özel boşluk) karışıyordu — `"accomplish[görünmez karakterler]this[görünmez karakterler]transition"` gibi. Bu çöp, modele context olarak gidiyordu.

**Çözüm:** PDF'ten metin çıkarılırken bu görünmez karakterleri temizleyen bir adım eklendi. Temizlik sonrası hem arama skorları yükseldi hem de modelin ürettiği cevaplar daha tutarlı hale geldi — küçük bir modelin kirli girdiyle başa çıkma toleransı düşük.

### Sorun 4: Farklı dildeki bir belgede sistem "bulamadım" diyordu

Belge İngilizce, soru Türkçeyse, sistem sık sık "belgede bu bilgi yok" diyordu — halbuki bilgi gerçekten belgede vardı.

**Neden oluyor:** Arama, soru ile belge parçaları arasındaki "anlamsal benzerlik skorunu" ölçüyor ve bir eşiğin üstündeyse "bu parça alakalı" kabul ediyor. Bu eşik, aynı dildeki (Türkçe-Türkçe) örneklerle ayarlanmıştı. Farklı dilde belgede bu benzerlik skoru yapısal olarak daha düşük çıkıyor, eşiğin altında kalıp reddediliyordu.

**Çözüm:** Eşiği, hem aynı dilli hem farklı dilli örnekleri kapsayacak şekilde yeniden ölçüp ayarladık.

### Sorun 5: Model "bulamadım" cümlesini bazen tam söylemiyordu

Belgede olmayan bir şey sorulduğunda modelden belirli, sabit bir Türkçe cümle söylemesini istiyorduk. Ama küçük model bu cümleyi bazen **birebir** değil, anlamca yakın ama farklı kelimelerle söylüyordu — bazen de bunun yerine uzun, alakasız bir açıklama yazıyordu.

**Çözüm:** Modelden artık uzun bir cümle değil, tek bir sabit kod kelimesi istiyoruz ("bilgi yok" anlamına gelen özel bir işaret kelime). Model bu kelimeyi ürettiğinde, kullanıcıya modelin kendi cümlesini değil, **bizim kontrol ettiğimiz, sabit ve garanti** bir cevabı gösteriyoruz. Küçük modeller tek bir sabit kelimeyi üretmekte, uzun bir cümleyi harfiyen tekrarlamaktan çok daha güvenilir.

### Sorun 6: "Bu belge ne hakkında?" gibi genel sorularda sistem çuvallıyordu

Belgeyle ilgili çok spesifik sorularda ("izin kaç gün?" gibi) sistem iyi çalışıyordu. Ama "bu belgede ne anlatılıyor?" gibi genel/özet sorularında ya "bulamadım" diyordu ya da alakasız bir parçayı getiriyordu.

**Neden oluyor:** Arama sistemi, soruya **en çok benzeyen tek bir parçayı** buluyor. Ama "bu belge ne hakkında" sorusunun tek bir parçaya "benzemesi" diye bir şey yok — bu soru bütün belgeyi kapsıyor, tek bir cümleyi değil.

**Çözüm:** Bu tip genel soruları ayrı bir kategori olarak tanıyoruz. Böyle bir soru geldiğinde, en çok benzeyen tek parçayı aramak yerine **belgenin her sayfasından bir örnek** alıp modele veriyoruz ve ondan bir özet çıkarmasını istiyoruz — "en çok benzeyeni bul" yerine "genele bak" mantığına geçiyoruz.

---

## 4. Sonuç

Bu sorunların ortak noktası: hiçbiri "kod bozuk" değildi, hepsi küçük bir dil modelinin (Phi-4-mini, 3.8 milyar parametre) ve embedding aramasının **gerçek, ölçülebilir sınırlarıydı**. Çözüm her seferinde modele daha fazla yük bindirmek değil, uygulama katmanında modelin zayıf olduğu yeri tespit edip etrafından dolaşacak, deterministik (garanti çalışan) küçük mekanizmalar kurmaktı — tekrar tespiti, sabit kod kelimesi, soru tipine göre farklı arama stratejisi gibi.

Sonuçta sistem hem genel sohbeti hem gerçek PDF belgelerinden kaynaklı soru-cevabı, tamamen internetsiz, tek bir yerel makinede çalıştırabiliyor.
