# 🤖 Kick AI Asistanı & Web Kontrol Paneli

Kick yayın platformu için özel olarak geliştirilmiş; **Google Gemini AI** destekli, mini oyunlar barındıran, yayıncılara özel gelişmiş bir **Web Dashboard (Kontrol Paneli)** ile yönetilen modern sohbet asistanı projesi.

Bu rehber, hiç kodlama bilmeseniz bile botu sıfırdan kurup kendi yayınınıza nasıl bağlayacağınızı adım adım ve olabilecek en detaylı şekilde anlatmaktadır.

---

## 🌟 Öne Çıkan Özellikler

- **💻 Gelişmiş Web Arayüzü:** Botu başlatmak/durdurmak, logları izlemek ve tüm ayarları değiştirmek için şık tasarımlı yerel web paneli.
- **🧠 Yapay Zeka (Gemini):** İzleyicilerin mesajlarını bağlamıyla (önceki konuşmalarla birlikte) anlayıp doğal ve eğlenceli yanıtlar üretir.
- **⚡ Tetikleyiciler (Events):** "sa", "selam" gibi günlük kelimelere ünlem işareti `!` olmadan anında belirlediğiniz yanıtları verebilirsiniz. 100'den fazla tetikleyiciyi arayüzdeki arama motoru ile yönetebilirsiniz.
- **🏆 Liderlik Tabloları:** Sohbetinizde en çok mesaj gönderenleri ve botun oyunlarından en çok puanı toplayanları altın taçlarıyla 👑 sıralar.
- **🎮 Mini Oyunlar:** Kelime bulmaca ve sayı tahmin oyunları.

---

## 🛠️ ADIM ADIM KURULUM REHBERİ

### Adım 1: Gerekli Programların Yüklenmesi
1. Bilgisayarınızda **Python 3.10+** kurulu olduğundan emin olun. (Kurarken *'Add Python to PATH'* kutucuğunu işaretlemeyi unutmayın!)
2. Bu projeyi bilgisayarınıza indirin (ZIP olarak indirip klasöre çıkarabilir veya `git clone` kullanabilirsiniz).

### Adım 2: Dosyaları Hazırlama
1. Proje klasörünü açın.
2. Klasörün içerisindeki boş bir yere **Sağ Tık -> Terminal'de Aç** (veya Komut İstemini bu klasörde açın).
3. Şu komutu yazıp *Enter*'a basarak botun ihtiyaç duyduğu kütüphaneleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```

### Adım 3: Kick API (Geliştirici) Anahtarlarını Alma
Botun Kick hesabınıza giriş yapıp yazı yazabilmesi için resmi geliştirici izni alması gerekir:

1. Tarayıcınızda Kick'e girin ve **Bot olarak kullanacağınız hesaba** giriş yapın (Kendi ana hesabınızı da kullanabilirsiniz ancak ayrı bir bot hesabı açmak tavsiye edilir).
2. Kick Dashboard üzerinden **Geliştirici (Developer)** sayfasına gidin (veya doğrudan [dev.kick.com](https://dev.kick.com) adresine girin).
3. **"Yeni Uygulama Oluştur" (Create Application)** butonuna basın.
4. Çıkan formu şu şekilde doldurun:
   - **App Name:** `Yayin_Asistanim` (veya istediğiniz bir isim)
   - **Redirect URI:** Burası çok önemli, kutuya tam olarak şunu yazın: `http://localhost:3000/callback`
5. İzinler (Scopes) bölümünde botun neler yapabileceğini seçeceksiniz. **"Chat"** sekmesi altındaki `chat:write` ve `chat:read` kutucuklarını mutlaka işaretleyin.
6. Uygulamayı oluşturduğunuzda size iki şifre verilecek:
   - **Client ID**
   - **Client Secret**
   *(Bu sayfayı kapatmayın, birazdan bu şifreleri panele yapıştıracağız)*

### Adım 4: Yapay Zeka (Gemini) Anahtarını Alma
1. [Google AI Studio](https://aistudio.google.com/app/apikey) adresine Google hesabınızla giriş yapın.
2. **"Create API Key"** butonuna basarak yeni bir anahtar (key) oluşturun ve kopyalayın.

---

## 🚀 WEB PANELİ ÜZERİNDEN BOTU AYARLAMA

Proje klasöründeki terminalinizde şu komutu çalıştırarak kontrol panelini başlatın:
```bash
python web_app.py
```
*(Konsolda `Running on http://127.0.0.1:5000` yazısını göreceksiniz)*

Tarayıcınızı açın ve **http://localhost:5000** adresine gidin. Karşınıza şık, koyu temalı Kontrol Paneli çıkacak!

### Ayarlar Sekmesi Nasıl Doldurulacak?
Sol menüden **"Ayarlar"** sekmesine tıklayın ve kutuları demin aldığımız bilgilerle doldurun:
- **Kanal Slug:** Yayın yaptığınız KENDİ hesabınızın kick sonundaki ismidir (Örn: `omerf`).
- **Bot Adı:** Bot için açtığınız hesabın görünen adı.
- **Gemini API Key:** 4. Adımda aldığınız Google AI şifresi.
- **Kick Client ID:** 3. Adımda aldığımız kısa Kick şifresi.
- **Kick Client Secret:** 3. Adımda aldığımız uzun Kick şifresi.
- **Kick Redirect URI:** Buraya dokunmayın (`http://localhost:3000/callback` kalmalı).

Bilgileri girdikten sonra **"Ayarları Kaydet"** butonuna basın.

---

## 🔑 İLK YETKİLENDİRME (Zorunlu!)

Botun sizin adınıza chat'e mesaj atabilmesi için bir defaya mahsus yetki vermeniz gerekiyor:
1. Proje klasöründe yeni bir terminal açın.
2. Şu komutu çalıştırın:
   ```bash
   python main.py --setup
   ```
3. Otomatik olarak tarayıcınız açılacak ve Kick size *"Bu bot hesabına erişim izni veriyor musunuz?"* diye soracak.
4. **"Authorize" (Onayla)** butonuna basın. Terminal ekranında *"Kurulum Tamamlandı"* yazısını göreceksiniz. (Bu sayede `kick_tokens.json` adlı gizli dosya oluşur).

---

## 🟢 KULLANIMA HAZIR!

Artık web paneline (`http://localhost:5000`) dönüp ana sayfadaki (Panel) **"Botu Başlat"** butonuna basabilirsiniz! Botunuz aktifleşecek ve yayınınızı dinlemeye başlayacaktır. Log ekranından olan biteni anlık takip edebilirsiniz.

**Arayüzün Diğer Özellikleri:**
- **Tetikleyiciler:** İstediğiniz kadar otomatik cevap ekleyebilirsiniz (Örn: `!youtube`, `sa`, `selam`). Mevcut olanları kalem ikonuyla düzenleyebilir, çöp kutusu ikonuyla silebilirsiniz.
- **Liderlik:** Yayın esnasında oluşan tüm etkileşim rekorlarını burada tablo halinde inceleyebilirsiniz.

---
*Geliştirici:* [OmerF-CS](https://github.com/OmerF-CS)
