import os
import sys
import threading
import subprocess
from collections import deque
from flask import Flask, render_template, request, jsonify
from database import Database

app = Flask(__name__)

# Global variables to manage the bot process and logs
bot_process = None
bot_logs = deque(maxlen=200) # Keep last 200 lines of logs

db = Database()

ENV_FILE_PATH = ".env"

def read_env():
    """Reads the .env file and returns a dictionary of settings."""
    settings = {}
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        settings[key.strip()] = value.strip()
    return settings

def write_env(settings):
    """Writes the settings dictionary back to the .env file."""
    # First, read existing lines to preserve comments and order
    existing_lines = []
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, "r", encoding="utf-8-sig") as f:
            existing_lines = f.readlines()
            
    with open(ENV_FILE_PATH, "w", encoding="utf-8-sig") as f:
        written_keys = set()
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in settings:
                    f.write(f"{key}={settings[key]}\n")
                    written_keys.add(key)
                else:
                    f.write(line)
            else:
                f.write(line)
                
        # Write any new keys that weren't in the file
        for key, value in settings.items():
            if key not in written_keys:
                f.write(f"{key}={value}\n")

def log_reader(process):
    """Reads stdout from the bot process and appends to the log queue."""
    for line in iter(process.stdout.readline, b''):
        try:
            decoded_line = line.decode('utf-8', errors='replace').strip()
            if decoded_line:
                bot_logs.append(decoded_line)
        except Exception:
            pass

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def status():
    global bot_process
    is_running = False
    if bot_process is not None:
        if bot_process.poll() is None:
            is_running = True
        else:
            bot_process = None
            
    return jsonify({"running": is_running})

@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_process, bot_logs
    if bot_process is None or bot_process.poll() is not None:
        bot_logs.clear()
        bot_logs.append("Sistem: Bot başlatılıyor...")
        
        # Determine python executable (handle venv if necessary, fallback to sys.executable)
        python_exec = sys.executable
        
        # Start process
        bot_process = subprocess.Popen(
            [python_exec, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # Start a background thread to read logs
        threading.Thread(target=log_reader, args=(bot_process,), daemon=True).start()
        
        return jsonify({"success": True, "message": "Bot başlatıldı."})
    return jsonify({"success": False, "message": "Bot zaten çalışıyor."})

@app.route("/api/stop", methods=["POST"])
def stop_bot():
    global bot_process
    if bot_process is not None and bot_process.poll() is None:
        if os.name == 'nt':
            # Send CTRL_BREAK on Windows to stop subprocess gracefully
            bot_process.send_signal(subprocess.signal.CTRL_BREAK_EVENT)
        else:
            bot_process.terminate()
            
        try:
            bot_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            bot_process.kill()
            
        bot_process = None
        bot_logs.append("Sistem: Bot durduruldu.")
        return jsonify({"success": True, "message": "Bot durduruldu."})
    return jsonify({"success": False, "message": "Bot zaten çalışmıyor."})

@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify({"logs": list(bot_logs)})

@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    if request.method == "GET":
        return jsonify(read_env())
    else:
        new_settings = request.json
        current_settings = read_env()
        current_settings.update(new_settings)
        write_env(current_settings)
        return jsonify({"success": True})

@app.route("/api/commands", methods=["GET", "POST", "DELETE"])
def handle_commands():
    if request.method == "GET":
        return jsonify(db.get_static_commands())
    elif request.method == "POST":
        data = request.json
        cmd = data.get("command")
        resp = data.get("response")
        if cmd and resp:
            db.set_static_command(cmd, resp)
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Eksik bilgi."}), 400
    elif request.method == "DELETE":
        data = request.json
        cmd = data.get("command")
        if cmd:
            with db.conn:
                db.conn.execute("DELETE FROM static_commands WHERE command = ?", (cmd,))
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Komut belirtilmedi."}), 400

@app.route("/api/leaderboard", methods=["GET"])
def get_leaderboard():
    users = db.get_all_users()
    # Puan sıralaması (Games)
    scores = [{"username": u, "score": d["oyun_puani"]} for u, d in users.items() if d["oyun_puani"] > 0]
    scores.sort(key=lambda x: x["score"], reverse=True)
    
    # Mesaj sayısı sıralaması (Chat)
    chat_activity = [{"username": u, "messages": d["toplam_mesaj"]} for u, d in users.items() if d["toplam_mesaj"] > 0]
    chat_activity.sort(key=lambda x: x["messages"], reverse=True)
    
    return jsonify({
        "scores": scores,
        "chat": chat_activity
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
