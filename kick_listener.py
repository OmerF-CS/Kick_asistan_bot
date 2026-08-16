"""
╔══════════════════════════════════════════════════════════╗
║              KICK LISTENER (Kulak Modülü)                ║
║  Kick sohbetine Pusher WebSocket ile bağlanıp mesajları  ║
║  dinler. İsteğe bağlı olarak mesaj gönderir.             ║
╚══════════════════════════════════════════════════════════╝
"""

import json
import asyncio
import logging
import time
import os
import hashlib
import base64
import secrets
from typing import Callable, Awaitable, Optional, Dict, List, Any
import websockets
from curl_cffi import requests as cffi_requests

logger = logging.getLogger("KickListener")


class KickChatListener:
    """
    Kick.com sohbet dinleyicisi.

    Pusher WebSocket üzerinden belirtilen kanalın sohbet odasına bağlanır,
    gelen mesajları yakalar ve bir callback fonksiyonuna iletir.

    Ayrıca Kick'in resmi API'si üzerinden mesaj gönderme desteği sunar
    (OAuth 2.1 kimlik doğrulaması gerektirir).
    """

    # Kick'in kullandığı Pusher WebSocket adresi
    PUSHER_URL = (
        "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
        "?protocol=7&client=js&version=8.4.0-rc2&flash=false"
    )

    # Kick API adresleri
    KICK_CHANNEL_API = "https://kick.com/api/v2/channels"
    KICK_CHAT_API = "https://api.kick.com/public/v1/chat"
    KICK_TOKEN_URL = "https://id.kick.com/oauth/token"
    KICK_AUTH_URL = "https://id.kick.com/oauth/authorize"

    def __init__(
        self,
        channel_slug: str,
        on_message_callback: Callable[[str, str, str, bool], Awaitable[None]] | None = None,
        on_subscription_callback: Callable[[str], Awaitable[None]] | None = None,
        on_follow_callback: Callable[[str], Awaitable[None]] | None = None,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "http://localhost:3000/callback",
    ):
        """
        Args:
            channel_slug:       Kick kanal slug'ı (URL'deki isim)
            on_message_callback: Mesaj geldiğinde çağrılacak async fonksiyon
                                 Signature: async fn(username, content, msg_id, is_mod)
            on_subscription_callback: Abone olunduğunda çağrılacak async fonksiyon
            client_id:          Kick OAuth Client ID (mesaj göndermek için)
            client_secret:      Kick OAuth Client Secret (mesaj göndermek için)
            redirect_uri:       OAuth yönlendirme adresi
        """
        self.channel_slug = channel_slug
        self.chatroom_id = None
        self.broadcaster_user_id = None
        self.socket_id = None
        self.ws = None
        self.on_message = on_message_callback
        self.on_subscription = on_subscription_callback
        self.on_follow = on_follow_callback
        self.on_message_deleted = None
        self._running = False
        self._reconnect_delay = 5   # Saniye cinsinden yeniden bağlanma bekleme süresi
        self._max_reconnect_delay = 60

        # OAuth ayarları
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expiry: float = 0
        self._can_send = False

        # PKCE parametreleri (OAuth 2.1 zorunlu)
        self._code_verifier = None

        # Token dosyası varsa yükle
        self._token_file = os.path.join(os.path.dirname(__file__), "kick_tokens.json")
        self._load_tokens()

        # Moderasyon için username -> user_id önbelleği
        self.user_id_cache: dict[str, int] = {}

    # ══════════════════════════════════════════════════
    #  BAĞLANTI ve DİNLEME
    # ══════════════════════════════════════════════════

    def fetch_chatroom_id(self) -> int | None:
        """
        Cloudflare korumasını aşarak kanalın chatroom ID'sini alır.
        curl_cffi kütüphanesi tarayıcı TLS parmak izini taklit eder.
        """
        try:
            url = f"{self.KICK_CHANNEL_API}/{self.channel_slug}"
            logger.info(f"📡 Kanal bilgisi alınıyor: {url}")

            resp = cffi_requests.get(url, impersonate="chrome")

            if resp.status_code == 200:
                data = resp.json()
                self.chatroom_id = data.get("chatroom", {}).get("id")
                self.broadcaster_user_id = data.get("user_id") or data.get("user", {}).get("id")
                logger.info(f"✅ Chatroom ID: {self.chatroom_id} | Yayıncı ID: {self.broadcaster_user_id}")
                return self.chatroom_id
            else:
                logger.error(f"❌ API yanıt kodu: {resp.status_code}")
                return None

        except Exception as e:
            logger.error(f"❌ Chatroom ID alınamadı: {e}")
            return None

    async def connect(self):
        """Pusher WebSocket'e bağlanır ve chatroom'a abone olur."""
        if not self.chatroom_id:
            if not self.fetch_chatroom_id():
                raise ConnectionError(
                    f"'{self.channel_slug}' kanalının Chatroom ID'si alınamadı! "
                    "Kanal slug'ının doğru olduğundan emin ol."
                )

        logger.info("🔌 Pusher WebSocket'e bağlanılıyor...")
        self.ws = await websockets.connect(self.PUSHER_URL)

        # ── 1. Bağlantı onayını al ──
        raw = await self.ws.recv()
        data = json.loads(raw)

        if data.get("event") == "pusher:connection_established":
            conn_data = json.loads(data["data"])
            self.socket_id = conn_data.get("socket_id")
            logger.info(f"✅ Pusher'a bağlanıldı! Socket ID: {self.socket_id}")
        else:
            logger.warning(f"⚠️ Beklenmeyen ilk mesaj: {data}")

        # ── 2. Chatroom ve Kanal'a subscribe ol ──
        # Chat mesajları için:
        await self.ws.send(json.dumps({
            "event": "pusher:subscribe",
            "data": {"channel": f"chatrooms.{self.chatroom_id}.v2"},
        }))
        logger.info(f"📨 chatrooms.{self.chatroom_id}.v2 kanalına abone olunuyor...")

        # Abonelik (Sub) ve Kanal eventleri için:
        await self.ws.send(json.dumps({
            "event": "pusher:subscribe",
            "data": {"channel": f"channel.{self.broadcaster_user_id}"},
        }))
        logger.info(f"📨 channel.{self.broadcaster_user_id} kanalına abone olunuyor...")
        
        logger.info("✅ Tüm odalara başarıyla bağlanıldı! Eventler dinleniyor...")

        # Yeniden bağlanma gecikmesini sıfırla
        self._reconnect_delay = 5

    async def _keepalive(self):
        """Bağlantıyı canlı tutmak için her 30 saniyede bir ping gönderir."""
        while self._running:
            try:
                await asyncio.sleep(30)
                if self.ws and not self.ws.closed:
                    ping = json.dumps({"event": "pusher:ping", "data": {}})
                    await self.ws.send(ping)
                    logger.debug("💓 Ping gönderildi")
            except Exception:
                break

    async def listen(self):
        """
        Ana dinleme döngüsü. Sohbet mesajlarını yakalar ve
        callback fonksiyonuna yönlendirir.

        Bağlantı koparsa otomatik olarak yeniden bağlanır.
        """
        self._running = True

        while self._running:
            try:
                await self.connect()
                keepalive_task = asyncio.create_task(self._keepalive())

                try:
                    while self._running:
                        raw = await self.ws.recv()
                        await self._handle_event(raw)
                except websockets.ConnectionClosed as e:
                    logger.warning(f"⚡ Bağlantı koptu: {e}. Yeniden bağlanılıyor...")
                finally:
                    keepalive_task.cancel()
                    try:
                        await keepalive_task
                    except asyncio.CancelledError:
                        pass

            except ConnectionError as e:
                logger.error(f"❌ {e}")
                self._running = False
                break
            except Exception as e:
                logger.error(f"❌ Beklenmeyen hata: {e}")

            # Yeniden bağlanma bekleme süresi (exponential backoff)
            if self._running:
                logger.info(f"⏳ {self._reconnect_delay}s sonra yeniden denenecek...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _handle_event(self, raw: str):
        """Gelen Pusher event'lerini ayrıştırır."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        event = data.get("event", "")

        if event == "App\\Events\\ChatMessageEvent":
            msg_data = json.loads(data.get("data", "{}"))

            username = msg_data.get("sender", {}).get("username", "Anonim")
            user_id = msg_data.get("sender", {}).get("id")
            content = msg_data.get("content", "")
            msg_id = msg_data.get("id", "")
            
            replied_user = None
            if msg_data.get("type") == "reply" and "metadata" in msg_data:
                replied_user = msg_data["metadata"].get("original_sender", {}).get("username")
            
            if user_id:
                self.user_id_cache[username.lower()] = int(user_id)
            
            # Moderatör kontrolü
            badges = msg_data.get("sender", {}).get("identity", {}).get("badges", [])
            is_mod = any(b.get("type") in ["moderator", "broadcaster", "staff"] for b in badges)

            logger.info(f"💬 [{'MOD ' if is_mod else ''}{username}]: {content}" + (f" (Yanıt: @{replied_user})" if replied_user else ""))

            if self.on_message:
                await self.on_message(username, content, msg_id, is_mod, replied_user)

        elif event == "pusher:pong":
            logger.debug("💓 Pong alındı")

        elif event == "App\\Events\\SubscriptionEvent":
            try:
                sub_data = json.loads(data.get("data", "{}"))
                username = sub_data.get("username", "Biri")
                logger.info(f"⭐ Yeni Abonelik: {username}")
                if self.on_subscription:
                    await self.on_subscription(username)
            except Exception as e:
                logger.error(f"Abonelik eventi ayrıştırılamadı: {e}")

        elif "Follow" in event:
            try:
                sub_data = json.loads(data.get("data", "{}"))
                username = sub_data.get("username") or sub_data.get("user", {}).get("username")
                
                # Eğer Kick ismi gizlediyse (sadece sayı verdiyse) "Biri" olarak işaretle
                username = username or "Biri"
                
                logger.info(f"💖 Yeni Takipçi: {username}")
                if self.on_follow:
                    await self.on_follow(username)
            except Exception as e:
                logger.error(f"Takip eventi ayrıştırılamadı: {e}")

        elif event == "App\\Events\\ChatMessageDeletedEvent":
            try:
                del_data = json.loads(data.get("data", "{}"))
                msg_id = del_data.get("message", {}).get("id") or del_data.get("id")
                logger.debug(f"🗑️ Bir mesaj silindi (ID: {msg_id})")
                if self.on_message_deleted and msg_id:
                    await self.on_message_deleted(msg_id)
            except Exception as e:
                logger.error(f"Mesaj silme eventi ayrıştırılamadı: {e}")

        elif event.startswith("pusher"):
            logger.debug(f"📡 Pusher olayı: {event}")

    async def disconnect(self):
        """Bağlantıyı düzgünce kapatır."""
        self._running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            logger.info("🔌 WebSocket bağlantısı kapatıldı.")

    # ══════════════════════════════════════════════════
    #  MESAJ GÖNDERME (Kick Resmi API — OAuth 2.1)
    # ══════════════════════════════════════════════════

    def _load_tokens(self):
        """Daha önce kaydedilmiş OAuth tokenlarını yükler."""
        if os.path.exists(self._token_file):
            try:
                with open(self._token_file, "r", encoding="utf-8-sig") as f:
                    tokens = json.load(f)
                self.access_token = tokens.get("access_token")
                self.refresh_token = tokens.get("refresh_token")
                self.token_expiry = tokens.get("expiry", 0)
                if self.access_token:
                    self._can_send = True
                    logger.info("🔑 Kaydedilmiş OAuth tokenları yüklendi.")
            except Exception as e:
                logger.warning(f"⚠️ Token dosyası okunamadı: {e}")

    def _save_tokens(self):
        """OAuth tokenlarını dosyaya kaydeder."""
        try:
            with open(self._token_file, "w", encoding="utf-8-sig") as f:
                json.dump(
                    {
                        "access_token": self.access_token,
                        "refresh_token": self.refresh_token,
                        "expiry": self.token_expiry,
                    },
                    f,
                    indent=2,
                )
            logger.info("💾 OAuth tokenları kaydedildi.")
        except Exception as e:
            logger.error(f"❌ Token kaydedilemedi: {e}")

    def _refresh_access_token(self) -> bool:
        """Süresi dolmuş access token'ı refresh token ile yeniler."""
        if not self.refresh_token or not self.client_id or not self.client_secret:
            return False
        try:
            resp = cffi_requests.post(
                self.KICK_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                },
                impersonate="chrome",
            )
            if resp.status_code == 200:
                token_data = resp.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token", self.refresh_token)
                self.token_expiry = time.time() + token_data.get("expires_in", 3600)
                self._can_send = True
                self._save_tokens()
                logger.info("🔄 Access token yenilendi.")
                return True
            else:
                logger.error(f"❌ Token yenileme başarısız: {resp.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Token yenileme hatası: {e}")
            return False

    async def send_message(self, message: str, _retry: bool = False) -> bool:
        """
        Kick sohbetine mesaj gönderir.

        OAuth kimlik doğrulaması yapılandırılmamışsa sadece konsola yazar.

        Args:
            message: Gönderilecek mesaj metni

        Returns:
            Başarılı ise True, değilse False
        """
        if not self._can_send:
            logger.warning(
                f"📤 [KONSOL MODU] Bot yanıtı: {message}\n"
                "   ℹ️  Mesaj göndermek için OAuth ayarlarını yapılandır."
            )
            return False

        # Token süresi dolduysa yenile
        if time.time() >= self.token_expiry:
            if not self._refresh_access_token():
                logger.error("❌ Token yenilenemedi, mesaj gönderilemedi.")
                return False

        # Güvenlik: Kick API maksimum 500 karakter kabul eder. (Emojiler vs için 480 güvenlidir)
        if len(message) > 480:
            last_space = message.rfind(" ", 0, 477)
            if last_space == -1:
                last_space = 477
            message = message[:last_space] + "..."

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            if not self.broadcaster_user_id:
                logger.error("❌ Yayıncı ID'si henüz alınmadığı için mesaj gönderilemiyor.")
                return False

            payload = {
                "broadcaster_user_id": int(self.broadcaster_user_id),
                "content": message,
                "type": "user"
            }

            resp = await asyncio.to_thread(
                cffi_requests.post,
                self.KICK_CHAT_API,
                headers=headers,
                json=payload,
                impersonate="chrome",
            )

            if resp.status_code in (200, 201):
                logger.info(f"📤 Mesaj gönderildi: {message}")
                return True
            elif resp.status_code == 401:
                # Token geçersiz, yenilemeyi dene
                if not _retry and self._refresh_access_token():
                    return await self.send_message(message, _retry=True)
                return False
            else:
                logger.error(f"❌ Mesaj gönderilemedi: HTTP {resp.status_code} — {resp.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Mesaj gönderme hatası: {e}")
            return False

    async def _get_user_id(self, username: str) -> Optional[int]:
        """Kullanıcı adından ID'sini bulur (Önbellek destekli)."""
        username_lower = username.lstrip("@").lower()
        if username_lower in self.user_id_cache:
            return self.user_id_cache[username_lower]
            
        try:
            url = f"{self.KICK_CHANNEL_API}/{username_lower}"
            resp = await asyncio.to_thread(cffi_requests.get, url, impersonate="chrome")
            if resp.status_code == 200:
                data = resp.json()
                user_id = data.get("user_id") or data.get("user", {}).get("id")
                if user_id:
                    self.user_id_cache[username_lower] = int(user_id)
                    return int(user_id)
        except Exception as e:
            logger.error(f"❌ {username} için ID alınamadı: {e}")
        return None

    async def ban_user(self, banned_username: str, duration_minutes: int = 0, reason: str = "", _retry: bool = False) -> bool:
        """
        Kullanıcıyı kanaldan resmi Kick Moderasyon API'si ile banlar veya timeout atar.
        """
        banned_user_id = await self._get_user_id(banned_username)
        if not banned_user_id:
            logger.error(f"❌ {banned_username} ID'si bulunamadığı için ban atılamadı.")
            return False

        if not self.broadcaster_user_id:
            logger.error("❌ Yayıncı ID'si bilinmiyor, ban atılamadı.")
            return False

        # Token kontrolü
        if time.time() >= self.token_expiry:
            if not self._refresh_access_token():
                return False

        try:
            url = "https://api.kick.com/public/v1/moderation/bans"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "broadcaster_user_id": int(self.broadcaster_user_id),
                "user_id": banned_user_id,
                "reason": reason if reason else "Moderator action via bot"
            }
            
            if duration_minutes > 0:
                payload["duration"] = duration_minutes
                
            resp = await asyncio.to_thread(
                cffi_requests.post,
                url,
                headers=headers,
                json=payload,
                impersonate="chrome"
            )
            
            if resp.status_code in (200, 201):
                action = f"{duration_minutes} dk Susturuldu" if duration_minutes > 0 else "Kalıcı Banlandı"
                logger.info(f"🔨 [Mod İşlemi Resmi API] {banned_username} -> {action}")
                return True
            elif resp.status_code == 401:
                if not _retry and self._refresh_access_token():
                    return await self.ban_user(banned_username, duration_minutes, reason, _retry=True)
                logger.error(f"❌ Ban yetkisi reddedildi (401). OAuth'da 'moderation:ban' izni var mı? — {resp.text}")
                return False
            else:
                logger.error(f"❌ Ban isteği başarısız: HTTP {resp.status_code} — {resp.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Ban gönderme hatası: {e}")
            return False

    async def unban_user(self, banned_username: str, _retry: bool = False) -> bool:
        """
        Kullanıcının banını veya timeout'unu resmi Kick Moderasyon API'si ile kaldırır.
        """
        banned_user_id = await self._get_user_id(banned_username)
        if not banned_user_id:
            logger.error(f"❌ {banned_username} ID'si bulunamadığı için ban açılamadı.")
            return False

        if not self.broadcaster_user_id:
            logger.error("❌ Yayıncı ID'si bilinmiyor, ban açılamadı.")
            return False

        if time.time() >= self.token_expiry:
            if not self._refresh_access_token():
                return False

        try:
            url = "https://api.kick.com/public/v1/moderation/bans"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            payload = {
                "broadcaster_user_id": int(self.broadcaster_user_id),
                "user_id": banned_user_id
            }
            
            resp = await asyncio.to_thread(
                cffi_requests.delete,
                url,
                headers=headers,
                json=payload,
                impersonate="chrome"
            )
            
            if resp.status_code in (200, 201):
                logger.info(f"🔓 [Mod İşlemi Resmi API] {banned_username} -> Banı Açıldı")
                return True
            elif resp.status_code == 401:
                if not _retry and self._refresh_access_token():
                    return await self.unban_user(banned_username, _retry=True)
                logger.error(f"❌ Ban açma yetkisi reddedildi (401).")
                return False
            else:
                logger.error(f"❌ Ban açma isteği başarısız: HTTP {resp.status_code} — {resp.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Ban açma hatası: {e}")
            return False

    # ══════════════════════════════════════════════════
    #  OAuth KURULUM YARDIMCISI (PKCE destekli)
    # ══════════════════════════════════════════════════

    def _generate_pkce(self) -> tuple[str, str]:
        """
        PKCE (Proof Key for Code Exchange) parametrelerini üretir.
        Kick OAuth 2.1 bunu zorunlu tutuyor (S256 metodu).

        Returns:
            (code_verifier, code_challenge) tuple'ı
        """
        # 64 byte rastgele code_verifier üret (base64url encoded → ~86 karakter)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")

        # SHA-256 hash ile code_challenge oluştur
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        return code_verifier, code_challenge

    def get_auth_url(self) -> str | None:
        """
        OAuth yetkilendirme URL'sini üretir (PKCE dahil).
        Bu URL'yi tarayıcıda açıp botu yetkilendirmen gerekir.

        Returns:
            Yetkilendirme URL'si veya None
        """
        if not self.client_id:
            logger.error("❌ KICK_CLIENT_ID ayarlanmamış!")
            return None

        # PKCE parametrelerini üret ve sakla
        self._code_verifier, code_challenge = self._generate_pkce()

        # Güvenlik için state parametresi
        state = secrets.token_urlsafe(32)

        url = (
            f"{self.KICK_AUTH_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&scope=user:read+chat:write+chat:read+channel:read+channel:manage:bans+channel:manage:timeouts+moderation:ban"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
            f"&state={state}"
        )
        return url

    def exchange_code_for_token(self, auth_code: str) -> bool:
        """
        OAuth yetkilendirme kodunu access token ile değiştirir.
        PKCE code_verifier'ı da gönderir (Kick zorunlu tutuyor).

        Args:
            auth_code: Tarayıcıdan alınan yetkilendirme kodu

        Returns:
            Başarılı ise True
        """
        if not self._code_verifier:
            logger.error("❌ PKCE code_verifier bulunamadı! Önce get_auth_url() çağrılmalı.")
            return False

        try:
            resp = cffi_requests.post(
                self.KICK_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": auth_code,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": self._code_verifier,
                },
                impersonate="chrome",
            )
            if resp.status_code == 200:
                token_data = resp.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token")
                self.token_expiry = time.time() + token_data.get("expires_in", 3600)
                self._can_send = True
                self._code_verifier = None  # Kullanıldı, temizle
                self._save_tokens()
                logger.info("✅ OAuth yetkilendirme başarılı! Mesaj gönderme aktif.")
                return True
            else:
                logger.error(f"❌ Token alınamadı: {resp.status_code} — {resp.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Token değişim hatası: {e}")
            return False


# ──────────────────────────────────────────────────────────
#  BAĞIMSIZ TEST MODU
#  Bu dosyayı tek başına çalıştırarak Kick bağlantısını test et:
#     python kick_listener.py
# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    channel_slug = os.getenv("KICK_CHANNEL_SLUG")

    if not channel_slug or channel_slug == "buraya_kanal_adini_yaz":
        print("\n❌ HATA: .env dosyasındaki KICK_CHANNEL_SLUG değerini doldurman gerek!")
        print("   → Kick kanalının URL'sindeki ismi yaz (ör: kick.com/kanal_adin)\n")
        exit(1)

    async def print_message(username, content, msg_id):
        """Test için mesajları konsola basar."""
        print(f"  💬 [{username}]: {content}")

    listener = KickChatListener(
        channel_slug=channel_slug,
        on_message_callback=print_message,
    )

    print(f"\n{'='*50}")
    print(f"  👂 Kick Listener — Test Modu")
    print(f"  Kanal: {channel_slug}")
    print(f"  Çıkmak için Ctrl+C")
    print(f"{'='*50}\n")

    try:
        asyncio.run(listener.listen())
    except KeyboardInterrupt:
        print("\n👋 Dinleyici kapatıldı.")
