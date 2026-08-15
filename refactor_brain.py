import os

brain_file = os.path.join(os.path.dirname(__file__), "ai_brain.py")

with open(brain_file, "r", encoding="utf-8") as f:
    content = f.read()

# Add database import and pass it to init
content = content.replace(
    "def __init__(self, api_key: str, bot_name: str = \"KickAsistan\"):", 
    "def __init__(self, api_key: str, db, bot_name: str = \"KickAsistan\"):"
)
content = content.replace(
    "        self.api_key = api_key",
    "        self.api_key = api_key\n        self.db = db"
)

# Remove history_file
content = content.replace(
    '        self.history_file = os.path.join(os.path.dirname(__file__), "chat_history.json")\n',
    ''
)

old_load_history = """    def _load_history(self):
        \"\"\"Kayıtlı sohbet geçmişini JSON dosyasından yükler.\"\"\"
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Disk'te DISK_WINDOW kadar tutulur ama belleğe yüklüyoruz
                if len(data) > self.DISK_WINDOW:
                    data = data[-self.DISK_WINDOW:]
                    
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
        return None"""

new_load_history = """    def _load_history(self):
        \"\"\"Kayıtlı sohbet geçmişini Veritabanından yükler.\"\"\"
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
        return None"""

content = content.replace(old_load_history, new_load_history)

old_save_history = """    def _save_history(self):
        \"\"\"Sohbet geçmişini JSON dosyasına kaydeder (debounced).\"\"\"
        try:
            history = self.chat_session.get_history()
            if not history:
                return
                
            # Disk'e son DISK_WINDOW mesajı kaydet
            if len(history) > self.DISK_WINDOW:
                history = history[-self.DISK_WINDOW:]
                
            data = []
            for h in history:
                parts_data = []
                for p in h.parts:
                    if hasattr(p, 'text') and p.text:
                        parts_data.append({"text": p.text})
                
                if parts_data:
                    data.append({
                        "role": h.role,
                        "parts": parts_data
                    })
            
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self._ai_response_count = 0
            self._last_save_time = time.time()
            self._history_dirty = False
            logger.debug("💾 Sohbet geçmişi diske kaydedildi.")
        except Exception as e:
            logger.error(f"❌ Geçmiş kaydedilirken hata: {e}")"""

new_save_history = """    def _save_history(self):
        \"\"\"Sohbet geçmişini Veritabanına kaydeder (debounced).\"\"\"
        try:
            history = self.chat_session.get_history()
            if not history:
                return
                
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
            logger.error(f"❌ Geçmiş kaydedilirken hata: {e}")"""

content = content.replace(old_save_history, new_save_history)

with open(brain_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Refactored ai_brain.py")
