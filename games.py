import json
import os
import random
import time
import logging

logger = logging.getLogger("Games")

class GameEngine:
    def __init__(self, db):
        self.db = db
        self.word_pool_file = os.path.join(os.path.dirname(__file__), "word_pool.json")
        self.word_pool = self._load_word_pool()
        
        # Oyun Durumları
        self.current_game = None  # "number" veya "word"
        self.game_start_time = 0
        self.game_data = {}

    def _load_word_pool(self) -> list:
        if os.path.exists(self.word_pool_file):
            with open(self.word_pool_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception:
                    pass
        
        # Varsayılan havuz (eğer dosya yoksa)
        default_pool = [
            {"word": "klavye", "desc": "Bilgisayara yazı yazmak için kullanılan, üzerinde harf ve rakam tuşları bulunan donanım."},
            {"word": "monitör", "desc": "Bilgisayarın görüntü vermesini sağlayan ekran."},
            {"word": "istanbul", "desc": "Türkiye'nin en kalabalık ve tarihi açıdan en zengin şehri, iki kıtayı birbirine bağlar."},
            {"word": "kaplan", "desc": "Asya'da yaşayan, çizgili kürküyle bilinen büyük ve yırtıcı bir kedi türü."},
            {"word": "ram", "desc": "Bilgisayarlarda geçici belleği ifade eden 3 harfli kısaltma."},
            {"word": "anakart", "desc": "Bilgisayardaki tüm donanımların üzerine takıldığı ana elektronik devre kartı."},
            {"word": "ankara", "desc": "Türkiye'nin başkenti."},
            {"word": "kanguru", "desc": "Avustralya'da yaşayan, zıplayarak hareket eden ve yavrularını kesesinde taşıyan hayvan."},
            {"word": "japonya", "desc": "Doğu Asya'da bulunan, 'Doğan Güneşin Ülkesi' olarak bilinen ada ülkesi."},
            {"word": "orkide", "desc": "Zarif ve egzotik çiçekleriyle bilinen, bakımı özel ilgi isteyen bir süs bitkisi."}
        ]
        with open(self.word_pool_file, "w", encoding="utf-8") as f:
            json.dump(default_pool, f, ensure_ascii=False, indent=2)
        return default_pool

    def get_score(self, username: str) -> int:
        return self.db.get_score(username)

    def add_score(self, username: str, points: int):
        self.db.update_score(username, points)

    def get_leaderboard(self) -> list:
        scores = self.db.get_all_scores()
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:5]

    # --- Sayı Tahmini Oyunu ---
    
    def start_number_game(self) -> str | None:
        if self.current_game is not None:
            return "Şu an zaten devam eden bir oyun var!"
            
        self.current_game = "number"
        self.game_start_time = time.time()
        target = random.randint(1, 100)
        self.game_data = {"target": target, "duration": 120}  # 2 dakika
        logger.info(f"Sayı oyunu başladı. Hedef: {target}")
        return "🔢 Sayı tahmini oyunu başladı! 1 ile 100 arasında bir sayı tuttum. (Süre: 2 dakika)\nTahmin etmek için doğrudan sayıyı sohbete yazın!"

    def check_number_guess(self, username: str, guess_str: str) -> str | None:
        if self.current_game != "number":
            return None
            
        # Süre kontrolü
        if time.time() - self.game_start_time > self.game_data["duration"]:
            self.current_game = None
            return f"⏱️ Süre doldu! Kimse sayıyı ( {self.game_data['target']} ) bilemedi."

        # Tahmin bir sayı mı?
        try:
            guess = int(guess_str.strip())
        except ValueError:
            return None

        target = self.game_data["target"]
        if guess == target:
            self.add_score(username, 10)
            self.current_game = None
            return f"🎉 BİLDİN! @{username} 10 puan kazandı. Sayı {target} idi."
        elif guess < target:
            return f"🤖 @{username}, Daha yüksek! ⬆️"
        else:
            return f"🤖 @{username}, Daha düşük! ⬇️"

    # --- Kelime Oyunu ---
    
    def start_word_game(self) -> str | None:
        if self.current_game is not None:
            return "Şu an zaten devam eden bir oyun var!"
            
        self.current_game = "word"
        self.game_start_time = time.time()
        
        word_obj = random.choice(self.word_pool)
        word = word_obj["word"].lower()
        desc = word_obj["desc"]
        
        self.game_data = {
            "word": word,
            "desc": desc,
            "duration": 30,  # 30 saniye
            "hint_given": False
        }
        logger.info(f"Kelime oyunu başladı. Hedef: {word}")
        return f"🔤 Kelime Oyunu Başladı! (Süre: 30 sn)\n❓ Anlamı: {desc}\n(10 saniye sonra ipucu gelecek)"

    def check_word_guess(self, username: str, guess_str: str) -> str | None:
        if self.current_game != "word":
            return None
            
        elapsed = time.time() - self.game_start_time
        
        # Süre doldu mu?
        if elapsed > self.game_data["duration"]:
            word = self.game_data["word"]
            self.current_game = None
            return f"⏱️ Süre doldu! Kimse kelimeyi bilemedi. Doğru cevap: {word.upper()}"
            
        # İpucu zamanı geldi mi?
        if elapsed >= 10 and not self.game_data["hint_given"]:
            self.game_data["hint_given"] = True
            word = self.game_data["word"]
            hint = f"{word[0].upper()}{'*' * (len(word)-1)}"
            return f"💡 İpucu: Kelime {len(word)} harfli ve '{hint}' şeklinde."

        # Tahmin kontrolü
        guess = guess_str.strip().lower()
        if guess == self.game_data["word"]:
            self.add_score(username, 10)
            self.current_game = None
            return f"🎉 BİLDİN! @{username} 10 puan kazandı. Doğru cevap: {guess.upper()} idi."
            
        return None

    def tick(self) -> str | None:
        """
        Oyun durumlarını saniyede bir kontrol eden fonksiyon.
        İpucu göndermek veya süresi biten oyunları kapatmak için main'den çağrılır.
        """
        if self.current_game == "word":
            elapsed = time.time() - self.game_start_time
            if elapsed >= 10 and not self.game_data["hint_given"]:
                self.game_data["hint_given"] = True
                word = self.game_data["word"]
                hint = f"{word[0].upper()}{'*' * (len(word)-1)}"
                return f"💡 Kelime Oyunu İpucu: Kelime {len(word)} harfli ve '{hint}' şeklinde."
                
            if elapsed > self.game_data["duration"]:
                word = self.game_data["word"]
                self.current_game = None
                return f"⏱️ Kelime oyunu süresi doldu! Kimse bilemedi. Doğru cevap: {word.upper()}"
                
        elif self.current_game == "number":
            elapsed = time.time() - self.game_start_time
            if elapsed > self.game_data["duration"]:
                target = self.game_data["target"]
                self.current_game = None
                return f"⏱️ Sayı oyunu süresi doldu! Kimse sayıyı ( {target} ) bilemedi."
                
        return None
