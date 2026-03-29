/* ═══════════════════════════════════════════════════════════════
   CREDGEN — DASHBOARD.JS (Consolidated & Robust)
   ═══════════════════════════════════════════════════════════════ */

// ── HELPERS ───────────────────────────────────────────────────
function authHeaders() {
    const token = sessionStorage.getItem('admin_token');
    return {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    };
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatIndian(s) {
    s = String(Math.floor(s));
    if (s.length <= 3) return s;
    const last3 = s.slice(-3);
    const rest  = s.slice(0, -3);
    return rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3;
}

// ── TAB SWITCHING ─────────────────────────────────────────────
function switchTab(tab) {
    console.log('[DASHBOARD] Switching to tab:', tab);
    
    // Reset all
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    // Activate selected
    const targetTab = document.getElementById('tab-' + tab);
    if (targetTab) targetTab.classList.add('active');
    
    const navItem = document.querySelector(`.nav-item[data-tab="${tab}"]`);
    if (navItem) navItem.classList.add('active');

    // Route calls
    if (tab === 'dashboard') loadDashboard();
    if (tab === 'applications') loadApplications(1);
    if (tab === 'chatlogs') loadChatSessions(1);
    if (tab === 'tuning') loadTuning();
}

// ── DASHBOARD (ANALYTICS) ─────────────────────────────────────
async function loadDashboard() {
    try {
        const resp = await fetch('/admin/analytics/summary', { headers: authHeaders() });
        const data = await resp.json();
        
        if (data.error) throw new Error(data.error);

        document.getElementById('stat-total').textContent = data.total_applications || 0;
        document.getElementById('stat-approved').textContent = data.approved_today || 0;
        document.getElementById('stat-rejected').textContent = data.rejected_today || 0;
        document.getElementById('stat-rate').textContent = (data.approval_rate_pct || 0) + '%';
        
        renderOverviewChart(data.daily_counts || []);
        renderStatusChart(data.applications_by_status || {});
    } catch (err) {
        console.error('[ADMIN] analytics error:', err);
    }
}

let overviewChart = null;
function renderOverviewChart(counts) {
    const ctx = document.getElementById('overviewChart');
    if (!ctx) return;
    if (overviewChart) overviewChart.destroy();

    overviewChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: counts.map(c => c.date),
            datasets: [{
                label: 'Applications',
                data: counts.map(c => c.count),
                borderColor: '#6366f1',
                tension: 0.4,
                fill: true,
                backgroundColor: 'rgba(99, 102, 241, 0.1)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

let statusChart = null;
function renderStatusChart(statusMap) {
    const ctx = document.getElementById('statusChart');
    if (!ctx) return;
    if (statusChart) statusChart.destroy();

    const labels = Object.keys(statusMap);
    const data = Object.values(statusMap);

    statusChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } }
        }
    });
}

// ── APPLICATIONS ──────────────────────────────────────────────
let currentAppPage = 1;
function applyStatusFilter() {
    loadApplications(1);
}

async function exportCSV() {
    const status = document.getElementById('filter-status').value;
    const url = `/admin/export/applications?status=${status}`;
    
    try {
        const resp = await fetch(url, { headers: authHeaders() });
        if (!resp.ok) throw new Error('Export failed');
        
        const blob = await resp.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `applications_${status || 'all'}_${new Date().toISOString().slice(0,10)}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        a.remove();
    } catch (err) {
        alert('Could not export CSV. Please try again.');
    }
}

async function loadApplications(page = 1) {
    currentAppPage = page;
    const tbody = document.getElementById('applications-tbody');
    if (!tbody) return;

    const statusFilter = document.getElementById('filter-status').value;
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted)">Loading applications...</td></tr>`;

    try {
        const res = await fetch(`/admin/applications?page=${page}&per_page=15&status=${statusFilter}`, { 
            headers: authHeaders() 
        });
        const data = await res.json();
        const apps = data.applications || [];

        if (apps.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:60px;color:var(--text-muted)">No applications found matching criteria.</td></tr>`;
            return;
        }

        tbody.innerHTML = '';
        apps.forEach(app => {
            const row = document.createElement('tr');
            const status = (app.status || 'pending').toLowerCase();
            const amt = typeof app.loan_amount === 'number' ? app.loan_amount : 0;
            
            row.innerHTML = `
                <td>
                    <div style="font-weight:600">${escHtml(app.customer_name)}</div>
                    <div style="font-size:11px;color:var(--text-muted)">${escHtml(app.application_id.slice(0,8))}</div>
                </td>
                <td>${escHtml(app.loan_type || 'Personal')}</td>
                <td>₹ ${formatIndian(amt)}</td>
                <td><span class="status-badge status-${status}">${status.charAt(0).toUpperCase() + status.slice(1)}</span></td>
                <td style="font-size:12px">${escHtml(String(app.created_at || '').slice(0,10))}</td>
                <td><button class="btn-view" onclick="openAppDetails('${app.application_id}')">View</button></td>
            `;
            tbody.appendChild(row);
        });

        renderPagination(data.total_pages || 1, page);
    } catch (err) {
        console.error('[ADMIN] loadApplications failed:', err);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--danger)">Failed to load data.</td></tr>`;
    }
}

function renderPagination(totalPages, activePage) {
    const container = document.getElementById('pagination');
    if (!container) return;
    container.innerHTML = '';
    
    if (totalPages <= 1) return;

    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        btn.onclick = () => loadApplications(i);
        if (i === activePage) btn.classList.add('active');
        container.appendChild(btn);
    }
}

async function openAppDetails(id) {
    const drawer = document.getElementById('app-drawer');
    const backdrop = document.getElementById('drawer-backdrop');
    if (!drawer || !backdrop) return;

    drawer.innerHTML = '<div style="padding:40px;text-align:center">Loading...</div>';
    backdrop.style.display = 'block';
    setTimeout(() => { backdrop.style.opacity = '1'; drawer.style.transform = 'translateX(0)'; }, 10);

    try {
        // Find in loaded list or fetch
        const res = await fetch(`/admin/applications?page=1&per_page=100`, { headers: authHeaders() });
        const data = await res.json();
        const app = (data.applications || []).find(a => a.application_id === id);
        
        if (!app) {
            drawer.innerHTML = '<div style="padding:40px;text-align:center">Application not found</div>';
            return;
        }

        const status = (app.status || 'pending').toLowerCase();
        const amt = typeof app.loan_amount === 'number' ? app.loan_amount : 0;

        drawer.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
                <h3 style="margin:0">Application Detail</h3>
                <button onclick="closeAppDrawer()" style="background:none;border:none;font-size:24px;cursor:pointer;color:var(--text-secondary)">×</button>
            </div>
            
            <div class="drawer-section">
                <div class="drawer-label">Status</div>
                <span class="status-badge status-${status}">${status.toUpperCase()}</span>
            </div>

            <div class="drawer-section">
                <div class="drawer-label">Customer Info</div>
                <div class="drawer-row"><span>Name</span><strong>${escHtml(app.customer_name)}</strong></div>
                <div class="drawer-row"><span>Mobile</span><strong>${escHtml(app.phone)}</strong></div>
                <div class="drawer-row"><span>City</span><strong>${escHtml(app.city)}</strong></div>
            </div>

            <div class="drawer-section">
                <div class="drawer-label">Loan Details</div>
                <div class="drawer-row"><span>Type</span><strong>${escHtml(app.loan_type)}</strong></div>
                <div class="drawer-row"><span>Amount</span><strong>₹ ${formatIndian(amt)}</strong></div>
                <div class="drawer-row"><span>Applied</span><strong>${escHtml(String(app.created_at).slice(0,10))}</strong></div>
            </div>

            ${app.has_sanction_letter ? `
                <div class="drawer-section">
                    <div class="drawer-label">Documents</div>
                    <a href="/admin/application/${id}/letter" class="btn-download" target="_blank" style="margin-top:10px">Download Sanction Letter</a>
                </div>
            ` : ''}
        `;
    } catch (err) {
        drawer.innerHTML = '<div style="padding:40px;text-align:center;color:var(--danger)">Error loading details</div>';
    }
}

function closeAppDrawer() {
    const drawer = document.getElementById('app-drawer');
    const backdrop = document.getElementById('drawer-backdrop');
    if (drawer) drawer.style.transform = 'translateX(100%)';
    if (backdrop) {
        backdrop.style.opacity = '0';
        setTimeout(() => backdrop.style.display = 'none', 300);
    }
}

// ── CHAT LOGS ─────────────────────────────────────────────────
async function loadChatSessions(page = 1) {
    const tbody = document.getElementById('chat-sessions-body');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted)">Loading sessions...</td></tr>`;

    try {
        const res = await fetch(`/admin/chat-sessions?page=${page}&per_page=15`, { headers: authHeaders() });
        const data = await res.json();
        const sessions = data.sessions || [];

        if (sessions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:60px;color:var(--text-muted)">No chat history found.</td></tr>`;
            return;
        }

        tbody.innerHTML = '';
        sessions.forEach(s => {
            const row = document.createElement('tr');
            const dateStr = s.last_activity ? new Date(s.last_activity).toLocaleString() : 'N/A';
            
            row.innerHTML = `
                <td><span style="font-family:monospace;font-size:12px">${escHtml(String(s.session_id).slice(0,12))}...</span></td>
                <td><strong>${escHtml(s.customer_name)}</strong></td>
                <td><span class="status-badge" style="background:var(--bg-panel);border:1px solid var(--border)">${escHtml(s.stage)}</span></td>
                <td style="text-align:center">${s.interaction_count}</td>
                <td style="font-size:12px;color:var(--text-muted)">${dateStr}</td>
                <td><button class="btn-view" onclick="openLogModal('${s.session_id}', '${escHtml(s.customer_name)}')">View Log</button></td>
            `;
            tbody.appendChild(row);
        });

        renderChatPagination(data.total_pages || 1, page);
    } catch (err) {
        console.error('[ADMIN] loadChatSessions failed:', err);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--danger)">Failed to load data.</td></tr>`;
    }
}

function renderChatPagination(totalPages, activePage) {
    const container = document.getElementById('chatlogs-pagination');
    if (!container) return;
    container.innerHTML = '';
    
    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        btn.onclick = () => loadChatSessions(i);
        if (i === activePage) btn.classList.add('active');
        container.appendChild(btn);
    }
}

async function openLogModal(sessionId, userName) {
    const modal = document.getElementById('log-modal');
    const container = document.getElementById('log-messages-container');
    if (!modal || !container) return;

    document.getElementById('log-session-id').textContent = 'ID: ' + sessionId;
    document.getElementById('log-user-name').textContent = 'User: ' + userName;

    modal.classList.remove('hidden');
    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)">Loading messages...</div>';

    try {
        const res = await fetch(`/admin/chat-logs/${sessionId}`, { headers: authHeaders() });
        const data = await res.json();
        const logs = data.logs || [];

        if (logs.length === 0) {
            container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)">Empty transcript.</div>';
            return;
        }

        container.innerHTML = '';
        logs.forEach(l => {
            const msg = document.createElement('div');
            msg.className = `log-msg ${l.role === 'user' ? 'user' : 'bot'}`;
            msg.innerHTML = `
                <div>${escHtml(l.text)}</div>
                <span class="log-msg-meta">${l.role === 'user' ? 'User' : 'Assistant'} • ${new Date(l.created_at).toLocaleTimeString()}</span>
            `;
            container.appendChild(msg);
        });
        container.scrollTop = container.scrollHeight;
    } catch (err) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--danger)">Error loading transcript.</div>';
    }
}

function closeLogModal() {
    const modal = document.getElementById('log-modal');
    if (modal) modal.classList.add('hidden');
}

// ── AI TUNING ─────────────────────────────────────────────────
async function loadTuning() {
    try {
        const res = await fetch('/admin/tuning', { headers: authHeaders() });
        const data = await res.json();
        const editor = document.getElementById('tuning-content');
        if (editor) editor.value = data.content || '';
    } catch (err) {
        console.error('[ADMIN] loadTuning failed:', err);
    }
}

async function saveTuning() {
    const content = document.getElementById('tuning-content').value;
    const btn = document.querySelector('.btn-primary');
    
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
        const res = await fetch('/admin/tuning', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ content })
        });
        const data = await res.json();
        if (data.msg) alert('Tuning saved successfully');
    } catch (err) {
        alert('Failed to save tuning');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Changes';
    }
}

// ── THEME ─────────────────────────────────────────────────────
function setAdminTheme(theme) {
    localStorage.setItem('credgen_theme', theme);
    if (theme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    
    // Update theme icons and UI selections
    document.querySelectorAll('.theme-option').forEach(opt => {
        opt.classList.remove('active');
        if (opt.id === 'theme-' + theme) opt.classList.add('active');
    });

    console.log('[ADMIN] Theme set to:', theme);
}

// ── INITIALIZATION ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Check if token exists, else redirect (extra safety)
    if (!sessionStorage.getItem('admin_token')) {
        window.location.href = '/admin/login';
        return;
    }

    const activeTheme = localStorage.getItem('credgen_theme') || 'dark';
    setAdminTheme(activeTheme);

    // Set date in dashboard
    const dashDate = document.getElementById('dash-date');
    if (dashDate) dashDate.textContent = new Date().toLocaleDateString('en-US', { 
        weekday: 'long', 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });

    // Load initial tab
    switchTab('dashboard');
});
