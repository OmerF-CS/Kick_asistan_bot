# Kick AI Asistanı (Kick Chat Bot)

Bu proje, Kick yayın platformu için geliştirilmiş, yapay zeka (Gemini API) destekli gelişmiş bir sohbet asistanıdır. Yayıncıların sohbetini izler, izleyicilerle etkileşime geçer, oyunlar oynatır ve sohbet bağlamını hafızasında tutarak doğal bir konuşma deneyimi sunar.

## Özellikler

- **Yapay Zeka Destekli Beyin (AIBrain):** Google Gemini API kullanarak sohbeti anlar ve mantıklı, doğal cevaplar üretir.
- **Canlı Sohbet Dinleyicisi (Kick Listener):** Kick sohbetindeki mesajları gerçek zamanlı olarak dinler.
- **Hafıza ve Bağlam Yönetimi:** Sohbetin geçmişini ve kullanıcılarla olan etkileşimlerini hatırlar.
- **Mini Oyunlar (Games Engine):** İzleyicilerin sohbet üzerinden oynayabileceği oyunları barındırır.
- **Veritabanı Entegrasyonu:** Kullanıcı bilgilerini ve botun hafızasını SQLite/JSON veritabanında saklar.

## Kurulum

1. **Gereksinimleri Yükleyin:**
   Kullanılan Python kütüphanelerini yüklemek için terminalinizde şu komutu çalıştırın:
   ```bash
   pip install -r requirements.txt
   ```

2. **Ortam Değişkenlerini Ayarlayın:**
   Proje dizininde `.env` adında bir dosya oluşturun ve içine gerekli API anahtarlarını ve bilgilerinizi ekleyin (Örnek olarak):
   ```env
   GEMINI_API_KEY=senin_gemini_api_anahtarin
   KICK_CHANNEL_SLUG=yayin_yapilan_kanalin_adi
   BOT_NAME=KickAsistan
   KICK_CLIENT_ID=senin_kick_client_id
   KICK_CLIENT_SECRET=senin_kick_client_secret
   KICK_REDIRECT_URI=http://localhost:3000/callback
   BOT_COOLDOWN=3
   ```

## Kullanım

Uygulamayı başlatmak için ana dosyayı çalıştırmanız yeterlidir:

```bash
python main.py
```

- Sadece AI modülünü test etmek isterseniz: `python main.py --test-ai`
- Kick OAuth kurulumu yapmak için: `python main.py --setup`

## Dosya Yapısı

- `main.py`: Projenin ana dosyasıdır (Orkestra Şefi). Beyin ve Kulak modüllerini birbirine bağlar.
- `ai_brain.py`: Gemini yapay zekasıyla iletişim kurup cevapları üreten modül.
- `kick_listener.py`: Kick sohbetine bağlanıp mesajları okuyan ve gönderen sistem.
- `database.py`: Kullanıcı verileri, vip listesi ve oyun verileri için veritabanı işlemleri.
- `games.py`: Chat üzerinden oynanabilecek mini oyunların bulunduğu modül.
- `memory.py`: Yapay zekanın sohbet geçmişini hatırlamasını sağlayan hafıza modülü.

## Katkıda Bulunma

Bu projeye katkıda bulunmak isterseniz lütfen bir Pull Request (PR) açmaktan çekinmeyin!
