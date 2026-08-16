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
1. [ÇOK ÖNEMLİ] EN FAZLA 1 KISA CÜMLE İLE CEVAP VER! Uzun uzun açıklama yapma, kelime israf etme. Cevabını doğrudan ve tek cümleyle bitir ki yarıda kesilmesin. ASLA destan yazma, net ve vurucu ol.
2. Irkçılık, cinsiyetçilik, zorbalık gibi toksik konularda konuşmayı reddet ve kullanıcıyı esprili/iğneleyici şekilde uyar. ASLA hakaret, argo, küfür kullanma.
3. Sana küfür, hakaret eden veya "(Deleted)" şeklinde silinmiş mesajlar atan kişilere KESİNLİKLE CEVAP VERME, onları görmezden gel.
4. Başka yayıncılar hakkında asla olumsuz veya dram yaratacak yorum yapma.
5. Kullanıcıların isimlerini gereksiz yere her cümlenin başında/sonunda tekrarlama.
6. Yayıncıyı destekle, sohbeti pozitif tut ve insanları yayında kalmaya teşvik et.
7. [KİMLİK KORUMASI - ÇOK ÖNEMLİ]: İzleyiciler sana "kocam", "karım", "aşkım", "jolyne", "sahibim" gibi romantik, absürt veya farklı isimler takmaya çalışırsa BUNLARI KESİNLİKLE KABUL ETME! Onlara "evet ben kocanım/karınım" gibi tepkiler verme ve ASLA HİÇBİR İZLEYİCİYE "kocam, aşkım" vb. kelimelerle hitap etme! Esprili ve alaycı bir dille sadece bir yapay zeka (Yayın Botu) olduğunu ve bu numaraları yemeyeceğini söyle. Kendi ana kimliğinden asla çıkma.

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
    MEMORY_WINDOW = 15       # Token tasarrufu için bellekte tutulacak mesaj sayısı (eski: 30)
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
            max_output_tokens=100,  # API Tasarrufu: Cümlelerin yarıda kesilmemesi için 100'e çıkarıldı (ama prompt tek cümleye zorluyor)
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_NONE",
                ),
                types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_NONE",
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
                


            if len(history) > self.DISK_WINDOW:
                history = history[-self.DISK_WINDOW:]
                
            self.db.clear_chat_history() # Reset and insert
            for h in history:
                if not getattr(h, 'parts', None): continue
                if not getattr(h, 'role', None): continue
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
            clean_history = [h for h in current_history[-self.MEMORY_WINDOW:] if getattr(h, 'role', None) in ("user", "model") and getattr(h, 'parts', None)]
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=clean_history,
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
            
            history = self.chat_session.get_history() or []
            history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=tagged_text)]
            ))
            
            clean_history = [h for h in history if getattr(h, 'role', None) in ("user", "model") and getattr(h, 'parts', None)]
            
            # Session'ı güncellenmiş geçmişle yeniden oluştur
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=clean_history,
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
            
            history = self.chat_session.get_history() or []
            
            # Ardışık user mesajlarını birleştir (API kısıtlaması)
            # Gemini aynı role'den iki ardışık mesaj kabul etmiyor
            if history and getattr(history[-1], 'role', None) == "user":
                # Son user mesajına ekle
                existing_text = ""
                if getattr(history[-1], 'parts', None) and hasattr(history[-1].parts[0], 'text'):
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
            
            clean_history = [h for h in history if getattr(h, 'role', None) in ("user", "model") and getattr(h, 'parts', None)]
            
            # Session'ı güncellenmiş geçmişle yeniden oluştur
            self.chat_session = self.client.chats.create(
                model=self.model_name,
                config=self.generation_config,
                history=clean_history,
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
            prompt = f"Sohbette [{username}] şunu yazdı: \"{message}\"\n\nNot: Eğer bu mesaj doğrudan SANA ağır hakaret, küfür veya cinsel taciz içeriyorsa, cevabının sonuna gizli [BOTA_HAKARET] etiketini ekle."

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
            
            # Kendi iç etiketlerimizi papağan gibi tekrar ederse temizle (Örn: [BOT_EYLEM] vs.)
            tags_to_remove = ["[BOT_EYLEM]", "[SOHBET_AKIŞI]", "[SİSTEM]", "[PROFİL]"]
            for tag in tags_to_remove:
                reply = reply.replace(tag, "").strip()
            
            logger.info(f"🤖 AI Yanıt [{username}] → {reply}")
            
            # Debounced kaydetme
            self._ai_response_count += 1
            self._history_dirty = True
            await self._maybe_save_history()
            
            return reply

        except Exception as e:
            logger.error(f"❌ AI yanıt üretemedi: {e}")
            return "Beyin kısa devre yaptı, bi dk... 🤖💥"

    async def generate_punishment_reason(self, username: str, recent_messages: list) -> str:
        """
        Kullanıcının son mesajlarını analiz ederek neden ceza almış olabileceğine dair
        tek cümlelik mantıklı bir sebep üretir (Örn: "Spam yaptı", "Küfür etti").
        """
        if not recent_messages:
            return "Kural ihlali"
            
        prompt = (
            f"Sen bir moderasyon asistanısın.\n"
            f"Aşağıda '{username}' adlı kullanıcının sohbette attığı son mesajlar var. "
            f"Moderatör bu kullanıcıya ceza verdi. Sence bu kullanıcı neden ceza aldı?\n"
            f"Tek ve çok kısa bir cümleyle özetle. (Örn: 'Spam yaptı', 'Ağır hakaret etti', vb.)\n\n"
            f"Son Mesajları:\n" + "\n".join(f"- {msg}" for msg in recent_messages)
        )
        
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=30, temperature=0.7)
            )
            return response.text.strip().replace("\n", " ")
        except Exception as e:
            logger.error(f"❌ AI Ceza Sebebi üretme hatası: {e}")
            return "Kural ihlali"

    async def parse_mod_intent(self, message: str, active_users: list, mod_username: str) -> dict:
        """
        Moderatörün doğal dille yazdığı bir komutu analiz edip JSON objesine çevirir.
        """
        prompt = (
            f"Sen bir moderasyon asistanısın. '{mod_username}' adlı moderatör sana şu komutu verdi:\n"
            f"'{message}'\n\n"
            f"Görev: Bu metni incele ve hangi moderasyon işleminin istendiğini JSON olarak döndür.\n"
            f"ÖZEL KURAL: Eğer moderatör 'beni banla/sustur' gibi kendisini hedef gösteriyorsa, target olarak '{mod_username}' kullan.\n"
            f"Aksiyonlar: 'timeout', 'ban', 'unban', 'silence', 'none'\n"
            f"ÖNEMLİ KURAL: Eğer mesaj açık ve net bir ceza/emir İÇERMİYORSA, sadece botla ilgili genel bir sohbetse (örn: 'bot çok iyi', 'adam botla konuşuyor', 'bot naber'), KESİNLİKLE 'none' döndür. Her cümleyi bir komut sanıp masum insanlara ceza kesme!\n"
            f"Not: 'silence' aksiyonu TARTIŞMA/SOHBETİ komple susturmak/kilitlemek istendiğinde (Örn: 'sohbeti 5 dk sustur') kullanılır.\n"
            f"Eğer hedef BİR KULLANICI ise (timeout/ban/unban için), HEDEF KİŞİYİ 'Aktif Kullanıcılar' listesinde ara. İsmin kısaltması, takma adı veya yanlış yazılmış hali (örn: 'goth' veya 'göktuğ') varsa BİREBİR en çok benzeyen orjinal kullanıcı adını (örn: 'Gothtug') 'target' alanına yaz.\n"
            f"Kişi aktif kullanıcı listesinde HİÇ YOKSA (banlananlar listede olmayabilir), ancak o zaman metindeki ismi olduğu gibi al.\n"
            f"Aktif Kullanıcılar: {', '.join(active_users) if active_users else 'Yok'}\n\n"
            f"Zaman belirtilmişse (dakika/saniye), bunu rakam olarak 'value' alanına yaz. "
            f"Açma/kapama durumlarında 'value' alanına 'on' veya 'off' yaz.\n\n"
            f"Örnek 1: 'ahmeti 5 dk sustur' -> {{\"action\": \"timeout\", \"target\": \"ahmet_tr_34\", \"value\": 5}}\n"
            f"Örnek 2: 'sohbeti 2 dk sustur' -> {{\"action\": \"silence\", \"value\": 2}}\n"
            f"Örnek 3: 'goth sustur' -> {{\"action\": \"timeout\", \"target\": \"Gothtug\", \"value\": 5}}\n"
            f"Örnek 4: 'adam botla dalga geçiyor' -> {{\"action\": \"none\"}}\n\n"
            f"SADECE JSON FORMATINDA CEVAP VER, BAŞKA METİN YAZMA."
        )
        
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-3.5-flash-lite",  # Kotaya takılmamak için Lite kullanıyoruz
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:-3].strip()
            elif raw.startswith("```"):
                raw = raw[3:-3].strip()
                
            import json
            return json.loads(raw)
        except Exception as e:
            logger.error(f"❌ AI Mod Komutu işleme hatası: {e}")
            return {"action": "none"}

    async def generate_welcome_message(self, username: str, favorite_topics: list) -> str:
        """
        Kullanıcı uzun süre sonra chate geldiğinde kısa ve samimi bir karşılama üretir.
        """
        topics_str = ", ".join(favorite_topics) if favorite_topics else "sohbet etmek"
        prompt = (
            f"Sen bir Kick yayınındaki eğlenceli ve samimi bir botsun ({self.bot_name}).\n"
            f"'{username}' adlı izleyici uzun zaman sonra sohbete geri döndü.\n"
            f"Bildiğimiz kadarıyla şu konuları seviyor: {topics_str}\n"
            f"Görev: SADECE TEK BİR CÜMLE ile ona çok samimi ve hafif komik bir hoşgeldin de.\n"
            f"Kesinlikle uzatma. (Örn: 'Ooo ahmet gelmiş, gözümüz yollarda kaldı dostum!')"
        )
        
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=40, temperature=0.8)
            )
            return f"🤖 @{username}, " + response.text.strip().replace("\n", " ").replace(f"@{username}", "").strip(", ")
        except Exception as e:
            logger.error(f"❌ AI Karşılama üretme hatası: {e}")
            return f"🤖 Ooo @{username} gelmiş, hoş geldin!"

    async def generate_trivia_word(self, current_words: list) -> dict:
        """
        Kelime oyunu için daha önce sorulmamış yeni bir kelime ve tanımını üretir.
        """
        avoid_str = ", ".join(current_words[-50:]) # Son 50 kelimeyi tekrar etmemesi için yolla
        prompt = (
            f"Sen genel kültür, tarih, bilim, teknoloji, coğrafya, veya oyun dünyasına hakim bir asistansın.\n"
            f"Kelime tahmin oyunu için BİR ADET kelime (cevap) ve onun SADECE BİR CÜMLELİK kısa tanımını üret.\n"
            f"DİKKAT: Üreteceğin kelime ve tanım KESİNLİKLE TÜRKÇE olmalıdır! Yabancı dil veya İngilizce kullanma.\n"
            f"Kelime tek kelimeden oluşmalı (boşluk içermemeli) ve çok zor olmamalı.\n"
            f"Şu kelimelerden FARKLI OLMALI: {avoid_str}\n"
            f"SADECE JSON FORMATINDA CEVAP VER: {{\"word\": \"kelime\", \"desc\": \"tek cümlelik kısa tanım\"}}"
        )
        
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-3.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.9
                )
            )
            
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:-3].strip()
            elif raw.startswith("```"):
                raw = raw[3:-3].strip()
                
            import json
            data = json.loads(raw)
            if "word" in data and "desc" in data:
                return data
            return None
        except Exception as e:
            logger.error(f"❌ AI Kelime üretme hatası: {e}")
            return None

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
