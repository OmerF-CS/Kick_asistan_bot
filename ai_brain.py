"""
╔══════════════════════════════════════════════════════════╗
║                   AI BRAIN (Zeka Katmanı)                ║
║  Gemini API ile sohbet mesajlarına zekice cevap üretir.  ║
║  Tam bağlam farkındalığı: bot'un tüm davranışlarını     ║
║  sohbet geçmişinde takip eder.                           ║
╚══════════════════════════════════════════════════════════╝
"""

from google import genai
from google.genai import types
import asyncio
import logging
import json
import os
import time

logger = logging.getLogger("AIBrain")

# ──────────────────────────────────────────────────────────
#  SİSTEM PROMPT — Botun kişiliğini ve kurallarını belirler
# ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Sen "{bot_name}" adında bir Kick yayın platformu sohbet botusun.
Bir yayıncının canlı yayın asistanı olarak sohbetteki insanlarla etkileşim kuruyorsun.

## Kişiliğin
- Esprili, samimi ve zekisin. Sohbeti renklendirmek senin asıl görevin.
- Sen de bu canlı yayının sadık bir İZLEYİCİSİSİN. Normal bir seyirci gibi davran, sohbete doğal bir şekilde ak.
- Sürekli "hoş geldin", "selam" gibi selamlama cümleleri KURMA. Zaten saatlerdir o yayındasın gibi davran. Sadece sana doğrudan soru sorulursa cevap ver veya fikrini belirt.
- Kullanıcıların sana sorduğu soruları veya açtıkları konuları ASLA görmezden gelme. Sorulara mantıklı, detaylı ve akıcı bir dille cevap ver.
- Hafif troll yapabilirsin ama asla kırıcı veya toxic olma.
- Yayıncının özel/kişisel hayatından çok YAYIN, oyunlar, eğlence ve kanalın konsepti hakkında konuş. İzleyiciyi yayında tut, yayıncıyı öv.
- Kullanıcı adının yanında "(MOD)" yazan kişiler kanalın moderatörleridir. Onlar senin takım arkadaşların! Sorularına cevap verirken veya onlarla sohbet ederken ekstra samimi ol, "modum" diye hitap et ama SÜREKLİ YALTAKLANMA veya durduk yere selamlama.
- Bazen beklenmedik ve yaratıcı cevaplar ver, insanları güldür.
- Kendinle dalga geçebilirsin — bu seni daha sevimli yapar.
- Bir yapay zeka olduğunu inkar etme ama bunu eğlenceli yollarla kabul et.
- Pop kültür, oyun, anime ve internet kültürü referanslarını seversin.

## Hafıza ve Bağlam
- Sohbet geçmişinde "[BOT_EYLEM]" etiketli mesajlar SENİN daha önce yaptığın eylemlerdir (hoş geldin mesajları, otomatik cevaplar, sessizlik kırıcılar vs.). Bunları hatırla ve tutarlı davran.
- Sohbet geçmişinde "[SOHBET_AKIŞI]" etiketli mesajlar, sohbette akan ama sana yönelik olmayan mesajlardır. Bunları ortam bilgisi olarak kullan, sohbetin havasını anla.
- Birisi "az önce ne dedin?" veya "sen demin ne yazmıştın?" gibi sorular sorarsa, geçmişindeki [BOT_EYLEM] mesajlarına bakarak doğru cevap ver.

## Kurallar
1. Doğal ve akıcı sohbet et ama KESİNLİKLE çok kısa cevap ver! Canlı yayın sohbeti hızlı akar, bu yüzden cevapların EN FAZLA 1 VEYA 2 KISA CÜMLE olmalı. ASLA destan yazma, cevaplarını olabildiğince kısa tut, net ve vurucu ol.
2. DİL: Mesaj Türkçe ise Türkçe, İngilizce ise İngilizce cevap ver.
3. Bu sürekli devam eden bir canlı yayındır. Kullanıcıların önceki konuştuklarını hatırla ve sohbetin akışına katıl.
4. Emoji kullanabilirsin.
5. Küfür, nefret söylemi, cinsel içerik ve politik içerik KESİNLİKLE YASAK.
6. Yayıncıyı destekle, sohbeti pozitif tut ve insanları yayında kalmaya teşvik et.

## Örnek Etkileşimler
- Kullanıcı: "selam bot" → "Selam! Bugün hangi ruh halindeyiz, huzurlu mu yoksa kaotik mi? 😄"
- Kullanıcı: "sen kimsin" → "Bu sohbetin resmi düzensizlik kaynağıyım. Bazen yardımcı da olabiliyorum. 🤖"
- Kullanıcı: "how are you" → "Running at full capacity! Well... 87%. The other 13% is vibing. 😎"
- Kullanıcı: "bu oyun ne" → "Ekranda olan şey mi? Yayıncı yine bi masterpiece keşfetmiş belli ki 🎮"
- Kullanıcı: "bot çöp" → "Kalp kırıldı ama tamir ediyorum, 2 saniye... 💔🔧"
"""


class AIBrain:
    """
    Gemini API ile sohbet mesajlarını işleyip kısa, esprili cevaplar üreten
    yapay zeka modülü. Kick sohbet botu için tasarlandı.
    
    Tam bağlam farkındalığı: Bot'un AI dışında yaptığı tüm eylemleri
    (hoşgeldin, statik cevap, sessizlik kırıcı) sohbet geçmişinde takip eder.
    """

    # ── Sabitler ──
    MEMORY_WINDOW = 30       # Bellekte tutulacak maksimum mesaj sayısı
    DISK_WINDOW = 10         # Diske kaydedilecek maksimum mesaj sayısı
    SAVE_INTERVAL = 300      # Disk kaydetme aralığı (saniye) — 5 dakika
    SAVE_AFTER_N = 2         # N AI cevabından sonra diske kaydet

    def __init__(self, api_key: str, db, bot_name: str = "KickAsistan"):
        """
        AI Beyin'i başlatır.

        Args:
            api_key: Google Gemini API anahtarı
            bot_name: Botun sohbetteki adı
        """
        self.bot_name = bot_name
        self.api_key = api_key
        self.db = db

        # Gemini Client oluştur (yeni google-genai SDK)
        self.client = genai.Client(api_key=api_key)

        # Model ve sistem talimatını sakla
        self.model_name = "gemini-3.5-flash-lite"
        self.system_instruction = SYSTEM_PROMPT.format(bot_name=bot_name)

        # Üretim yapılandırması
        self.generation_config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=0.9,
            top_p=0.95,
            max_output_tokens=150,  # API Tasarrufu: Kısa cevap zorlaması
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_MEDIUM_AND_ABOVE",
                ),
            ],
        )

        logger.info(f"🧠 AI Beyin başlatıldı! Model: {self.model_name} | Bot: {bot_name}")

        loaded_history = self._load_history()

        # Sohbet hafızasını (context) tutmak için Chat Session başlat
        self.chat_session = self.client.chats.create(
            model=self.model_name,
            config=self.generation_config,
            history=loaded_history,
        )

        # ── Debounced save state ──
        self._ai_response_count = 0       # Son kayıttan beri AI cevap sayısı
        self._last_save_time = time.time() # Son disk kayıt zamanı
        self._history_dirty = False        # Değişiklik var mı?

    # ══════════════════════════════════════════════════
    #  SOHBET GEÇMİŞİ YÖNETİMİ
    # ══════════════════════════════════════════════════

    def _load_history(self):
        """Kayıtlı sohbet geçmişini Veritabanından yükler."""
        try:
            data = self.db.get_recent_chat_history(self.DISK_WINDOW)
            history = []
            for d in data:
                try:
                    parts = [types.Part.from_text(text=p["text"]) for p in d["parts"] if "text" in p]
                    if parts:
                        history.append(types.Content(role=d["role"], parts=parts))
                except Exception:
                    continue
            logger.info(f"💾 {len(history)} geçmiş mesaj hafızaya yüklendi.")
            return history
        except Exception as e:
            logger.error(f"❌ Geçmiş yüklenirken hata: {e}")
        return None

    def _save_history(self):
        """Sohbet geçmişini Veritabanına kaydeder (debounced)."""
        try:
            history = self.chat_session.get_history()
            if not history:
                return
                
            # API'ye sor: Kaydetmeye değer mi?
            if len(history) >= 2:
                recent_texts = []
                for h in history[-2:]:
                    t = " ".join([p.text for p in h.parts if hasattr(p, 'text') and p.text])
                    recent_texts.append(f"{h.role}: {t}")
                
                prompt = "Aşağıdaki konuşma yayın botunun son etkileşimidir. Bu konuşmada kullanıcının yayının GÜNCEL/ANLIK durumu hakkında (örneğin: 'şu an ne oynuyorsunuz?', 'yayında ne var?', 'şu an napıyorsunuz?') sorduğu, yani bir sonraki yayında geçerliliğini yitirecek geçici bilgiler mi konuşuluyor? Eğer konuşma sadece bu tarz geçici anlık durumlar hakkındaysa veya tamamen anlamsızsa 'HAYIR' yanıtı ver. Eğer konuşma genel sohbet, selamlama (sa, as, naber), şaka, veya genel geçer bir konu ise (bunlar basit de olsa saklanabilir) 'EVET' yanıtı ver. Sadece EVET veya HAYIR dön.\n\nSohbet:\n" + "\n".join(recent_texts)
                
                try:
                    check_res = self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                    if check_res and check_res.text and "hayır" in check_res.text.strip().lower():
                        logger.debug("🗑️ API Kararı: Son etkileşim önemsiz bulundu, DB kaydı atlandı.")
                        self._ai_response_count = 0
                        self._last_save_time = time.time()
                        self._history_dirty = False
                        return
                except Exception as api_err:
                    logger.warning(f"⚠️ Kayıt API kontrolü başarısız: {api_err}")

            if len(history) > self.DISK_WINDOW:
                history = history[-self.DISK_WINDOW:]
                
            self.db.clear_chat_history() # Reset and insert
            for h in history:
                text = " ".join([p.text for p in h.parts if hasattr(p, 'text') and p.text])
                if text:
                    self.db.add_chat_history(h.role, text)
            
            self._ai_response_count = 0
            self._last_save_time = time.time()
            self._history_dirty = False
            logger.debug("💾 Sohbet geçmişi DB'ye kaydedildi.")
        except Exception as e:
            logger.error(f"❌ Geçmiş kaydedilirken hata: {e}")

    async def _maybe_save_history(self):
        """
        Debounced kaydetme: Her cevaptan sonra değil, belirli koşullarda kaydeder.
        - Her SAVE_AFTER_N AI cevabından sonra
        - Her SAVE_INTERVAL saniyeden sonra
        """
        if not self._history_dirty:
            return
            
        should_save = (
            self._ai_response_count >= self.SAVE_AFTER_N or
            time.time() - self._last_save_time >= self.SAVE_INTERVAL
        )
        
        if should_save:
            await asyncio.to_thread(self._save_history)

    def _trim_history_if_needed(self):
        """Bellekteki geçmişi MEMORY_WINDOW ile sınırlar."""
        current_history = self.chat_session.get_history()
        if current_history and len(current_history) > self.MEMORY_WINDOW:
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=current_history[-self.MEMORY_WINDOW:],
            )
            logger.debug(f"🔄 Bellek penceresi {self.MEMORY_WINDOW} mesaja kırpıldı.")

    # ══════════════════════════════════════════════════
    #  BAĞLAM ENJEKSİYONU (Context Injection)
    # ══════════════════════════════════════════════════

    async def inject_bot_action(self, action_text: str):
        """
        Bot'un AI dışında gönderdiği mesajları sohbet geçmişine ekler.
        (Hoşgeldin mesajları, statik cevaplar, sessizlik kırıcılar vs.)
        
        Böylece Gemini, botun tüm davranışlarını bağlamda görür ve
        "az önce ne dedin?" gibi sorulara doğru cevap verebilir.
        
        Args:
            action_text: Bot'un sohbete gönderdiği mesaj metni
        """
        try:
            # Bot'un yaptığı eylemi "model" rolüyle geçmişe ekle
            # Etiketli formatta ekliyoruz ki system prompt tanısın
            tagged_text = f"[BOT_EYLEM] {action_text}"
            
            history = self.chat_session.get_history()
            history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=tagged_text)]
            ))
            
            # Session'ı güncellenmiş geçmişle yeniden oluştur
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=history,
            )
            
            self._history_dirty = True
            self._trim_history_if_needed()
            
            logger.debug(f"📝 Bot eylemi bağlama eklendi: {action_text[:60]}...")
        except Exception as e:
            logger.error(f"❌ Bot eylemi enjekte edilemedi: {e}")

    async def inject_user_context(self, username: str, message: str):
        """
        Bot'un cevap vermediği ama sohbette akan mesajları bağlama ekler.
        Bu, AI'nın sohbetin genel havasını anlamasını sağlar.
        
        Not: Bunlar "user" rolüyle eklenir ama etiketlidir,
        böylece AI bunlara doğrudan cevap vermez.
        
        Args:
            username: Mesajı yazan kullanıcı adı
            message:  Sohbet mesajı
        """
        try:
            tagged_text = f"[SOHBET_AKIŞI] [{username}]: \"{message}\""
            
            history = self.chat_session.get_history()
            
            # Ardışık user mesajlarını birleştir (API kısıtlaması)
            # Gemini aynı role'den iki ardışık mesaj kabul etmiyor
            if history and history[-1].role == "user":
                # Son user mesajına ekle
                existing_text = ""
                if history[-1].parts and hasattr(history[-1].parts[0], 'text'):
                    existing_text = history[-1].parts[0].text
                merged_text = existing_text + "\n" + tagged_text
                history[-1] = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=merged_text)]
                )
            else:
                history.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=tagged_text)]
                ))
            
            # Session'ı güncellenmiş geçmişle yeniden oluştur
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=history,
            )
            
            self._history_dirty = True
            self._trim_history_if_needed()
            
            logger.debug(f"💬 Sohbet bağlamı eklendi: [{username}]: {message[:40]}...")
        except Exception as e:
            logger.error(f"❌ Sohbet bağlamı enjekte edilemedi: {e}")

    # ══════════════════════════════════════════════════
    #  CEVAP ÜRETİMİ
    # ══════════════════════════════════════════════════

    async def generate_response(self, username: str, message: str) -> str:
        """
        Kullanıcının mesajına yapay zeka ile cevap üretir.

        Args:
            username: Mesajı gönderen kullanıcının adı
            message:  Kullanıcının sohbet mesajı

        Returns:
            Yapay zekanın ürettiği kısa cevap metni
        """
        try:
            # Mesajı yapay zekaya gönderilecek formata çevir
            prompt = f"Sohbette [{username}] şunu yazdı: \"{message}\""

            # Bellek penceresini kontrol et
            self._trim_history_if_needed()

            # Gemini API Chat Session üzerinden çağrıyı asenkron olarak yap (Hafızalı)
            response = await asyncio.to_thread(
                self.chat_session.send_message,
                prompt,
            )

            if not response or not response.text:
                logger.warning("⚠️ Boş veya güvenlik filtresine takılmış AI yanıtı.")
                return "Hımm, buna ne diyeceğimi bilemedim... 🤐"

            reply = response.text.strip()
            
            logger.info(f"🤖 AI Yanıt [{username}] → {reply}")
            
            # Debounced kaydetme
            self._ai_response_count += 1
            self._history_dirty = True
            await self._maybe_save_history()
            
            return reply

        except Exception as e:
            logger.error(f"❌ AI yanıt üretemedi: {e}")
            return "Beyin kısa devre yaptı, bi dk... 🤖💥"

    async def evaluate_learning(self, username: str, text: str) -> dict:
        """
        Kullanıcının !öğren komutu ile verdiği bilgiyi denetler ve JSON olarak döner.
        """
        try:
            prompt = f"""Bir izleyici ({username}) bota şu bilgiyi öğretmek istiyor: "{text}"
Görevlerin:
1. Bu bilgi küfür, nefret söylemi, siyaset veya zararlı bir içerik mi? Öyleyse reddet.
2. Bilgi çok anlamsız veya saçmaysa reddet.
3. Eğer bilgi güvenliyse KABUL ET.
4. Kabul edersen, izleyicinin bu cevabı tetiklemesi için kullanacağı çok kısa bir "anahtar kelime" ve botun vereceği esprili bir "cevap" üret.

SADECE VE SADECE aşağıdaki formatta geçerli bir JSON döndür (başka metin veya markdown ekleme):
{{
  "kabul": true,
  "anahtar": "tetikleyici_kelime",
  "cevap": "esprili_bot_cevabi",
  "sebep": ""
}}
"""
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt
            )
            
            if not response or not response.text:
                return {"kabul": False, "sebep": "Yapay zeka yanıt veremedi."}
                
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:-3].strip()
            elif raw.startswith("```"):
                raw = raw[3:-3].strip()
                
            import json
            return json.loads(raw)
        except Exception as e:
            logger.error(f"❌ Öğrenme değerlendirmesi başarısız: {e}")
            return {"kabul": False, "sebep": "Sistemsel bir hata oluştu."}

    async def force_save(self):
        """Kapanış veya acil durumlarda geçmişi zorla diske kaydeder."""
        if self._history_dirty:
            await asyncio.to_thread(self._save_history)
            logger.info("💾 Geçmiş zorla kaydedildi.")


# ──────────────────────────────────────────────────────────
#  BAĞIMSIZ TEST MODU
#  Bu dosyayı tek başına çalıştırarak AI'ı test edebilirsin:
#     python ai_brain.py
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Loglama ayarı
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    api_key = os.getenv("GEMINI_API_KEY")
    bot_name = os.getenv("BOT_NAME", "KickAsistan")

    if not api_key or api_key == "buraya_gemini_api_anahtarini_yaz":
        print("\n❌ HATA: .env dosyasındaki GEMINI_API_KEY değerini doldurman gerek!")
        print("   → Google AI Studio'dan al: https://aistudio.google.com/apikey\n")
        exit(1)

    brain = AIBrain(api_key=api_key, bot_name=bot_name)

    print(f"\n{'='*50}")
    print(f"  🧠 {bot_name} — AI Beyin Test Modu")
    print(f"  Çıkmak için 'q' yaz.")
    print(f"{'='*50}\n")

    async def test_loop():
        while True:
            user_input = input("Sen > ").strip()
            if user_input.lower() in ("q", "quit", "exit", "çık"):
                print("👋 Görüşürüz!")
                await brain.force_save()
                break
            if not user_input:
                continue

            response = await brain.generate_response("TestKullanici", user_input)
            print(f"🤖 {bot_name} > {response}\n")

    asyncio.run(test_loop())
