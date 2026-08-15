import os
import json
from database import Database

def migrate():
    print("SQLite Migration Started...")
    db = Database("bot_data.db")
    base_dir = os.path.dirname(__file__)

    # 1. Migrate user_memory.json
    user_memory_file = os.path.join(base_dir, "user_memory.json")
    if os.path.exists(user_memory_file):
        print("Migrating user_memory.json...")
        with open(user_memory_file, "r", encoding="utf-8") as f:
            try:
                users = json.load(f)
                for username, data in users.items():
                    db.upsert_user(username, data)
            except Exception as e:
                print(f"Error migrating user_memory.json: {e}")
                
    # 2. Migrate scores.json
    scores_file = os.path.join(base_dir, "scores.json")
    if os.path.exists(scores_file):
        print("Migrating scores.json...")
        with open(scores_file, "r", encoding="utf-8") as f:
            try:
                scores = json.load(f)
                for username, score in scores.items():
                    db.update_score(username, score)
            except Exception as e:
                print(f"Error migrating scores.json: {e}")

    # 3. Migrate vip_users.json (active days)
    vip_file = os.path.join(base_dir, "vip_users.json")
    if os.path.exists(vip_file):
        print("Migrating vip_users.json...")
        with open(vip_file, "r", encoding="utf-8") as f:
            try:
                vip_users = json.load(f)
                for username, dates in vip_users.items():
                    # Ensure user exists first
                    db.conn.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
                    for date in dates:
                        db.add_active_day(username, date)
            except Exception as e:
                print(f"Error migrating vip_users.json: {e}")

    # 4. Migrate static_commands.json
    static_file = os.path.join(base_dir, "static_commands.json")
    if os.path.exists(static_file):
        print("Migrating static_commands.json...")
        with open(static_file, "r", encoding="utf-8") as f:
            try:
                commands = json.load(f)
                for cmd, resp in commands.items():
                    db.set_static_command(cmd, resp)
            except Exception as e:
                print(f"Error migrating static_commands.json: {e}")

    # 5. Migrate pending_commands.json
    pending_file = os.path.join(base_dir, "pending_commands.json")
    if os.path.exists(pending_file):
        print("Migrating pending_commands.json...")
        with open(pending_file, "r", encoding="utf-8") as f:
            try:
                pending = json.load(f)
                for cmd, data in pending.items():
                    db.set_pending_command(cmd, data)
            except Exception as e:
                print(f"Error migrating pending_commands.json: {e}")

    # 6. Migrate chat_history.json
    history_file = os.path.join(base_dir, "chat_history.json")
    if os.path.exists(history_file):
        print("Migrating chat_history.json...")
        with open(history_file, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
                for item in history:
                    role = item.get("role", "")
                    parts = item.get("parts", [])
                    text = parts[0].get("text", "") if parts else ""
                    if text:
                        db.add_chat_history(role, text)
            except Exception as e:
                print(f"Error migrating chat_history.json: {e}")

    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
