# Kick AI Yayın Asistanı (Yapay Zeka Destekli Moderatör ve Eğlence Botu)

Bu proje, Kick.com yayıncıları için özel olarak geliştirilmiş, Google Gemini yapay zekası ile güçlendirilmiş tam kapsamlı bir yayın asistanıdır. Yalnızca basit komutlara yanıt veren standart botların aksine, **Kick AI Asistanı** sohbetteki konuşmaları anlar, kullanıcıları tanır, moderasyon işlemlerini doğal dille yapmanızı sağlar ve izleyicilerinizle tıpkı bir insan gibi etkileşime girer.

## 🌟 Temel Özellikler

### 🧠 Gelişmiş Yapay Zeka (Gemini 3.5 Flash Lite)
- **Bağlamsal İletişim:** Bot, sohbette dönen muhabbeti anlar. Kendisine veya yayına dair sorulan sorulara, yapılan esprilere ve sohbet akışına uygun mantıklı ve eğlenceli cevaplar üretir.
- **Hafıza Sistemi (Bellek):** Her izleyicinin daha önce ne yazdığını, kaç puanı olduğunu ve ne zaman geldiğini hafızasında (SQLite) tutar. Böylece sadık izleyicilerinizi tanır ve kişiselleştirilmiş cevaplar verir.
- **NLP Moderasyon (Doğal Dil İşleme):** Moderatörler, `!ban kullanici` yazmak yerine doğrudan bota dönüp _`"bot şu adamı 5 dakika sustur"`_ veya _`"bot küfredeni banla"`_ yazdığında, yapay zeka bu emri anlar ve işlemi otomatik olarak gerçekleştirir.

### 🛡️ Kapsamlı ve Akıllı Moderasyon
- **Otomatik Küfür ve Hakaret Filtresi:** Sistem sohbette geçen kötü kelimeleri algılar ve ilgili kullanıcıyı anında kısa süreli (timeout) olarak uzaklaştırarak uyarır.
- **Bota Yönelik Saldırı Koruması:** İzleyiciler doğrudan bota hakaret ettiğinde, bot onlara hazırcevap bir şekilde laf sokarak karşılık verir ve ardından kullanıcıyı otomatik olarak susturur (Yapay Zeka destekli).
- **Dost Ateşi (Friendly Fire) Koruması:** Bot; yayıncıyı ve kanal moderatörlerini asla banlamaz. Yanlışlıkla veya şaka amaçlı girilen moderasyon komutlarını reddeder.
- **Sessizlik Modu (Global Mute):** Çok yoğun sohbet akışlarında veya spoiler durumlarında sohbeti geçici olarak sadece moderatörlere açar.

### 🎮 Eğlence ve Etkileşim
- **Özel Karşılama:** İlk defa gelen izleyicilere normal bir karşılama, kanalın daimi izleyicilerine (VIP) ise çok daha samimi bir karşılama yapar.
- **Oyunlar:** İzleyicilerin puan kazanabileceği Kelime Oyunları ve Sayı Tahmin oyunları barındırır.
- **Liderlik Tablosu:** Sohbette en çok mesaj yazanları ve oyunlardan en çok puan toplayanları listeleyerek kanal içi rekabeti artırır.
- **Sessizlik Kırıcı (Silence Breaker):** Yayında uzun süre sessizlik olduğunda (örneğin 3 dakika boyunca kimse yazmadığında), bot kendiliğinden sohbete ilginç bir tartışma sorusu atarak etkileşimi canlandırır.

### 🖥️ Modern Kontrol Paneli (Web UI)
- Siyah tema, kolay kullanılabilir arayüzü ile botu tek tıkla başlatıp durdurabilirsiniz.
- Gelen mesajları canlı log ekranından takip edebilir, `!komut` listesine kolayca yeni anahtar kelimeler ekleyebilirsiniz.
- Tüm liderlik tablolarını panel üzerinden görsel olarak inceleyebilirsiniz.

---

## ⚙️ Kurulum ve Başlangıç

Bu projeyi kendi bilgisayarınızda çalıştırmak oldukça basittir.

### 1. Gereksinimler
- **Python 3.10+** yüklü olmalıdır.
- Proje dosyalarını indirin veya Git üzerinden klonlayın.

### 2. Kütüphanelerin Yüklenmesi
Komut satırını (Terminal / CMD) açın ve proje klasörüne giderek gerekli paketleri kurun:
```bash
pip install -r requirements.txt
```

### 3. Yapılandırma (Ayarlar)
Proje klasörünün içinde bulunan `.env.example` dosyasının adını `.env` olarak değiştirin (veya yeni bir `.env` dosyası oluşturup içindekileri kopyalayın). Bu dosyayı bir metin editörüyle açıp kendi bilgilerinizi girin:

- `GEMINI_API_KEY`: Google AI Studio üzerinden tamamen **ücretsiz** olarak alacağınız yapay zeka API anahtarı.
- `KICK_CHANNEL_SLUG`: Yayın yaptığınız kanalın linkteki adıdır (Örn: `kick.com/benimkanalim` ise `benimkanalim` yazılır).
- `BOT_NAME`: Botunuzun Kick platformundaki kullanıcı adı.
- _(Opsiyonel)_ `KICK_CLIENT_ID` & `SECRET`: Kick Developer Portalı'ndan alınacak mesaj gönderme yetkileri.

### 4. Çalıştırma
Windows kullanıcıları için doğrudan `Baslat.bat` dosyasına tıklayarak veya terminal üzerinden aşağıdaki komutla kontrol panelini başlatabilirsiniz:
```bash
python web_app.py
```

Karşınıza çıkan arayüzde **Başlat** tuşuna basarak yapay zeka asistanınızı Kick kanalınıza hemen bağlayabilirsiniz.

---

## 🤝 Katkıda Bulunma
Bu proje açık kaynaktır. Hata bildirimleri, yeni özellik talepleri ve Pull Request (PR) gönderimleri memnuniyetle karşılanmaktadır.

## 📝 Lisans
Bu proje MIT lisansı altında yayınlanmıştır. Dilediğiniz gibi kullanabilir ve geliştirebilirsiniz.
