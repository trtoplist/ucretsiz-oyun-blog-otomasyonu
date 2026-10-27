# Ücretsiz Oyun Blogu Otomasyonu (Türkçe)

Bu paket, `freesteamkeyalma.blogspot.com` için günde iki kez oyun fırsatlarını kontrol eder, doğrulanabilen yeni teklifleri Türkçe Blogger **taslağı** olarak hazırlar ve iş akışı özetini GitHub Actions ekranında gösterir. Hiçbir taslak otomatik yayımlanmaz.

## Maliyet ve gizlilik

- Zamanlama GitHub Actions ile yapılır. Depo herkese açık olursa kaynak kodu ve iş akışı herkesçe görülebilir.
- Google şifresi, OAuth istemci sırrı ve yenileme belirteci kaynak koduna konmaz. GitHub Actions Secrets içinde saklanır. Secret'lar çalışma sırasında iş akışına verilir; dışarıya sızdırılmamaları için loglara basılmaz.
- Herkese açık depoda Actions ücretsiz kullanımı mevcut plan/koşullara tabidir. GitHub zamanlaması kesin saat garantisi vermez.
- GamerPower API ücretsizdir ve GamerPower'a atıf ister. Liste her mağaza için eksiksiz veya resmî doğrulama garantili değildir.
- E-posta gönderimi bu ilk pakete dahil değildir; GitHub Actions çalıştırma özeti bildirim/inceleme noktasıdır.

## Bu sürümün sınırları

GamerPower aktif kampanya/çekiliş toplayıcısıdır; tüm abonelik kataloglarını (Game Pass, PlayStation Plus, Prime Gaming gibi), süresiz ücretsiz oyunları veya her mağazadaki ücretsiz hafta sonlarını eksiksiz sunmaz. API kaydında açıkça bulunan koşul ve bitiş tarihi yazıda kullanılır. Kaynakta bulunmayan abonelik şartı tahmin edilmez. Bu nedenle abonelik teklifi olduğu güvenilir veride açıkça doğrulanamıyorsa otomatik taslak oluşturulmaz; çalıştırma raporunda incelemeye bırakılır.

Bu güvenlik sınırı önemlidir: son kullanıcıya "ücretsiz" diye sunulacak erişimin ücretli üyelik, süreli deneme, bölge, platform veya tarih koşulu olabilir. Sistem yalnızca veri kaynağının açıkça bildirdiği şartları yazar; mağaza sayfasından doğrulama gerektiren teklifleri otomatik yayıma hazır içerik saymaz. Görsellerde kaynağın sağladığı oyun kapak görseli kullanılır; mağaza görselinin kullanım hakkı ve Blogger'da yüklenmesi otomatik olarak garanti edilmez. Taslak içindeki görsel kaynağı atıfla gösterilir.

## Kurulum özeti

1. Bu klasörün içeriğini GitHub'da **public** bir depoya yükle. `data/seen.json` dosyası deduplikasyon için takip edilir.
2. Depo → **Settings → Secrets and variables → Actions → New repository secret** bölümünden aşağıdakileri ekle:
   - `BLOGGER_BLOG_ID`: Blogger API blog kimliği.
   - `GOOGLE_CLIENT_ID`: Google OAuth Desktop uygulamasının istemci kimliği.
   - `GOOGLE_CLIENT_SECRET`: OAuth istemci sırrı (varsa; Desktop istemcilerde her zaman sır sayılmaz).
   - `GOOGLE_REFRESH_TOKEN`: Blogger izni verilerek yerelde üretilen yenileme belirteci.
3. Google Cloud Console'da Blogger API v3'ü etkinleştir ve OAuth istemcisini kur. `scripts/oauth_setup.py` yalnızca yerel bilgisayarında çalışır, tarayıcıda Google iznini açar ve refresh token değerini terminalde verir. Bu değeri GitHub Secret olarak kaydet; sohbete veya repoya yapıştırma.
4. Google OAuth izin ekranı **Testing** durumundaysa Blogger kapsamı içeren yenileme belirteci yedi gün sonra sona erebilir. Düzenli çalışması için OAuth uygulamasını uygun yayın durumuna alman gerekebilir; Google doğrulama gereklilikleri ve kullanımına uygulanabilir koşulları kontrol et. Bu paket OAuth doğrulamasını senin adına tamamlayamaz.
5. `config.json` içindeki ayarları düzenle: blog adresi, bildirim e-posta adresi (`trtoplist@gmail.com`), saat dilimi ve mağaza filtreleri.
6. Actions sekmesinden **Ücretsiz oyunları kontrol et** iş akışını elle çalıştırıp ilk denemeyi gözle. Varsayılan çalışma günde iki kez Türkiye saatiyle 10:00 ve 22:00 civarıdır; GitHub gecikme yapabilir.

## OAuth belirteci üretme

Yerel bilgisayarında Python 3.11+ kurulu olmalı. Google Cloud Console'dan OAuth Client ID türü **Desktop app** oluşturup Blogger API'yi etkinleştir. Sonra PowerShell'de:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GOOGLE_CLIENT_ID="..."
$env:GOOGLE_CLIENT_SECRET="..."
python scripts/oauth_setup.py
```

Tarayıcıda blogu yönetme iznini ver. Komutun ürettiği belirteci GitHub Secret'a gir. Token dosyası/JSON çıktısı üretme ve repoya ekleme.

## E-posta bildirimi

Bu paket yalnızca GitHub Actions çalışma özetini üretir; `trtoplist@gmail.com` adresine doğrudan e-posta göndermez. GitHub e-posta bildirimleri depo/Actions ayarlarına ve hesabının bildirim tercihine bağlıdır; her yeni oyun için e-posta garantisi vermez. Sıfır maliyet şartı nedeniyle haricî e-posta sağlayıcısı ve onun erişim bilgileri bu sürüme eklenmemiştir.

## Kontroller

Sistem `data/seen.json` içinde teklif kimliklerini/URL'lerini saklar; aynı teklifi ikinci kez taslak yapmaz. Kampanyası bitmiş, bitişi geçmiş veya bağlantısı güvenli HTTP(S) olmayan kayıtları eler. Süreli tekliflerde bitiş bilgisini yazar. Süresiz/kalıcı ücretsiz olduğuna dair veri kaynağından açık kanıt bulunmuyorsa süresiz olduğunu iddia etmez. Blogger API'ye `isDraft=true` ile gönderir ve otomatik yayımlama yapmaz.

## Mağaza kapsamı

Kaynak adaptörü şu anda GamerPower API'den Steam, Epic Games Store, GOG, itch.io, PlayStation, Xbox ve PC platformları için **API'de listelenmiş etkin giveaway/teklifleri** alır. GamerPower belgelerinde Ubisoft Connect, EA app, Prime Gaming, Humble Bundle, Fanatical ve abonelik katalogları yer almıyor. Ayrıca Steam free weekend/süresiz ücretsiz kataloglarının kapsandığı garanti edilmez. Kaynak API'nin sağlayamadığı mağaza kapsamı tahmin edilmez.

## Lisans ve atıf

Kendi kodun MIT lisanslıdır. GamerPower verisinden oluşturulan içeriklerde [GamerPower](https://www.gamerpower.com/) kaynağına görünür bağlantı bulunur. Mağazaların marka/görsel hakları ilgili sahiplerine aittir.

