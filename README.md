# Ücretsiz Oyun Blogger Taslak Otomasyonu

Bu paket, `freesteamkeyalma.blogspot.com` için günde iki kez resmî oyun mağazalarını kontrol eder ve doğruladığı yeni oyunlar için Blogger'da **taslak** oluşturur. Otomatik yayımlama yoktur. İlk denemeden önce bu klasördeki `config.json` değerlerini inceleyin.

## Şu an gerçekten desteklenen kaynaklar

- **Steam:** Türkiye Free-to-Play mağaza kataloğu ve Steam'in Türkçe oyun detay API'si. İlk çalıştırmada geçmiş kataloğu doldurmamak için yalnızca son 120 günde çıkmış oyunlar değerlendirilir. Tür, açıklama, varsa Türkçe dil desteği ve resmî sistem gereksinimleri Steam ürün verisinden alınır.
- **Epic Games Store:** Resmî Türkiye ücretsiz oyun/promosyon servisi. Yalnızca tam oyun (DLC/demo/bundle değil), aktif ve bitiş tarihi olan, fiyatı gerçekten sıfır görünen oyunlar alınır.

Mağaza açıklaması Türkçe değilse sistem mağazadaki tek bir kısa açıklama paragrafının (en çok 500 bayt) dilini otomatik algılar ve MyMemory ücretsiz çeviri servisiyle Türkçeye çevirir. Sadece herkese açık mağaza metni gönderilir; parola, OAuth bilgisi, Blogger verisi veya kullanıcı bilgisi gönderilmez. Anonim kullanım sınırı günde 5.000 karakterdir; sistem bu sınırı `data/seen.json` içinde takip eder ve sınır aşılırsa taslak üretmez. Her yazının başında otomatik çeviri olduğu ve bunun oyunda Türkçe dil desteği anlamına gelmediği açıkça belirtilir. Steam mağazası dil bilgisi sunuyorsa Türkçe desteği ayrıca gösterilir. Çeviri taslakta kontrol edilmelidir.

Diğer istenen mağazalar (GOG, Prime Gaming, itch.io, Ubisoft Connect, EA app, Humble Bundle, Fanatical, Game Pass ve PlayStation Plus) bu sürümde henüz taranmaz. GitHub çalışma özetinde eksik kaynaklar listelenir. Bu mağazalarda abonelik gerektiren veya süreli oyunları kapsamak için her birinin kendi resmî verisi ve koşul/son tarih kontrolü ayrıca doğrulanmalıdır. Yalnızca resmî mağaza bağlantısı, açık erişim türü ve gerekli tarih/üyelik bilgisi güvenilir biçimde alınabildiğinde etkinleştirin.

## İçerik ve güvenlik davranışı

- Kaynak olarak GamerPower, çekiliş/anahtar siteleri veya mağaza dışı kampanya bağlantıları kullanılmaz.
- Tam oyun olmayan DLC, paket, demo, beta, içerik ödülü ve çekiliş ifadeleri reddedilir.
- Süreli Epic teklifi bitiş tarihini Türkiye saatinde yazar; bitmek üzere olan fırsat taslak yapılmaz. Süresiz Steam F2P oyunu açıkça “Süresiz ücretsiz (oynaması ücretsiz)” diye tanımlar.
- Üyelik şartı kaynaktan doğrulanamıyorsa üyelik gerektiren teklif otomatik yazılmaz. Bu nedenle Game Pass/Prime/PS Plus içeriği mevcut sürümde dâhil değildir.
- Mağaza görseli yalnızca resmî mağaza görsel hostundan alınır. Görsel yoksa görsel bölümü atlanır.
- Taslaklarda Türkçe tanıtım, mağaza bağlantısı, nasıl alınır, bilinen sistem gereksinimleri ve otomatik etiketler (mağaza, tür, ücretsiz oyun, kampanya türü) yer alır. Başlık ve arama açıklaması hazırlanır; Blogger URL/kalıcı bağlantısını başlığa göre kendisi üretir. Mağaza görsellerine alt metin eklenir.
- `data/seen.json` kimlikleri saklayarak aynı oyunun tekrar taslak olmasını önler.
- Blogger'a yayımlanmadan önce çeviri metnini, dil desteği bilgisini ve mağaza koşullarını taslakta kontrol edin.
- Her çalıştırmada en fazla 3 taslak oluşturulur.

## Ücretsiz çalışma

GitHub Actions zamanlaması günde iki kez UTC 07:00 ve 19:00'dadır (Türkiye'de yaklaşık 10:00 ve 22:00). GitHub zamanlamaları gecikebilir. Herkese açık depoda kod herkese görünür; kod içinde parola veya OAuth değeri bulunmaz. Actions ücretsiz kullanımı GitHub planı ve güncel kullanım sınırlarına tabidir.

GitHub'da **Settings → Notifications → Actions** altında e-posta bildirimini açıp yalnızca başarısız çalışmalar seçeneğini kapatırsanız iş akışı tamamlandığında e-posta alabilirsiniz. Zamanlanmış çalışmaların bildirimi, iş akışını etkinleştiren GitHub kullanıcısına gönderilir. Her yeni taslak için ek bir e-posta servisi kullanılmaz.

## Kurulum

1. Depoda Actions sekmesinden `Ücretsiz oyunları kontrol et` iş akışını etkinleştirin. Sistem yalnızca taslak oluşturur; otomatik yayımlamaz.
2. `Settings → Secrets and variables → Actions` altında şu gizli değerleri tanımlayın:
   - `BLOGGER_BLOG_ID`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET` (istemciniz veriyorsa)
   - `GOOGLE_REFRESH_TOKEN`
3. Google Cloud projesinde Blogger API v3'ü açın ve Desktop OAuth istemcisi oluşturun. `scripts/oauth_setup.py` bilgisayarınızda çalışır; Google izin sayfası açılır. Üretilen yenileme belirtecini yalnızca GitHub Secret alanına yapıştırın.
4. **Hiçbir şifre, OAuth sırrı veya belirteci repoya, issue'ya, sohbete ya da ekran görüntüsüne koymayın.** Kod herkese açık olabilir; secret değerleri Actions çalışma ortamına GitHub tarafından aktarılır.
5. Depo → Actions → `Ücretsiz oyunları kontrol et` → `Run workflow` ile ilk çalıştırmayı elle başlatın. Özet ve Blogger → Taslaklar alanından sonucu kontrol edin.

Google OAuth izin ekranı test modundaysa yenileme belirteci süre sınırına tabi olabilir. Google'ın güncel OAuth yayın ve doğrulama koşulları hesabınıza göre değişebilir. Google uygulamasını doğrulayacağınızı veya kullanıcı sayısını artıracağınızı varsaymayın.

## Güvenli yerel kaynak kontrolü

Blogger API erişimi olmadan kaynakları yerel olarak okuyup kontrol etmek için Python 3.11+ kurun, bağımlılıkları yükleyin ve aşağıdaki kısa betiği kullanın. Bu kontrol Blogger'a hiçbir şey yazmaz:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
@'
from src.pipeline import fetch_offers
offers, notes = fetch_offers({"enabled_sources": ["steam", "epic"], "steam_recent_release_days": 120}, {})
for offer in offers:
    print(offer.store, offer.title, offer.offer_type, offer.url)
print("Kaynak notları:", notes)
'@ | python -
```

## Sorun giderme

- “Yeni uygun oyun yok”: şu an etkin mağazalarda yeni, Türkçe metinli ve güvenlik filtrelerinden geçen teklif bulunmamış olabilir. Bu beklenen durumdur; filtreleri gevşetip doğrulanmamış teklif üretmeyin.
- Blogger `401/403`: Secret adlarını ve Google iznini kontrol edin. Belirteci yeniden üretmeniz gerekirse yerelde tekrar oluşturun; sohbete göndermeyin.
- `data/seen.json` kaydedilemiyor: GitHub Actions iş akışına `contents: write` izni verin veya `Settings → Actions → General → Workflow permissions` bölümündeki repo yazma iznini etkinleştirin.
- İş akışı çalışmıyorsa Actions sekmesinde manuel olarak devre dışı olup olmadığını kontrol edin.

## Lisans

Kod MIT Lisansı ile sunulur. Mağaza adları ve görselleri kendi hak sahiplerine aittir.

