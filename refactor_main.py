import os

main_file = os.path.join(os.path.dirname(__file__), "main.py")

with open(main_file, "r", encoding="utf-8") as f:
    content = f.read()

# Replace fuzzy match static_commands
content = content.replace("for key in self.static_commands:", "for key in self.db.get_static_commands():")
content = content.replace("return self.static_commands[best_match]", "return self.db.get_static_commands()[best_match]")

# Replace VIP logic
content = content.replace("""        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if username not in self.vip_users:
            self.vip_users[username] = []
        if today not in self.vip_users[username]:
            self.vip_users[username].append(today)
            self._save_vip_users()""", """        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.db.add_active_day(username, today)""")

content = content.replace("if len(self.vip_users[username]) >= 5:", "if self.db.get_active_days_count(username) >= 5:")

# Static & Pending command logic
content = content.replace("static_reply = self.static_commands.get(raw_msg_lower)", "static_reply = self.db.get_static_commands().get(raw_msg_lower)")

pending_learn_logic_old = """                    if keyword not in self.pending_commands:
                        self.pending_commands[keyword] = {"response": ai_cevap, "users": []}
                    if username not in self.pending_commands[keyword]["users"]:
                        self.pending_commands[keyword]["users"].append(username)
                        self._save_pending_commands()
                    if len(self.pending_commands[keyword]["users"]) >= 3:
                        self.static_commands[keyword] = self.pending_commands[keyword]["response"]
                        self._save_static_commands()
                        del self.pending_commands[keyword]
                        self._save_pending_commands()"""

pending_learn_logic_new = """                    pending = self.db.get_pending_commands()
                    if keyword not in pending:
                        pending[keyword] = {"response": ai_cevap, "users": []}
                    if username not in pending[keyword]["users"]:
                        pending[keyword]["users"].append(username)
                        self.db.set_pending_command(keyword, pending[keyword])
                    if len(pending[keyword]["users"]) >= 3:
                        self.db.set_static_command(keyword, pending[keyword]["response"])
                        self.db.delete_pending_command(keyword)"""

content = content.replace(pending_learn_logic_old, pending_learn_logic_new)

auto_learn_logic_old = """        # ── OTOMATİK ÖĞRENME ──
        if raw_msg_lower in self.pending_commands:
            pending_resp = self.pending_commands[raw_msg_lower]["response"]
            if username not in self.pending_commands[raw_msg_lower]["users"]:
                self.pending_commands[raw_msg_lower]["users"].append(username)
                self._save_pending_commands()
                if len(self.pending_commands[raw_msg_lower]["users"]) >= 3:
                    self.static_commands[raw_msg_lower] = pending_resp
                    self._save_static_commands()
                    del self.pending_commands[raw_msg_lower]
                    self._save_pending_commands()
            await self._send_formatted_response(username, pending_resp)"""

auto_learn_logic_new = """        # ── OTOMATİK ÖĞRENME ──
        pending = self.db.get_pending_commands()
        if raw_msg_lower in pending:
            pending_resp = pending[raw_msg_lower]["response"]
            if username not in pending[raw_msg_lower]["users"]:
                pending[raw_msg_lower]["users"].append(username)
                self.db.set_pending_command(raw_msg_lower, pending[raw_msg_lower])
                if len(pending[raw_msg_lower]["users"]) >= 3:
                    self.db.set_static_command(raw_msg_lower, pending_resp)
                    self.db.delete_pending_command(raw_msg_lower)
            await self._send_formatted_response(username, pending_resp)"""

content = content.replace(auto_learn_logic_old, auto_learn_logic_new)

add_pending_old = """            if "Beyin kısa devre yaptı" not in response:
                self.pending_commands[raw_msg_lower] = {"response": response, "users": [username]}
                self._save_pending_commands()"""

add_pending_new = """            if "Beyin kısa devre yaptı" not in response:
                self.db.set_pending_command(raw_msg_lower, {"response": response, "users": [username]})"""

content = content.replace(add_pending_old, add_pending_new)

with open(main_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Refactor script finished.")
