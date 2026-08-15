document.addEventListener('DOMContentLoaded', () => {
    
    // --- Navigation ---
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.view-section');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active from all
            navItems.forEach(nav => nav.classList.remove('active'));
            sections.forEach(sec => sec.classList.remove('active'));
            
            // Add active to clicked
            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
            
            // Load settings if settings view is opened
            if (targetId === 'settings') {
                loadSettings();
            } else if (targetId === 'commands') {
                loadCommands();
            } else if (targetId === 'leaderboard') {
                loadLeaderboard();
            }
        });
    });

    // --- Bot Control ---
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const statusBadge = document.getElementById('main-status-badge');
    const statusMessage = document.getElementById('status-message');
    const sidebarDot = document.getElementById('sidebar-status-dot');
    const sidebarText = document.getElementById('sidebar-status-text');
    const logContainer = document.getElementById('log-container');

    let logPollInterval = null;

    function updateStatusUI(isRunning) {
        if (isRunning) {
            statusBadge.textContent = 'Çevrimiçi';
            statusBadge.className = 'badge online';
            sidebarDot.className = 'status-dot online';
            sidebarText.textContent = 'Çevrimiçi';
            statusMessage.textContent = 'Bot arka planda başarıyla çalışıyor ve sohbeti dinliyor.';
            btnStart.disabled = true;
            btnStop.disabled = false;
            
            if (!logPollInterval) {
                logPollInterval = setInterval(fetchLogs, 1500);
            }
        } else {
            statusBadge.textContent = 'Çevrimdışı';
            statusBadge.className = 'badge offline';
            sidebarDot.className = 'status-dot offline';
            sidebarText.textContent = 'Çevrimdışı';
            statusMessage.textContent = 'Bot şu anda çalışmıyor. Başlatmak için butonu kullanın.';
            btnStart.disabled = false;
            btnStop.disabled = true;
            
            if (logPollInterval) {
                clearInterval(logPollInterval);
                logPollInterval = null;
            }
        }
    }

    async function checkStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            updateStatusUI(data.running);
        } catch (err) {
            console.error('Status check failed', err);
        }
    }

    async function fetchLogs() {
        try {
            const res = await fetch('/api/logs');
            const data = await res.json();
            renderLogs(data.logs);
        } catch (err) {
            console.error('Log fetch failed', err);
        }
    }

    function renderLogs(logs) {
        // Only update if we have new logs
        logContainer.innerHTML = '';
        if (logs.length === 0) {
            logContainer.innerHTML = '<div class="log-line system">Sistem bekleniyor...</div>';
            return;
        }
        
        logs.forEach(log => {
            const div = document.createElement('div');
            div.className = 'log-line';
            
            // Simple coloring logic
            if (log.includes('ERROR') || log.includes('Hata') || log.includes('Exception')) {
                div.classList.add('error');
            } else if (log.includes('✅') || log.includes('Bağlandı')) {
                div.classList.add('success');
            } else if (log.includes('🤖')) {
                div.classList.add('bot');
            } else if (log.includes('Sistem:')) {
                div.classList.add('system');
            }
            
            div.textContent = log;
            logContainer.appendChild(div);
        });
        
        // Auto scroll to bottom
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    btnStart.addEventListener('click', async () => {
        btnStart.disabled = true;
        try {
            const res = await fetch('/api/start', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                updateStatusUI(true);
            } else {
                alert(data.message);
                btnStart.disabled = false;
            }
        } catch (err) {
            alert('Bot başlatılırken hata oluştu.');
            btnStart.disabled = false;
        }
    });

    btnStop.addEventListener('click', async () => {
        btnStop.disabled = true;
        try {
            const res = await fetch('/api/stop', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                updateStatusUI(false);
            } else {
                alert(data.message);
                btnStop.disabled = false;
            }
        } catch (err) {
            alert('Bot durdurulurken hata oluştu.');
            btnStop.disabled = false;
        }
    });

    // --- Settings ---
    const settingsForm = document.getElementById('settings-form');
    const saveStatus = document.getElementById('save-status');

    async function loadSettings() {
        try {
            const res = await fetch('/api/settings');
            const data = await res.json();
            
            const fields = ['KICK_CHANNEL_SLUG', 'BOT_NAME', 'GEMINI_API_KEY', 'KICK_CLIENT_ID', 'KICK_CLIENT_SECRET'];
            fields.forEach(field => {
                const input = document.getElementById(field);
                if (input && data[field]) {
                    input.value = data[field];
                }
            });
        } catch (err) {
            console.error('Settings load failed', err);
        }
    }

    settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(settingsForm);
        const settings = Object.fromEntries(formData.entries());
        
        const btnSave = document.getElementById('btn-save-settings');
        btnSave.disabled = true;
        
        try {
            const res = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            const data = await res.json();
            
            if (data.success) {
                saveStatus.textContent = 'Ayarlar başarıyla kaydedildi!';
                saveStatus.classList.add('show');
                setTimeout(() => {
                    saveStatus.classList.remove('show');
                }, 3000);
            }
        } catch (err) {
            alert('Ayarlar kaydedilirken hata oluştu.');
        } finally {
            btnSave.disabled = false;
        }
    });

    // --- Commands ---
    const addCommandForm = document.getElementById('add-command-form');
    const commandsList = document.getElementById('commands-list');
    const searchCmdInput = document.getElementById('search-cmd');
    const btnCancelEdit = document.getElementById('btn-cancel-edit');
    const formTitle = document.getElementById('form-title');
    const btnSubmitCmd = document.getElementById('btn-submit-cmd');
    
    let allCommands = []; // Store commands for searching

    async function loadCommands() {
        try {
            const res = await fetch('/api/commands');
            const data = await res.json();
            
            allCommands = Object.entries(data);
            renderCommands();
        } catch (err) {
            console.error('Commands load failed', err);
        }
    }

    function renderCommands(filterText = '') {
        commandsList.innerHTML = '';
        
        const filtered = allCommands.filter(([cmd, resp]) => {
            return cmd.toLowerCase().includes(filterText.toLowerCase()) || 
                   resp.toLowerCase().includes(filterText.toLowerCase());
        });
        
        if (filtered.length === 0) {
            commandsList.innerHTML = '<div style="color: var(--text-muted); font-size: 14px;">Sonuç bulunamadı.</div>';
            return;
        }
        
        filtered.forEach(([cmd, resp]) => {
            const item = document.createElement('div');
            item.className = 'command-item';
            
            // Escape HTML just in case
            const safeCmd = cmd.replace(/</g, "&lt;").replace(/>/g, "&gt;");
            const safeResp = resp.replace(/</g, "&lt;").replace(/>/g, "&gt;");
            
            item.innerHTML = `
                <div class="cmd-details">
                    <div class="cmd-name">${safeCmd}</div>
                    <div class="cmd-response">${safeResp}</div>
                </div>
                <div style="display: flex; gap: 4px;">
                    <button class="btn-icon edit-cmd" data-cmd="${safeCmd}" data-resp="${safeResp}" title="Düzenle" style="color: var(--primary);">
                        <i class="ti ti-edit"></i>
                    </button>
                    <button class="btn-icon delete-cmd" data-cmd="${safeCmd}" title="Sil">
                        <i class="ti ti-trash"></i>
                    </button>
                </div>
            `;
            commandsList.appendChild(item);
        });

        // Add delete event listeners
        document.querySelectorAll('.delete-cmd').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const cmd = e.currentTarget.getAttribute('data-cmd');
                if(confirm(`'${cmd}' tetikleyicisini silmek istediğinize emin misiniz?`)) {
                    await fetch('/api/commands', {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ command: cmd })
                    });
                    loadCommands();
                    resetCmdForm();
                }
            });
        });

        // Add edit event listeners
        document.querySelectorAll('.edit-cmd').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const cmd = e.currentTarget.getAttribute('data-cmd');
                const resp = e.currentTarget.getAttribute('data-resp');
                
                document.getElementById('cmd-name').value = cmd;
                document.getElementById('cmd-resp').value = resp;
                
                formTitle.textContent = 'Tetikleyiciyi Düzenle';
                btnSubmitCmd.textContent = 'Güncelle';
                btnCancelEdit.style.display = 'block';
                
                // Scroll to top of form
                document.getElementById('add-command-form').scrollIntoView({ behavior: 'smooth' });
            });
        });
    }

    if(searchCmdInput) {
        searchCmdInput.addEventListener('input', (e) => {
            renderCommands(e.target.value);
        });
    }

    function resetCmdForm() {
        if(addCommandForm) {
            addCommandForm.reset();
            formTitle.textContent = 'Yeni Tetikleyici Ekle';
            btnSubmitCmd.textContent = 'Ekle';
            btnCancelEdit.style.display = 'none';
        }
    }

    if(btnCancelEdit) {
        btnCancelEdit.addEventListener('click', resetCmdForm);
    }

    if(addCommandForm) {
        addCommandForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(addCommandForm);
            const cmd = formData.get('command');
            const resp = formData.get('response');
            
            try {
                const res = await fetch('/api/commands', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: cmd, response: resp })
                });
                
                if(res.ok) {
                    resetCmdForm();
                    loadCommands();
                }
            } catch (err) {
                alert('Tetikleyici eklenirken hata oluştu.');
            }
        });
    }

    // --- Leaderboard ---
    const lbGames = document.getElementById('lb-games');
    const lbChat = document.getElementById('lb-chat');

    async function loadLeaderboard() {
        try {
            const res = await fetch('/api/leaderboard');
            const data = await res.json();
            
            // Render Games
            lbGames.innerHTML = '';
            if(data.scores.length === 0) {
                lbGames.innerHTML = '<li class="lb-item" style="justify-content: center; color: var(--text-muted);">Henüz puan alan yok.</li>';
            } else {
                data.scores.forEach((item, index) => {
                    let rankClass = index < 3 ? `rank-${index + 1}` : '';
                    let rankIcon = index === 0 ? '👑' : (index + 1);
                    lbGames.innerHTML += `
                        <li class="lb-item">
                            <span class="lb-rank ${rankClass}">${rankIcon}</span>
                            <span class="lb-user">${item.username}</span>
                            <span class="lb-score">${item.score} Puan</span>
                        </li>
                    `;
                });
            }

            // Render Chat
            lbChat.innerHTML = '';
            if(data.chat.length === 0) {
                lbChat.innerHTML = '<li class="lb-item" style="justify-content: center; color: var(--text-muted);">Henüz mesaj yok.</li>';
            } else {
                data.chat.forEach((item, index) => {
                    let rankClass = index < 3 ? `rank-${index + 1}` : '';
                    let rankIcon = index === 0 ? '👑' : (index + 1);
                    lbChat.innerHTML += `
                        <li class="lb-item">
                            <span class="lb-rank ${rankClass}">${rankIcon}</span>
                            <span class="lb-user">${item.username}</span>
                            <span class="lb-score">${item.messages} Msj</span>
                        </li>
                    `;
                });
            }

        } catch (err) {
            console.error('Leaderboard load failed', err);
        }
    }

    // Initial checks
    checkStatus();
    // Poll status every 5 seconds just in case it crashes
    setInterval(checkStatus, 5000);
});
