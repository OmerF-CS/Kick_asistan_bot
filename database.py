import sqlite3
import json
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Database")

class Database:
    def __init__(self, db_path="bot_data.db"):
        self.db_path = os.path.join(os.path.dirname(__file__), db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    ilk_gorulen TEXT,
                    son_gorulen TEXT,
                    toplam_mesaj INTEGER DEFAULT 0,
                    oyun_puani INTEGER DEFAULT 0,
                    mod BOOLEAN DEFAULT 0,
                    last_injected REAL DEFAULT 0,
                    favori_konular TEXT DEFAULT '[]',
                    son_mesajlar TEXT DEFAULT '[]'
                )
            """)
            
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_active_days (
                    username TEXT,
                    date TEXT,
                    PRIMARY KEY (username, date),
                    FOREIGN KEY (username) REFERENCES users(username)
                )
            """)
            
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS static_commands (
                    command TEXT PRIMARY KEY,
                    response TEXT
                )
            """)

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_commands (
                    command TEXT PRIMARY KEY,
                    response TEXT,
                    users TEXT DEFAULT '[]'
                )
            """)

    # --- Users & Memory ---
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            user_data = dict(row)
            user_data['favori_konular'] = json.loads(user_data['favori_konular'])
            user_data['son_mesajlar'] = json.loads(user_data['son_mesajlar'])
            user_data['mod'] = bool(user_data['mod'])
            # Fetch active days
            active_days_cursor = self.conn.execute("SELECT date FROM user_active_days WHERE username = ?", (username,))
            user_data['aktif_gunler'] = [r['date'] for r in active_days_cursor.fetchall()]
            return user_data
        return None

    def upsert_user(self, username: str, user_data: dict):
        with self.conn:
            self.conn.execute("""
                INSERT INTO users (username, ilk_gorulen, son_gorulen, toplam_mesaj, oyun_puani, mod, last_injected, favori_konular, son_mesajlar)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    ilk_gorulen=excluded.ilk_gorulen,
                    son_gorulen=excluded.son_gorulen,
                    toplam_mesaj=excluded.toplam_mesaj,
                    oyun_puani=excluded.oyun_puani,
                    mod=excluded.mod,
                    last_injected=excluded.last_injected,
                    favori_konular=excluded.favori_konular,
                    son_mesajlar=excluded.son_mesajlar
            """, (
                username,
                user_data.get('ilk_gorulen', ''),
                user_data.get('son_gorulen', ''),
                user_data.get('toplam_mesaj', 0),
                user_data.get('oyun_puani', 0),
                1 if user_data.get('mod', False) else 0,
                user_data.get('last_injected', 0.0),
                json.dumps(user_data.get('favori_konular', [])),
                json.dumps(user_data.get('son_mesajlar', []))
            ))

            if 'aktif_gunler' in user_data:
                for date in user_data['aktif_gunler']:
                    self.add_active_day(username, date)
                    
    def get_all_users(self) -> Dict[str, dict]:
        users = {}
        cursor = self.conn.execute("SELECT username FROM users")
        for row in cursor.fetchall():
            users[row['username']] = self.get_user(row['username'])
        return users

    def add_active_day(self, username: str, date: str):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO user_active_days (username, date) VALUES (?, ?)", (username, date))

    def get_active_days_count(self, username: str) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM user_active_days WHERE username = ?", (username,))
        return cursor.fetchone()[0]

    # --- Scores (Games) ---
    def update_score(self, username: str, score_delta: int):
        with self.conn:
            self.conn.execute("""
                INSERT INTO users (username, oyun_puani) VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET oyun_puani = oyun_puani + excluded.oyun_puani
            """, (username, score_delta))

    def get_score(self, username: str) -> int:
        cursor = self.conn.execute("SELECT oyun_puani FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return row['oyun_puani'] if row else 0
        
    def get_all_scores(self) -> Dict[str, int]:
        cursor = self.conn.execute("SELECT username, oyun_puani FROM users WHERE oyun_puani > 0")
        return {row['username']: row['oyun_puani'] for row in cursor.fetchall()}

    # --- Static Commands ---
    def get_static_commands(self) -> Dict[str, str]:
        cursor = self.conn.execute("SELECT command, response FROM static_commands")
        return {row['command']: row['response'] for row in cursor.fetchall()}

    def set_static_command(self, command: str, response: str):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO static_commands (command, response) VALUES (?, ?)", (command, response))

    # --- Pending Commands ---
    def get_pending_commands(self) -> Dict[str, dict]:
        cursor = self.conn.execute("SELECT command, response, users FROM pending_commands")
        return {row['command']: {"response": row['response'], "users": json.loads(row['users'])} for row in cursor.fetchall()}

    def set_pending_command(self, command: str, data: dict):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO pending_commands (command, response, users) VALUES (?, ?, ?)", 
                              (command, data['response'], json.dumps(data['users'])))
                              
    def delete_pending_command(self, command: str):
        with self.conn:
            self.conn.execute("DELETE FROM pending_commands WHERE command = ?", (command,))

    # --- Chat History (AI Brain) ---
    def add_chat_history(self, role: str, text: str):
        with self.conn:
            self.conn.execute("INSERT INTO chat_history (role, text) VALUES (?, ?)", (role, text))

    def get_recent_chat_history(self, limit: int) -> List[Dict[str, Any]]:
        cursor = self.conn.execute("SELECT role, text FROM chat_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        # Veritabanından sondan başa doğru (DESC) çekildiği için, kronolojik sıraya sokmak için reverse yapıyoruz.
        history = []
        for row in reversed(rows):
            history.append({
                "role": row["role"],
                "parts": [{"text": row["text"]}]
            })
        return history
        
    def clear_chat_history(self):
        with self.conn:
            self.conn.execute("DELETE FROM chat_history")
