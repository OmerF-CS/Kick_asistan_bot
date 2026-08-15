import os
import time
import datetime
import logging

logger = logging.getLogger("Memory")

class UserMemory:
    def __init__(self, db):
        self.db = db
        # Injection cooldown (12 saat = 43200 saniye)
        self.INJECTION_COOLDOWN = 12 * 60 * 60

    def get_user(self, username: str) -> dict:
        user = self.db.get_user(username)
        if not user:
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            user = {
                "ilk_gorulen": today,
                "son_gorulen": today,
                "toplam_mesaj": 0,
                "aktif_gunler": [today],
                "favori_konular": [],
                "en_cok_sorulan": "",
                "oyun_puani": 0,
                "mod": False,
                "son_mesajlar": [],
                "last_injected": 0  # Son AI'ya aktarım zamanı (timestamp)
            }
            self.db.upsert_user(username, user)
        return user

    def log_message(self, username: str, content: str, is_mod: bool, current_score: int = 0):
        """Kullanıcının her mesajında profilini günceller."""
        user = self.get_user(username)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        user["son_gorulen"] = today
        user["toplam_mesaj"] += 1
        user["mod"] = is_mod
        user["oyun_puani"] = current_score
        
        if today not in user["aktif_gunler"]:
            user["aktif_gunler"].append(today)
            
        # Son mesajları tut (en fazla 5)
        user["son_mesajlar"].append(content)
        if len(user["son_mesajlar"]) > 5:
            user["son_mesajlar"].pop(0)
            
        self.db.upsert_user(username, user)

    def get_context_for_ai(self, username: str) -> str | None:
        """
        AI'ya verilecek profil bilgisini hazırlar. 
        Sadece 12 saat geçtikten sonra yeni bir bilgi döner.
        Geçmediyse None döner.
        """
        user = self.get_user(username)
        now = time.time()
        
        if now - user.get("last_injected", 0) > self.INJECTION_COOLDOWN:
            user["last_injected"] = now
            self.db.upsert_user(username, user)
            
            days_active = len(user["aktif_gunler"])
            mod_str = " (MOD)" if user["mod"] else ""
            msg_count = user["toplam_mesaj"]
            score = user["oyun_puani"]
            
            return f"Kullanıcı Bilgisi: {username}{mod_str}, {days_active} gündür kanalda, {msg_count} mesaj yazmış. Oyun puanı: {score}."
        
        return None
