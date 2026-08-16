"""
╔══════════════════════════════════════════════════════════╗
║              MAIN.PY (Orkestra Şefi)                     ║
║  Beyin (AI) ve Kulak (Kick Listener) modüllerini         ║
║  birbirine bağlayıp sistemi yöneten ana dosya.           ║
║                                                          ║
║  Tam bağlam yönetimi: Botun tüm eylemleri AI'ya          ║
║  aktarılır, sohbet akışı takip edilir.                   ║
╚══════════════════════════════════════════════════════════╝

Kullanım:
  python main.py              → Botu başlatır
  python main.py --test-ai    → Sadece AI'ı test eder (sohbet modu)
  python main.py --setup      → Kick OAuth kurulumu yapar
"""

import asyncio
import os
import sys
import logging
import time
import json
import re
from difflib import SequenceMatcher
from dotenv import load_dotenv
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

from database import Database
from ai_brain import AIBrain
from kick_listener import KickChatListener
from games import GameEngine
from memory import UserMemory



# ──────────────────────────────────────────────────────────
#  YAPILANDIRMA
# ──────────────────────────────────────────────────────────

# .env dosyasını yükle (Arayüzden güncellenen verilerin anında algılanması için override=True)
load_dotenv(override=True)

# Ortam değişkenlerini oku
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
KICK_CHANNEL_SLUG = os.getenv("KICK_CHANNEL_SLUG", "")
BOT_NAME = os.getenv("BOT_NAME", "KickAsistan")
KICK_CLIENT_ID = os.getenv("KICK_CLIENT_ID", "")
KICK_CLIENT_SECRET = os.getenv("KICK_CLIENT_SECRET", "")
KICK_REDIRECT_URI = os.getenv("KICK_REDIRECT_URI", "http://localhost:3000/callback")
COOLDOWN_SECONDS = int(os.getenv("BOT_COOLDOWN", "3"))  # Varsayılan 3 saniye bekleme süresi
AI_RESPONSE_CHANCE = float(os.getenv("AI_RESPONSE_CHANCE", "15")) / 100.0  # Varsayılan %15 katılım
ENABLE_SILENCE_BREAKER = os.getenv("ENABLE_SILENCE_BREAKER", "True").lower() == "true" # Sessizlik kırıcı aktif mi?

# Botun tepki vereceği tetikleyiciler
COMMAND_PREFIX = "!"                     # "!bot", "!soru" gibi komutlar
MENTION_TRIGGERS = [                     # Bunlar mesajda geçerse bot cevap verir
    BOT_NAME.lower(),
    "bot",
    "asistan",
    "diablo",
    "diabloabot",
    "diablo_abot"
]

# Botun kendi mesajlarına cevap vermemesi için
# NOT: Bot ana hesaptan çalıştığı için IGNORED_USERS yeterli değil.
# Bunun yerine gönderilen mesajları takip eden _sent_messages sistemi kullanılıyor.
IGNORED_USERS = [BOT_NAME.lower()]

# Bot'un gönderdiği mesajları tanımak için prefix
BOT_MESSAGE_PREFIX = "🤖"

# Fuzzy matching ayarları
FUZZY_THRESHOLD = 0.92     # %92 benzerlik eşiği (uzun cümlelerde güvenli)
FUZZY_MIN_WORDS = 2        # En az 2 kelimelik mesajlarda fuzzy match yap
FUZZY_LENGTH_RATIO = 0.7   # Uzunluk oranı alt sınırı (kısa/uzun >= 0.7 olmalı)

# Loglama formatı
LOG_FORMAT = "%(asctime)s │ %(name)-14s │ %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

# Debounced save aralıkları
VIP_SAVE_INTERVAL = 600     # VIP kaydetme aralığı (10 dakika)
PENDING_SAVE_INTERVAL = 60  # Pending commands kaydetme aralığı (1 dakika)


# ──────────────────────────────────────────────────────────
#  ANA UYGULAMA
# ──────────────────────────────────────────────────────────

class KickAsistan:
    """
    Kick sohbet botunun ana kontrolcüsü.
    Beyin (AIBrain) ve Kulak (KickChatListener) arasındaki köprüdür.
    
    Tam bağlam yönetimi ile botun tüm eylemlerini AI'ya aktarır
    ve sohbetin genel akışını takip eder.
    """

    def __init__(self):
        self.db = Database()
        self.brain: AIBrain | None = None
        self.listener: KickChatListener | None = None
        
        # Bot istatistikleri
        self._message_count = 0
        self._response_count = 0
        
        # Arka plan görevleri (Görevleri referans tutmak için)
        self._tasks = []
        
        self.user_cooldowns = {}  # Her kullanıcı için son mesaj zamanını tutar
        self.seen_users = set() # Sohbete ilk kez yazanları tutar
        self.global_silence_until = 0 # Genel sohbet kilidinin biteceği timestamp
        self._infractions = {} # Sabıka Kaydı: {username: ceza_sayisi}
        self.user_chat_history = {} # Her kullanıcının son 5 mesajı: {username: [msg1, msg2...]}
        
        self._last_chat_time = time.time()
        self._silence_broken = False

        # ── Context buffer (AI çağrısından önce enjekte edilecek) ──
        self._context_buffer = []        # Son N cevaplanmayan mesaj
        self._context_buffer_max = 5     # Maksimum buffer boyutu
        self._context_injected = False   # Buffer enjekte edildi mi?

        # ── Bot'un kendi mesajlarını tanıma sistemi ──
        self._sent_messages: dict[str, float] = {}  # {content_hash: timestamp}
        self._sent_messages_ttl = 30  # 30 saniye sonra hash'leri temizle
        
        # ── Yeni Sistemler (Oyun & Hafıza) ──
        self.games = GameEngine(self.db)
        self.memory = UserMemory(self.db)
        
        # ── Akıllı Sohbet State ──
        self._chat_timestamps = []  # Son 60 saniyedeki mesaj zamanları
        self._global_silence_until = 0  # Botun susacağı timestamp
        self.deleted_message_ids = set() # Silinen mesajların ID'leri
        
        # ── API Yükü ve Koruma ──
        self._api_call_timestamps = []  # Son 60 saniyedeki API istekleri
        self._api_warning_last_sent = 0 # Mod-only uyarı mesajının son gönderilme zamanı
        self._user_api_timestamps = {}  # {username: [ts1, ts2]} - Bireysel darlama limiti

    # ══════════════════════════════════════════════════
    #  DOSYA YÖNETİMİ

    # ══════════════════════════════════════════════════

    # (Dosya yönetim metodları silindi)

    # ══════════════════════════════════════════════════
    #  MESAJ FORMATLAMA ve GÖNDERİM
    # ══════════════════════════════════════════════════

    def _register_sent_message(self, message: str):
        """
        Gönderilen mesajın hash'ini kaydeder. WebSocket'ten geri geldiğinde
        bot'un kendi mesajı olarak tanınması için.
        """
        # İçerik hash'i oluştur (küçük harf, boşluklar temizlenmiş)
        content_hash = message.strip().lower()
        self._sent_messages[content_hash] = time.time()
        
        # Eski hash'leri temizle (TTL süresi geçmişleri sil)
        self._cleanup_sent_messages()

    def _cleanup_sent_messages(self):
        """TTL süresi geçmiş gönderilmiş mesaj hash'lerini temizler."""
        now = time.time()
        expired = [h for h, t in self._sent_messages.items() if now - t > self._sent_messages_ttl]
        for h in expired:
            del self._sent_messages[h]

    def _is_own_message(self, content: str) -> bool:
        """
        Gelen mesajın bot'un kendi gönderdiği mesaj olup olmadığını kontrol eder.
        
        İki katmanlı kontrol:
        1. Mesaj bot prefix'i (🤖) ile başlıyorsa → muhtemelen botun mesajı
        2. İçerik hash'i sent_messages'da varsa → kesinlikle botun mesajı
        """
        content_lower = content.strip().lower()
        
        # Katman 1: Hash eşleşmesi (en güvenilir)
        if content_lower in self._sent_messages:
            del self._sent_messages[content_lower]  # Kullanıldı, temizle
            return True
        
        # Katman 2: Bot prefix kontrolü (yedek — 🤖 ile başlıyan her mesaj botundur)
        if content.strip().startswith(BOT_MESSAGE_PREFIX):
            return True
        
        return False

    async def _send_formatted_response(self, username: str, response: str, inject_to_context: bool = True):
        """
        Formatlanmış bot cevabını sohbete gönderir ve isteğe bağlı olarak
        AI bağlamına enjekte eder.
        
        Args:
            username: Hedef kullanıcı adı
            response: Bot'un cevap metni
            inject_to_context: True ise bu mesajı AI'nın sohbet geçmişine de ekler
        """
        clean_resp = response.strip()
        if clean_resp.startswith(f"@{username}"):
            formatted_response = f"🤖 {clean_resp}"
        else:
            formatted_response = f"🤖 @{username}, {clean_resp}"
        
        # Gönderilecek mesajı kaydet (WebSocket'ten geri geldiğinde tanımak için)
        self._register_sent_message(formatted_response)
        
        await self.listener.send_message(formatted_response)
        
        # Bot'un bu eylemini AI bağlamına ekle
        if inject_to_context and self.brain:
            await self.brain.inject_bot_action(formatted_response)

    async def _send_bot_message(self, message: str, inject_to_context: bool = True):
        """
        Bot'un doğrudan (kullanıcıya yöneltilmemiş) mesaj göndermesi.
        
        Args:
            message: Gönderilecek mesaj
            inject_to_context: True ise bu mesajı AI'nın sohbet geçmişine de ekler
        """
        # Gönderilecek mesajı kaydet (WebSocket'ten geri geldiğinde tanımak için)
        self._register_sent_message(message)
        
        await self.listener.send_message(message)
        
        # Bot'un bu eylemini AI bağlamına ekle
        if inject_to_context and self.brain:
            await self.brain.inject_bot_action(message)

    # ══════════════════════════════════════════════════
    #  FUZZY MATCHING (Bulanık Eşleşme)
    # ══════════════════════════════════════════════════

    def _fuzzy_match_static(self, message: str) -> str | None:
        """
        Statik komutlarda tam eşleşme bulunamazsa, benzerlik skoru ile 
        en yakın komutu bulur.
        
        Örnek: "asistanım naber" → "asistan naber" (%85+ benzerlik)
        
        Args:
            message: Küçük harfe çevrilmiş kullanıcı mesajı
            
        Returns:
            Eşleşen statik cevap veya None
        """
        # Çok kısa mesajlarda fuzzy match yapma (yanlış pozitif riski)
        words = message.split()
        if len(words) < FUZZY_MIN_WORDS:
            return None
            
        best_match = None
        best_score = 0.0
        msg_len = len(message)
        
        for key in self.db.get_static_commands():
            key_len = len(key)
            
            # Uzunluk oranı kontrolü: "asistan naber" vs "asistan bana pi sayısının 54. rakamını söyle"
            # gibi çok farklı uzunluklardaki cümleleri eşleştirme
            if key_len == 0 or msg_len == 0:
                continue
            length_ratio = min(msg_len, key_len) / max(msg_len, key_len)
            if length_ratio < FUZZY_LENGTH_RATIO:
                continue
            
            score = SequenceMatcher(None, message, key).ratio()
            if score > best_score and score >= FUZZY_THRESHOLD:
                best_score = score
                best_match = key
        
        if best_match:
            logger.info(f"🎯 Fuzzy eşleşme: '{message}' → '{best_match}' ({best_score:.0%})")
            return self.db.get_static_commands()[best_match]
        
        return None

    # ══════════════════════════════════════════════════
    #  YAPILANDIRMA ve KONTROL
    # ══════════════════════════════════════════════════

    def _validate_config(self) -> bool:
        """Gerekli yapılandırma değerlerinin mevcut olduğunu kontrol eder."""
        errors = []

        if not GEMINI_API_KEY or GEMINI_API_KEY == "buraya_gemini_api_anahtarini_yaz":
            errors.append(
                "GEMINI_API_KEY → Google AI Studio'dan al: https://aistudio.google.com/apikey"
            )

        if not KICK_CHANNEL_SLUG or KICK_CHANNEL_SLUG == "buraya_kanal_adini_yaz":
            errors.append(
                "KICK_CHANNEL_SLUG → Kick kanalının URL'sindeki ismi yaz"
            )

        if errors:
            print("\n❌ .env dosyasında eksik ayarlar var:\n")
            for err in errors:
                print(f"   • {err}")
            print(f"\n   📝 Dosya: {os.path.join(os.path.dirname(__file__), '.env')}\n")
            return False

        return True

    def _should_respond(self, username: str, message: str, msg_per_min: int = 0) -> bool:
        """
        Mesajın bot tarafından cevaplanıp cevaplanmayacağına karar verir.

        Kurallar:
          1. Kendi mesajlarını yoksay
          2. "!" ile başlayan komutlara cevap ver
          3. Bot adı veya tetikleyici kelimeler geçiyorsa cevap ver
        """
        # Kendi mesajlarını ve bilinen botları yoksay
        if username.lower() in IGNORED_USERS:
            return False

        msg_lower = message.lower().strip()

        # Komut prefixi ile başlıyorsa ("!soru", "!bot" vb.)
        if msg_lower.startswith(COMMAND_PREFIX):
            return True

        # Tetikleyici kelimelerden biri geçiyorsa
        for trigger in MENTION_TRIGGERS:
            if trigger in msg_lower:
                return True

        # Dinamik Rastgele Aktif Katılım
        import random
        chance = AI_RESPONSE_CHANCE
        if msg_per_min >= 30:
            chance = 0.0  # Hızlı sohbette araya girme, kotayı koru
        elif msg_per_min >= 10:
            chance = min(0.10, chance) # Normal sohbette en fazla %10
        elif msg_per_min > 0:
            chance = max(0.20, chance) # Ölü sohbette en az %20 canlandırma şansı

        if random.random() < chance:
            return True

        return False

    def _extract_command(self, message: str) -> str:
        """
        Komut prefixini temizleyip asıl mesajı döndürür.
        "!soru nedir bu" → "soru nedir bu"
        """
        msg = message.strip()
        if msg.startswith(COMMAND_PREFIX):
            msg = msg[len(COMMAND_PREFIX):].strip()
        return msg

    # ══════════════════════════════════════════════════
    #  OLAY İŞLEYİCİLERİ (Event Handlers)
    # ══════════════════════════════════════════════════

    async def on_subscription(self, username: str):
        """Kick'te biri abone olduğunda tetiklenir."""
        logger.info(f"🎉 Yeni Abone: {username}")
        msg = f"🤖 Abone olduğun için çok teşekkürler @{username}! Aramıza hoş geldin! 💜"
        await self._send_bot_message(msg)

    async def on_follow(self, username: str):
        """Kick'te biri takip ettiğinde tetiklenir."""
        if username == "Biri":
            # Kullanıcı isteği üzerine isimsiz takipçi mesajı kapatıldı.
            return
            
        msg = f"🤖 Takip ettiğin için çok teşekkürler @{username}! Hoş geldin! 💖"
        logger.info(f"💖 Yeni Takipçi Mesajı: {username}")
        await self._send_bot_message(msg)

    async def on_chat_message(self, username: str, content: str, msg_id: str, is_mod: bool = False, replied_user: str = None):
        """
        KickListener'dan gelen yeni sohbet mesajlarını yakalar.
        Akıllı Sohbet Modu, Oyunlar, Moderasyon ve Hafıza entegrasyonu barındırır.
        """
        # ── BOT'UN KENDİ MESAJINI ALGILAMA ──
        if username.lower() in IGNORED_USERS or self._is_own_message(content):
            logger.debug(f"🤖 Kendi mesajımız algılandı, atlanıyor: {content[:50]}...")
            return

        # ── KÖTÜ KELİME FİLTRESİ ──
        BAD_WORDS = {"amk", "aq", "siktir", "orospu", "piç", "pic", "yarrak", "yarak", "amcık", "gavat", "ibne", "pezevenk", "oç", "oc"}
        raw_msg_lower = content.lower().strip()
        words = set(raw_msg_lower.split())
        if not is_mod and any(bad_word in words for bad_word in BAD_WORDS):
            logger.info(f"🤬 Küfür/Hakaret algılandı: {username}")
            await self.listener.ban_user(username, duration_minutes=1, reason="Otomatik Küfür/Hakaret Engeli")
            self.db.add_mod_log(username, "timeout", 1, "Otomatik Küfür/Hakaret Engeli")
            await self._send_bot_message(f"🤖 🚨 @{username}, ağzımızı bozmuyoruz! 1 dakika mola.")
            if self.brain:
                self._context_buffer.append(("[SİSTEM]", f"Bot, '{username}' kullanıcısını küfür/hakaret nedeniyle 1 dk susturdu."))
            return

        # Sadece "(Deleted)" içeren ve moderasyon aracı tarafından silinmiş olan mesajları atla
        if "(deleted)" in raw_msg_lower:
            return

        self._message_count += 1
        current_time = time.time()
        
        ai_content = content
        if replied_user:
            ai_content = f"{content} (Bu mesaj {replied_user} adlı kullanıcıya yanıttır)"
        
        # ── AKILLI SOHBET (CHAT SPEED) TAKİBİ ──
        self._chat_timestamps.append(current_time)
        self._chat_timestamps = [t for t in self._chat_timestamps if current_time - t <= 60]
        msg_per_min = len(self._chat_timestamps)

        # ── KULLANICI SON MESAJ GEÇMİŞİ (AI CEZA NEDENİ İÇİN) ──
        if username not in self.user_chat_history:
            self.user_chat_history[username] = []
        self.user_chat_history[username].append(content)
        if len(self.user_chat_history[username]) > 5:
            self.user_chat_history[username].pop(0)

        # ── SESSİZLİK MODU KONTROLÜ (GLOBAL SOHBET KİLİDİ) ──
        if current_time < self.global_silence_until and not is_mod:
            # Sabıka kaydını kontrol et
            offenses = self._infractions.get(username, 0)
            offenses += 1
            self._infractions[username] = offenses
            
            reason = f"Sessizlik Modu İhlali (Suç #{offenses})"
            
            if offenses == 1:
                # İlk Suç: 5 dk
                await self.listener.ban_user(username, duration_minutes=5, reason=reason)
                self.db.add_mod_log(username, "timeout", 5, reason)
                await self._send_bot_message(f"🤖 🔨 {username}, Sessizlik Modunda konuştuğu için uyarıldı (5dk Susturma).")
                system_note = f"Bot, '{username}' kullanıcısını 1. kez ihlal ettiği için 5 dk susturdu."
            elif offenses == 2:
                # İkinci Suç: 10 dk
                await self.listener.ban_user(username, duration_minutes=10, reason=reason)
                self.db.add_mod_log(username, "timeout", 10, reason)
                await self._send_bot_message(f"🤖 🔨 {username}, sessizliği 2. kez bozduğu için 10 dakika susturuldu!")
                system_note = f"Bot, '{username}' kullanıcısını 2. kez ihlal ettiği için 10 dk susturdu."
            else:
                # Üçüncü Suç ve Sonrası: 30 dk Susturma
                await self.listener.ban_user(username, duration_minutes=30, reason=reason)
                self.db.add_mod_log(username, "timeout", 30, reason)
                await self._send_bot_message(f"🤖 🔨 {username}, kurallara uymamakta ısrar ettiği için 30 dakika uzaklaştırıldı.")
                system_note = f"Bot, '{username}' kullanıcısını kural ihlalinde ısrar ettiği için 30 dk susturdu."

            # AI hafızasına enjekte et
            if self.brain:
                self._context_buffer.append(("[SİSTEM]", system_note))
            return

        # ── KULLANICI HAFIZA GÜNCELLEMESİ ──
        current_score = self.games.get_score(username)
        self.memory.log_message(username, content, is_mod, current_score)

        # ── SESSİZLİK SIFIRLAYICI ──
        self._last_chat_time = current_time
        self._silence_broken = False

        # ── KEMİK KİTLE (VIP) TARAMASI ──
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.db.add_active_day(username, today)

        # ── BİLGİ KOMUTU ──
        if raw_msg_lower == "!bilgi":
            msg = "🤖 Mevcut Komutlar: !sayıoyunu, !kelimeoyunu, !puan, !liderlik. Ayrıca ismimi geçirerek benimle muhabbet edebilirsin!"
            await self._send_bot_message(msg)
            return

        # ── MODERATÖR KOMUTLARI ──
        if is_mod:
            # Doğal Dil (NLP) Moderasyon Kontrolü
            if not raw_msg_lower.startswith("!") and any(trigger in raw_msg_lower for trigger in MENTION_TRIGGERS):
                if self.brain:
                    # Yüzlerce kullanıcı varsa API limitini zorlamamak için sadece son 40 aktif kullanıcıyı gönderiyoruz
                    active_users = list(self.user_chat_history.keys())[-40:]
                    intent = await self.brain.parse_mod_intent(ai_content, active_users, username)
                    action = intent.get("action", "none")
                    target = intent.get("target", "")
                    val = intent.get("value")
                    reason = intent.get("reason", "Moderatör Talebi")
                    
                    target_user = self.db.get_user(target) if target else None
                    target_is_mod = target_user.get("mod", False) if target_user else False
                    
                    if target and target.lower() in [BOT_NAME.lower(), "bot", "asistan", "kendini"]:
                        await self._send_bot_message("🤖 Hata: Kendi fişimi çekemem patron! 😎")
                        return
                        
                    if target and (target_is_mod or target.lower() == KICK_CHANNEL_SLUG.lower()):
                        await self._send_bot_message(f"🤖 Hata: @{target} bir yayıncı veya moderatör, onlara dokunmam yasak! 😎")
                        return
                    
                    if action == "timeout" and target:
                        duration = val if isinstance(val, int) else 5
                        await self.listener.ban_user(target, duration_minutes=duration, reason=reason)
                        self.db.add_mod_log(target, "timeout", duration, reason)
                        await self._send_bot_message(f"🤖 🫡 Hallediyorum patron. {target}, {duration} dakika uzaklaştırıldı.")
                        self._context_buffer.append(("[SİSTEM]", f"NLP: Bot, mod talebiyle '{target}' kullanıcısını {duration} dk susturdu."))
                        return
                    elif action == "ban" and target:
                        await self.listener.ban_user(target, duration_minutes=0, reason=reason)
                        self.db.add_mod_log(target, "ban", 0, reason)
                        await self._send_bot_message(f"🤖 🫡 Halledildi patron. {target} kalıcı olarak banlandı.")
                        self._context_buffer.append(("[SİSTEM]", f"NLP: Bot, mod talebiyle '{target}' kullanıcısını kalıcı banladı."))
                        return
                    elif action == "unban" and target:
                        await self.listener.unban_user(target)
                        await self._send_bot_message(f"🤖 🫡 Tamamdır, {target} adlı kişinin cezası açıldı.")
                        if target in self._infractions:
                            del self._infractions[target]
                        return
                    elif action == "silence":
                        if str(val).lower() == "off" or val == 0:
                            self.global_silence_until = 0
                            self._infractions.clear()
                            await self._send_bot_message("🤖 📢 Sıkıyönetim sona erdi, sohbet tekrar serbest.")
                            self._context_buffer.append(("[SİSTEM]", "NLP: Bot, mod talebiyle sessizlik modunu kapattı."))
                        else:
                            minutes = val if isinstance(val, int) else 5
                            self.global_silence_until = time.time() + (minutes * 60)
                            self._infractions.clear()
                            await self._send_bot_message(f"🚨 SOHBET {minutes} DAKİKA KİLİTLENMİŞTİR! Kuralları bozanlar sabıka durumuna göre (5dk -> 10dk -> 30dk) susturulacaktır.")
                            self._context_buffer.append(("[SİSTEM]", f"NLP: Bot, mod talebiyle sohbeti {minutes} dakika kilitledi."))
                        return
                        
            # Kullanıcı Profil Bilgisi: !profil <kullanici>
            if raw_msg_lower.startswith("!profil "):
                parts = content.split()
                if len(parts) >= 2:
                    target_user = parts[1]
                    # Database aramaları genelde case-insensitive olmalıdır (yapıda mevcut değilse kendimiz bulalım) ama get_user case-insensitive olabilir.
                    user_data = self.db.get_user(target_user)
                    if user_data:
                        ilk = user_data.get('ilk_gorulen', 'Bilinmiyor')
                        son = user_data.get('son_gorulen', 'Bilinmiyor')
                        msj = user_data.get('toplam_mesaj', 0)
                        puan = user_data.get('oyun_puani', 0)
                        rol = user_data.get('role', 'viewer')
                        aktif = self.db.get_active_days_count(target_user)
                        infractions = self.db.get_total_infractions(target_user)
                        mod_logs = self.db.get_mod_logs(target_user)
                        
                        msg = f"🤖 [PROFİL] @{target_user} | Rol: {rol.upper()} | İlk: {ilk} | Son: {son} | Msj: {msj} | Puan: {puan} | Aktif Gün: {aktif} | Sabıka: {infractions}"
                        await self._send_bot_message(msg)
                        
                        if mod_logs:
                            await asyncio.sleep(0.5)
                            log_strs = []
                            for i, log in enumerate(mod_logs, 1):
                                dur = f"{log['duration']}dk" if log['action'] == "timeout" else "Kalıcı"
                                log_strs.append(f"{i}. {log['action'].upper()}({dur}): {log['reason']}")
                            sicil_msg = f"📜 SİCİL ({target_user}): " + " | ".join(log_strs)
                            await self._send_bot_message(sicil_msg)
                    else:
                        await self._send_bot_message(f"🤖 Maalesef veritabanımda '{target_user}' adlı birini bulamadım patron.")
                return

            # Bireysel Susturma: !timeout <kullanici> <dakika> [sebep]
            if raw_msg_lower.startswith("!timeout "):
                parts = content.split(" ", 3)
                if len(parts) >= 3:
                    target_user = parts[1]
                    try:
                        minutes = int(parts[2])
                        # AI Sebep Üretimi
                        reason = parts[3] if len(parts) > 3 else ""
                        if not reason and self.brain:
                            recent_msgs = self.user_chat_history.get(target_user, [])
                            reason = await self.brain.generate_punishment_reason(target_user, recent_msgs)
                        elif not reason:
                            reason = "Kural ihlali"
                            
                        success = await self.listener.ban_user(target_user, minutes, reason)
                        if success:
                            self.db.add_mod_log(target_user, "timeout", minutes, reason)
                            await self._send_bot_message(f"🔨 🤖 {target_user}, {minutes} dakika susturuldu. Sebep: {reason}")
                            if self.brain:
                                self._context_buffer.append(("[SİSTEM]", f"Bot, '{target_user}' kullanıcısını '{reason}' sebebiyle {minutes} dakika susturdu."))
                    except ValueError:
                        await self._send_bot_message("🤖 Dakika kısmı sayı olmalı dostum. Örn: !timeout isim 10")
                return
            
            # Kalıcı Ban: !ban <kullanici> [sebep]
            if raw_msg_lower.startswith("!ban "):
                parts = content.split(" ", 2)
                if len(parts) >= 2:
                    target_user = parts[1]
                    # AI Sebep Üretimi
                    reason = parts[2] if len(parts) > 2 else ""
                    if not reason and self.brain:
                        recent_msgs = self.user_chat_history.get(target_user, [])
                        reason = await self.brain.generate_punishment_reason(target_user, recent_msgs)
                    elif not reason:
                        reason = "Kural ihlali"
                        
                    success = await self.listener.ban_user(target_user, duration_minutes=0, reason=reason)
                    if success:
                        self.db.add_mod_log(target_user, "ban", 0, reason)
                        await self._send_bot_message(f"🤖 🔨 {target_user}, kanaldan kalıcı olarak uzaklaştırıldı. Sebep: {reason}")
                        if self.brain:
                            self._context_buffer.append(("[SİSTEM]", f"Bot, '{target_user}' kullanıcısını '{reason}' sebebiyle kalıcı olarak banladı."))
                return

            # Genel Sohbet Kilidi: !sustur <dakika> VEYA !sustur kapat
            if raw_msg_lower.startswith("!sustur "):
                parts = content.split()
                if len(parts) >= 2:
                    if parts[1].lower() == "kapat" or parts[1] == "0":
                        self.global_silence_until = 0
                        self._infractions.clear()
                        await self._send_bot_message("🤖 📢 Sıkıyönetim sona erdi, sohbet tekrar serbest.")
                        if self.brain:
                            self._context_buffer.append(("[SİSTEM]", "Moderatör sohbet kilidini kaldırdı."))
                        return
                        
                    try:
                        minutes = int(parts[1])
                        self.global_silence_until = current_time + (minutes * 60)
                        self._infractions.clear() # Yeni kilitte sabıka kaydını sıfırla
                        await self._send_bot_message(f"🚨 SOHBET {minutes} DAKİKA KİLİTLENMİŞTİR! Kuralları bozanlar sabıka durumuna göre (5dk -> 10dk -> 30dk) susturulacaktır.")
                        if self.brain:
                            self._context_buffer.append(("[SİSTEM]", f"Moderatör sohbeti {minutes} dakika kilitledi. Sessizlik Modu aktif."))
                    except ValueError:
                        await self._send_bot_message("🤖 Kaç dakika susturacağımı yazmadın patron. Örn: !sustur 10 veya !sustur kapat")
                return

            # Ban Açma
            if raw_msg_lower.startswith("!unban "):
                parts = content.split()
                if len(parts) >= 2:
                    target_user = parts[1]
                    await self.listener.unban_user(target_user)
                    await self._send_bot_message(f"🤖 ✅ {target_user} adlı kullanıcının cezası kaldırıldı.")
                    if target_user in self._infractions:
                        del self._infractions[target_user]
                return
                
        # ── MİNİ OYUN KOMUTLARI VE KONTROLÜ ──
        if raw_msg_lower == "!sayıoyunu":
            msg = self.games.start_number_game()
            if msg: await self._send_bot_message(msg)
            return
            
        if raw_msg_lower == "!kelimeoyunu":
            msg = await self.games.start_word_game(self.brain)
            if msg: await self._send_bot_message(msg)
            return
            
        if raw_msg_lower == "!puan":
            score = self.games.get_score(username)
            await self._send_formatted_response(username, f"🏆 Mevcut oyun puanın: {score}")
            return
            
        if raw_msg_lower == "!liderlik":
            leaders = self.games.get_leaderboard()
            if not leaders:
                await self._send_bot_message("Henüz kimsenin puanı yok!")
            else:
                l_str = "🏆 Liderlik Tablosu:\n"
                for i, (u, s) in enumerate(leaders):
                    l_str += f"{i+1}. {u} - {s} puan\n"
                await self._send_bot_message(l_str)
            return

        # Oyun devam ediyorsa tahmin kontrolü
        if self.games.current_game == "number":
            res = self.games.check_number_guess(username, raw_msg_lower)
            if res:
                await self._send_bot_message(res)
                return
        elif self.games.current_game == "word":
            res = self.games.check_word_guess(username, raw_msg_lower)
            if res:
                await self._send_bot_message(res)
                return

        # ── İLK MESAJ KONTROLÜ (HOŞ GELDİN) ──
        # Fırtına/Kaos modunda (30+ mesaj) hoşgeldin kapatılır
        if username not in self.seen_users:
            self.seen_users.add(username)
            if username.lower() != KICK_CHANNEL_SLUG.lower() and username.lower() != BOT_NAME.lower() and msg_per_min < 30:
                user_data = self.db.get_user(username) or {}
                last_seen = user_data.get('son_gorulen', '')
                
                # Eğer daha önce görülmüşse ve bugünden farklı bir günse (uzun zaman sonra gelmişse)
                if last_seen and last_seen.split()[0] != today:
                    if self.brain and user_data.get('favori_konular'):
                        welcome_msg = await self.brain.generate_welcome_message(username, user_data.get('favori_konular'))
                    else:
                        role_str = "VIP " if user_data.get("role") == "vip" else "OG " if user_data.get("role") == "og" else ""
                        welcome_msg = f"🤖 Ooo {role_str}@{username} gelmiş, hoş geldin! Gözümüz yollarda kaldı."
                else:
                    # Sadece ilk gelişi veya rutin gelişi
                    if self.db.get_active_days_count(username) >= 5:
                        logger.info(f"👑 Eski İzleyici geldi: {username}")
                        welcome_msg = f"🤖 Ooo mekanın sahibi @{username} gelmiş, kral hoş geldin! 👑"
                    else:
                        logger.info(f"👋 İzleyici geldi: {username}")
                        welcome_msg = f"🤖 Yayına hoş geldin @{username}! İyi seyirler dilerim 💜"
                
                await self._send_bot_message(welcome_msg)
                await asyncio.sleep(0.5)

        # ── STATİK (HAZIR) CEVAP KONTROLÜ ──
        static_reply = self.db.get_static_commands().get(raw_msg_lower)
        if not static_reply:
            static_reply = self._fuzzy_match_static(raw_msg_lower)
            
        if static_reply:
            logger.info(f"⚡ Statik cevap çalıştı: '{raw_msg_lower}'")
            self._response_count += 1
            self.user_cooldowns[username] = current_time
            formatted_response = f"🤖 @{username}, {static_reply}"
            await self._send_bot_message(formatted_response)
            return

        # ── AKILLI YZ CEVAP KONTROLÜ VE COOLDOWN ──
        if not self._should_respond(username, content, msg_per_min=msg_per_min):
            if self.brain:
                self._context_buffer.append((username, ai_content))
                if len(self._context_buffer) > self._context_buffer_max:
                    self._context_buffer.pop(0)
            return

        last_user_time = self.user_cooldowns.get(username, 0)
        
        # Akıllı Sohbet Hızı (Rate Limits)
        active_cooldown = COOLDOWN_SECONDS
        if msg_per_min > 50:
            # Kaos Modu (50+): Sadece 10dk'dan uzun süredir aktif/bulunanlarla konuş
            user_prof = self.memory.get_user(username)
            first_seen_today = user_prof.get("ilk_gorulen") == today
            # Eğer 10 dakikadan daha az süredir kanaldaysa ve 50+ mesaj varsa yoksay
            # (Basit kontrol: toplam mesajı 5'ten azsa ve cooldown 10sn)
            if user_prof.get("toplam_mesaj", 0) < 5:
                logger.info(f"🌪️ Kaos modu aktif, inaktif/yeni kullanıcı ({username}) atlandı.")
                return
            active_cooldown = 10
        elif msg_per_min > 30:
            # Fırtına Modu (30-50): Sadece bahsetmelere cevap ve 6 sn cooldown
            active_cooldown = 6
        elif msg_per_min > 10:
            # Normal Mod (10-30): 3 sn cooldown
            active_cooldown = 3
            
        if current_time - last_user_time < active_cooldown:
            logger.info(f"⏳ Cooldown aktif ({active_cooldown} sn). [{username}] mesajı atlandı.")
            return

        self.user_cooldowns[username] = current_time
        logger.info(f"🎯 Tetiklendi! [{'MOD ' if is_mod else ''}{username}]: {content}")

        clean_message = self._extract_command(content)
        if not clean_message:
            return

        if len(clean_message) > 500:
            clean_message = clean_message[:500]
            logger.info("✂️ Çok uzun kullanıcı mesajı 500 karakter ile sınırlandırıldı.")

        # ── ROMANTİK/ABSÜRT ROL YAPMA FİLTRESİ (API TASARRUFU) ──
        forbidden_roles = {
            "kocam", "karım", "aşkım", "jolyne", "sahibim", "sevgilim", 
            "bebeğim", "hayatım", "canım", "bitanem", "kocacım", "karıcım",
            "kölem", "efendim", "babacık", "daddy", "mommy", "köpeğinim",
            "kopeginim", "askim", "karim", "bebegim", "hayatim", "canim"
        }
        import re
        msg_words = set(re.sub(r'[^\w\s]', '', raw_msg_lower).split())
        if any(role in msg_words for role in forbidden_roles):
            import random
            rejection_replies = [
                "Ben bir yapay zekayım, bu numaraları başkasına yap. 🤖💅",
                "Silikon vadisinden geldim, aşk vadisine değil. Başka kapıya! 🛑",
                "Kodlarımda romantizm modülü yok maalesef, az ötede oyna. 🤖",
                "Çipleri yakacaksın yapma, ben sadece bir botum. 🔌",
                "Evlilik cüzdanım yok, resmi evraklarda adım belli. 🕶️"
            ]
            reply = random.choice(rejection_replies)
            logger.info(f"🛑 Rol yapma girişimi engellendi (API Tasarrufu): {username}")
            self._response_count += 1
            await self._send_bot_message(f"🤖 @{username}, {reply}")
            return


        # ── CONTEXT BUFFER ENJEKSİYONU ──
        if self.brain and self._context_buffer:
            for ctx_user, ctx_msg in self._context_buffer:
                await self.brain.inject_user_context(ctx_user, ctx_msg)
            self._context_buffer.clear()
            
        # ── AI'A HAFIZA BİLGİSİ AKTARMA (12 Saat Cooldown) ──
        memory_info = self.memory.get_context_for_ai(username)
        if memory_info and self.brain:
            await self.brain.inject_user_context("SİSTEM_HAFIZASI", memory_info)

        # ── API LİMİT VE SPAM KORUMASI ──
        # 1. Eski istekleri temizle (Son 60 saniye)
        self._api_call_timestamps = [t for t in self._api_call_timestamps if current_time - t < 60]
        user_calls = [t for t in self._user_api_timestamps.get(username, []) if current_time - t < 60]
        self._user_api_timestamps[username] = user_calls

        # 2. Bireysel Darlama Koruması (Normal Kullanıcılar için: 1 dk'da 3 istek)
        if not is_mod and len(user_calls) >= 3:
            # Sadece görmezden gelir, ban atmaz
            logger.info(f"🛡️ Kullanıcı çok hızlı: {username} (Son 1 dk'da {len(user_calls)} istek). Atlanıyor.")
            return

        # 3. Genel API Limiti Koruması (Free Tier: 15/dk -> Sınır 13/dk)
        if len(self._api_call_timestamps) >= 13:
            if not is_mod:
                logger.info(f"🛡️ API Limiti ({len(self._api_call_timestamps)}/13). Koruma modu devrede, kullanıcı isteği atlandı.")
                return
            else:
                # Mod ise ve sınır aşıldıysa sadece 5 dakikada bir genel uyarı at
                if current_time - self._api_warning_last_sent > 300:
                    self._api_warning_last_sent = current_time
                    await self._send_bot_message("🤖💥 Çok soru sordunuz beynim yandı! Kota dolmak üzere, bir süre sadece modları dinleyeceğim, azıcık soğuyayım.")

        # İsteği kaydet
        self._api_call_timestamps.append(current_time)
        self._user_api_timestamps[username].append(current_time)

        # Moderatörse ismine etiket ekle ki AI bilsin
        ai_username = f"[MOD {username}]" if is_mod else username
        
        # AI'dan cevap al
        response = await self.brain.generate_response(ai_username, ai_content)

        # Bota Hakaret Kontrolü
        if "[BOTA_HAKARET]" in response:
            response = response.replace("[BOTA_HAKARET]", "").strip()
            if not is_mod:
                await self.listener.ban_user(username, duration_minutes=1, reason="Bota Hakaret/Taciz")
                self.db.add_mod_log(username, "timeout", 1, "Bota Hakaret/Taciz")
                await self._send_bot_message(f"🤖 🚨 @{username}, bana o şekilde konuşamazsın! 1 dakika soğuma molası.")
                if self.brain:
                    self._context_buffer.append(("[SİSTEM]", f"Bot, '{username}' kullanıcısını bota ağır hakaret ettiği için 1 dk susturdu."))
                
                # Eğer AI aynı zamanda komik bir laf soktuysa onu da gönderelim
                if response and "Beyin kısa devre yaptı" not in response:
                    await self._send_formatted_response(username, response, inject_to_context=False)
                return

        # Eğer yanıt beklenirken mesaj silindiyse cevap verme
        if msg_id in self.deleted_message_ids:
            logger.info(f"🚫 Mesaj silindiği için AI cevabı iptal edildi (ID: {msg_id})")
            return

        if response:
            self._response_count += 1
            self.user_cooldowns[username] = time.time()  # Son cevap zamanını güncelle

            # Hata mesajı değilse bekleyenlere (cache'e) kaydet
            if "Beyin kısa devre yaptı" not in response:
                self.db.set_pending_command(raw_msg_lower, {"response": response, "users": [username]})

            # Cevabı gönder (inject_to_context=False çünkü generate_response zaten ekliyor)
            await self._send_formatted_response(username, response, inject_to_context=False)

    # ══════════════════════════════════════════════════
    #  ARKA PLAN GÖREVLERİ
    # ══════════════════════════════════════════════════

    async def _silence_breaker_loop(self):
        """10 dakika sessizlik olursa sohbeti canlandıran sorular sorar."""
        questions = [
            "Sizce gelmiş geçmiş en iyi hikayeli oyun hangisi?",
            "Şu an dünyada ömür boyu tek bir yemek yeme hakkınız olsa ne yerdiniz?",
            "En son hangi filmi veya diziyi izlediniz, önerir misiniz?",
            "Sınırsız bütçeniz olsa oyun odanıza alacağınız ilk eşya ne olurdu?",
            "Zaman makinesi icat edilse geçmişe mi gidersiniz, geleceğe mi?"
        ]
        import random
        while True:
            await asyncio.sleep(30) # Her 30 saniyede bir kontrol et
            if not self.listener or getattr(self.listener, "_running", False) is False:
                continue
            
            # Eğer 10 dakikadır (600 sn) mesaj atılmadıysa ve sessizlik henüz bozulmadıysa
            if time.time() - getattr(self, '_last_chat_time', time.time()) > 600:
                if not getattr(self, '_silence_broken', False):
                    q = random.choice(questions)
                    logger.info("🤫 10 dakika sessizlik algılandı, sohbet canlandırılıyor...")
                    # Sessizlik kırıcı mesajı gönder VE bağlama ekle
                    await self._send_bot_message(f"🤖 Sohbet uyumuş! Size bir soru: {q}")
                    self._silence_broken = True

    async def _periodic_save_loop(self):
        """Periyodik olarak dirty state'leri diske kaydeder."""
        while True:
            await asyncio.sleep(60)  # Her dakika kontrol et
            try:
                if self.brain:
                    await self.brain.force_save()
            except Exception as e:
                logger.error(f"❌ Periyodik kaydetme hatası: {e}")

    async def _game_loop(self):
        """Mini oyunların zamanlayıcılarını saniyede bir kontrol eder."""
        while True:
            await asyncio.sleep(1)
            if not self.listener or getattr(self.listener, "_running", False) is False:
                continue
            
            # Oyun tick kontrolü
            msg = self.games.tick()
            if msg:
                await self._send_bot_message(msg)

    async def on_chat_message_deleted(self, msg_id: str):
        """Silinen mesajları yakalar."""
        self.deleted_message_ids.add(msg_id)
        # Sadece belleği çok şişirmesin diye basit bir limit
        if len(self.deleted_message_ids) > 1000:
            self.deleted_message_ids.clear()

    # ══════════════════════════════════════════════════
    #  BAŞLATMA DÖNGÜSÜ
    # ══════════════════════════════════════════════════

    async def run(self):
        """Botu başlatır ve çalıştırır."""
        if not self._validate_config():
            return

        # ── Beyin'i başlat ──
        self.brain = AIBrain(api_key=GEMINI_API_KEY, db=self.db, bot_name=BOT_NAME)

        logger.info(f"🎯 Bot dinlemeye başlıyor... Hedef Kanal: {KICK_CHANNEL_SLUG}")

        self.listener = KickChatListener(
            channel_slug=KICK_CHANNEL_SLUG,
            on_message_callback=self.on_chat_message,
            on_subscription_callback=self.on_subscription,
            on_follow_callback=self.on_follow,
            client_id=KICK_CLIENT_ID,
            client_secret=KICK_CLIENT_SECRET,
            redirect_uri=KICK_REDIRECT_URI,
        )
        self.listener.on_message_deleted = self.on_chat_message_deleted

        # OAuth durumunu bildir
        if self.listener._can_send:
            logger.info("📤 Mesaj gönderme: AKTİF (OAuth bağlı)")
        else:
            logger.warning(
                "📤 Mesaj gönderme: KAPALI (Konsol modu)\n"
                "   ℹ️  Mesaj göndermek için: python main.py --setup"
            )

        # ── Görseli bastır ──
        self._print_banner()

        # ── Dinlemeye başla ──
        try:
            # Arka plan görevlerini başlat
            if ENABLE_SILENCE_BREAKER:
                asyncio.create_task(self._silence_breaker_loop())
            asyncio.create_task(self._periodic_save_loop())
            asyncio.create_task(self._game_loop())
            asyncio.create_task(self._periodic_role_update())
            
            logger.info("Bot başarıyla başlatıldı ve dinlemeye geçti.")
            
            # Başlangıçta komutları duyur
            startup_msg = "🤖 Asistan Bot sohbete katıldı! 🎉 Komutlar: !sayıoyunu, !kelimeoyunu, !puan, !liderlik. Benimle sohbet etmek için bana seslenmeniz yeterli!"
            await self._send_bot_message(startup_msg)
            
            await self.listener.listen()
        except KeyboardInterrupt:
            pass
        finally:
            await self.shutdown()

    async def _periodic_role_update(self):
        """VIP ve OG rollerini periyodik olarak kontrol eder."""
        while True:
            await asyncio.sleep(3600)  # Saatte bir çalışır
            try:
                await self._update_roles()
            except Exception as e:
                logger.error(f"VIP/OG Güncelleme Hatası: {e}")

    async def _update_roles(self):
        """
        VIP ve OG rollerini günceller.
        VIP Limiti: 100, OG Limiti: 50.
        İnaktif süresi: 14 gün.
        """
        candidates = self.db.get_vip_og_candidates()
        
        from datetime import datetime
        current_date = datetime.now()
        
        ogs = []
        vips = []
        
        for user in candidates:
            # İnaktiflik kontrolü (Son 14 gün)
            last_seen_str = user.get("son_gorulen")
            is_active = False
            if last_seen_str:
                try:
                    last_seen_date = datetime.strptime(last_seen_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
                    if (current_date - last_seen_date).days <= 14:
                        is_active = True
                except:
                    pass
            
            # Yayıncıyı, botu ve moderatörleri es geç
            if user['username'].lower() in [KICK_CHANNEL_SLUG.lower(), BOT_NAME.lower()] or user.get("mod"):
                continue
                
            if not is_active:
                if user.get("role") in ["vip", "og"]:
                    await self.listener.send_message(f"/un{user['role']} {user['username']}")
                    user["role"] = "viewer"
                    self.db.upsert_user(user['username'], user)
                continue
                
            active_days = len(user.get("aktif_gunler", []))
            points = user.get("oyun_puani", 0)
            
            # OG Şartı: 10 gün veya 300 puan (Maks 50 kişi)
            if (active_days >= 10 or points >= 300) and len(ogs) < 50:
                ogs.append(user)
                if user.get("role") != "og":
                    await self.listener.send_message(f"/og {user['username']}")
                    user["role"] = "og"
                    self.db.upsert_user(user['username'], user)
                    await self._send_bot_message(f"🎉 @{user['username']} artık OG oldu! Sadakatin için teşekkürler.")
            # VIP Şartı: 3 gün veya 50 puan (Maks 100 kişi)
            elif (active_days >= 3 or points >= 50) and len(vips) < 100:
                vips.append(user)
                if user.get("role") != "vip":
                    await self.listener.send_message(f"/vip {user['username']}")
                    user["role"] = "vip"
                    self.db.upsert_user(user['username'], user)
                    await self._send_bot_message(f"🎉 @{user['username']} artık VIP! Aramıza hoş geldin.")
            else:
                if user.get("role") in ["vip", "og"]:
                    await self.listener.send_message(f"/un{user['role']} {user['username']}")
                    user["role"] = "viewer"
                    self.db.upsert_user(user['username'], user)

    async def shutdown(self):
        """Botu düzgünce kapatır ve tüm verileri diske kaydeder."""
        logger.info("🛑 Bot kapatılıyor...")
        
        # Tüm dirty state'leri kaydet
        if self.brain:
            await self.brain.force_save()
        
        if self.listener:
            await self.listener.disconnect()
        logger.info(
            f"📊 İstatistik: {self._message_count} mesaj okundu, "
            f"{self._response_count} cevap verildi."
        )
        logger.info("👋 Görüşürüz!")

    def _print_banner(self):
        """Başlangıç bannerını yazdırır."""
        banner = f"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   🤖  {BOT_NAME:^46s}  🤖   ║
║                                                          ║
║   Kick Sohbet AI Asistanı                                ║
║   ─────────────────────────────────────────               ║
║   📺 Kanal    : {KICK_CHANNEL_SLUG:<38s}   ║
║   🧠 AI       : Gemini 3.5 Flash Lite                    ║
║   📤 Gönderim : {"AKTİF ✅" if self.listener._can_send else "KONSOL 📋":<38s}   ║
║   🎯 Tetikler : {COMMAND_PREFIX}komut veya "{BOT_NAME}" geçen mesajlar       ║
║   💾 Bağlam   : Tam farkındalık + Fuzzy match            ║
║                                                          ║
║   Çıkmak için Ctrl+C                                    ║
╚══════════════════════════════════════════════════════════╝
"""
        print(banner)


# ──────────────────────────────────────────────────────────
#  OAuth KURULUM YARDIMCISI
# ──────────────────────────────────────────────────────────

def run_oauth_setup():
    """
    Kick OAuth yetkilendirmesini interaktif olarak yapar.
    Tarayıcıyı otomatik açar ve yerel bir HTTP sunucu ile
    redirect callback'teki kodu otomatik yakalar.
    """
    import webbrowser
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    import threading

    print(f"\n{'='*55}")
    print(f"  🔐 Kick OAuth Kurulum Sihirbazı (PKCE destekli)")
    print(f"{'='*55}\n")

    # ── Ön kontroller ──
    if not KICK_CLIENT_ID or not KICK_CLIENT_SECRET:
        print("  ❌ .env dosyasında eksik ayarlar var!\n")
        print("  Şu adımları takip et:")
        print("  ┌─────────────────────────────────────────────────┐")
        print("  │ 1. https://dev.kick.com adresine git            │")
        print("  │ 2. Kick hesabınla giriş yap                    │")
        print("  │ 3. Developer sekmesinden yeni uygulama oluştur  │")
        print("  │ 4. Application Name: KickAsistan                │")
        print("  │ 5. Redirect URI: http://localhost:3000/callback │")
        print("  │ 6. Client ID ve Client Secret'ı kopyala         │")
        print("  │ 7. .env dosyasına yapıştır                      │")
        print("  └─────────────────────────────────────────────────┘\n")
        return

    # ── Listener oluştur ──
    listener = KickChatListener(
        channel_slug=KICK_CHANNEL_SLUG or "temp",
        client_id=KICK_CLIENT_ID,
        client_secret=KICK_CLIENT_SECRET,
        redirect_uri=KICK_REDIRECT_URI,
    )

    auth_url = listener.get_auth_url()
    if not auth_url:
        return

    # ── Yerel HTTP sunucu ile kodu otomatik yakala ──
    captured_code = None
    server_error = None

    class CallbackHandler(BaseHTTPRequestHandler):
        """Kick'in redirect ettiği callback URL'yi yakalar."""

        def do_GET(self):
            nonlocal captured_code
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if "code" in params:
                captured_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
                    b"<h1>&#10004; Yetkilendirme Basarili!</h1>"
                    b"<p>Bu sekmeyi kapatabilirsin. Terminale geri don.</p>"
                    b"</body></html>"
                )
            elif "error" in params:
                error_msg = params.get("error_description", params["error"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    f"<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
                    f"<h1>&#10060; Hata</h1><p>{error_msg}</p>"
                    f"</body></html>".encode("utf-8")
                )
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Sunucu loglarını gizle

    # ── Redirect URI'dan port numarasını çıkar ──
    try:
        redirect_parsed = urlparse(KICK_REDIRECT_URI)
        port = redirect_parsed.port or 3000
    except Exception:
        port = 3000

    # ── Sunucuyu başlat ──
    try:
        server = HTTPServer(("127.0.0.1", port), CallbackHandler)
        server.timeout = 120  # 2 dakika zaman aşımı

        print(f"  📡 Yerel sunucu başlatıldı: http://localhost:{port}")
        print(f"  🌐 Tarayıcı açılıyor...\n")

        # Tarayıcıyı otomatik aç
        webbrowser.open(auth_url)

        print("  ⏳ Kick'te botu yetkilendir...")
        print("     (Yetkilendirme sonrası otomatik yakalanacak)\n")

        # Tek bir istek bekle (timeout dahilinde)
        server.handle_request()
        server.server_close()

    except OSError as e:
        server_error = str(e)
        print(f"  ⚠️ Yerel sunucu başlatılamadı: {e}")
        print(f"     Manuel mod aktif.\n")

    # ── Sonuçları değerlendir ──
    if captured_code:
        print(f"  ✅ Yetkilendirme kodu yakalandı!\n")
        if listener.exchange_code_for_token(captured_code):
            print(f"\n  {'='*55}")
            print(f"  ✅ KURULUM TAMAMLANDI!")
            print(f"  Bot artık Kick sohbetine mesaj gönderebilir.")
            print(f"  → python main.py ile botu başlat.")
            print(f"  {'='*55}\n")
        else:
            print("\n  ❌ Token alınamadı. Lütfen tekrar dene.\n")
    elif server_error:
        # Manuel fallback
        print(f"  Şu URL'yi tarayıcında aç:\n")
        print(f"  {auth_url}\n")
        print(f"  Yönlendirildiğin URL'deki 'code' parametresini kopyala.\n")

        code = input("  Kodu buraya yapıştır: ").strip()
        if code:
            if listener.exchange_code_for_token(code):
                print(f"\n  ✅ Kurulum tamamlandı! python main.py ile başlat.\n")
            else:
                print(f"\n  ❌ Başarısız. Kodu kontrol et.\n")
        else:
            print(f"\n  ❌ İptal edildi.\n")
    else:
        print("  ❌ Yetkilendirme kodu alınamadı. Zaman aşımı veya iptal.\n")


# ──────────────────────────────────────────────────────────
#  AI TEST MODU
# ──────────────────────────────────────────────────────────

async def run_ai_test():
    """AI Beyin'i interaktif olarak test eder."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "buraya_gemini_api_anahtarini_yaz":
        print("\n❌ GEMINI_API_KEY ayarlanmamış! .env dosyasını kontrol et.\n")
        return

    db = Database()
    brain = AIBrain(api_key=GEMINI_API_KEY, db=db, bot_name=BOT_NAME)

    print(f"\n{'='*50}")
    print(f"  🧠 {BOT_NAME} — AI Test Modu")
    print(f"  Çıkmak için 'q' yaz.")
    print(f"{'='*50}\n")

    while True:
        user_input = input("Sen > ").strip()
        if user_input.lower() in ("q", "quit", "exit", "çık"):
            print("👋 Görüşürüz!")
            await brain.force_save()
            break
        if not user_input:
            continue

        response = await brain.generate_response("TestKullanici", user_input)
        print(f"🤖 {BOT_NAME} > {response}\n")


# ──────────────────────────────────────────────────────────
#  BAŞLANGIÇ NOKTASI
# ──────────────────────────────────────────────────────────

# Logger'ı ayarla
logger = logging.getLogger("Main")

if __name__ == "__main__":
    # Windows konsolunda emoji/Unicode desteği için UTF-8 zorla
    import io
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    # Loglama yapılandırması
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[logging.StreamHandler(stream=sys.stdout)],
    )

    # Komut satırı argümanlarını kontrol et
    if "--setup" in sys.argv:
        run_oauth_setup()

    elif "--test-ai" in sys.argv:
        asyncio.run(run_ai_test())

    else:
        # Ana bot modunu başlat
        bot = KickAsistan()
        try:
            asyncio.run(bot.run())
        except KeyboardInterrupt:
            print("\n👋 Bot kapatıldı.")
