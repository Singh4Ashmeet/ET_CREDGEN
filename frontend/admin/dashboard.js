/* ═══════════════════════════════════════════════════════════════
   CREDGEN — DASHBOARD.JS
   ═══════════════════════════════════════════════════════════════ */

let statusChart = null;
let dailyChart = null;
let currentPage = 1;
let currentStatusFilter = '';

// ── INIT ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const user = sessionStorage.getItem('admin_user');
    if (user) document.getElementById('sidebar-user').textContent = user;

    document.getElementById('dash-date').textContent = new Date().toLocaleDateString('en-IN', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
    });

    // Initial load
    const activeTab = document.querySelector('.nav-item.active')?.dataset.tab || 'dashboard';
    if (activeTab === 'dashboard') loadDashboard();
    else if (activeTab === 'applications') loadApplications(1, '');
});

// ── HELPERS ───────────────────────────────────────────────────
function authHeaders() {
    const token = sessionStorage.getItem('admin_token');
    return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatIndian(n) {
    const s = String(Math.round(n));
    if (s.length <= 3) return s;
    const last3 = s.slice(-3);
    const rest  = s.slice(0, -3);
    return rest.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + last3;
}

// ── TAB SWITCHING ─────────────────────────────────────────────
function switchTab(tab) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    document.getElementById('tab-' + tab).classList.add('active');
    const navItem = document.querySelector(`.nav-item[data-tab="${tab}"]`);
    if (navItem) navItem.classList.add('active');

    if (tab === 'dashboard') loadDashboard();
    if (tab === 'applications') loadApplications(1, currentStatusFilter);
    if (tab === 'tuning') loadTuning();
}

// ── DASHBOARD ─────────────────────────────────────────────────
async function loadDashboard() {
    try {
        const resp = await fetch('/admin/analytics/summary', { headers: authHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();

        document.getElementById('kpi-total').textContent = data.total_applications || 0;
        document.getElementById('kpi-approved').textContent = data.approved_today || 0;
        document.getElementById('kpi-rejected').textContent = data.rejected_today || 0;
        document.getElementById('kpi-rate').textContent = (data.approval_rate_pct || 0) + '%';

        renderCharts(data);
    } catch (e) {
        console.error('Dashboard load error:', e);
    }
}

function renderCharts(data) {
    const ctxStatus = document.getElementById('chart-status').getContext('2d');
    if (statusChart) statusChart.destroy();

    const statusData = data.applications_by_status || {};
    statusChart = new Chart(ctxStatus, {
        type: 'doughnut',
        data: {
            labels: Object.keys(statusData).map(s => s.charAt(0).toUpperCase() + s.slice(1)),
            datasets: [{
                data: Object.values(statusData),
                backgroundColor: ['#10b981', '#ef4444', '#6366f1', '#f59e0b', '#8b5cf6'],
                borderWidth: 0,
            }]
        },
        options: { cutout: '70%', plugins: { legend: { position: 'bottom' } }, responsive: true, maintainAspectRatio: false }
    });

    const ctxDaily = document.getElementById('chart-daily').getContext('2d');
    if (dailyChart) dailyChart.destroy();

    const dailyStats = data.daily_counts || [];
    dailyChart = new Chart(ctxDaily, {
        type: 'bar',
        data: {
            labels: dailyStats.map(d => d.date),
            datasets: [{
                label: 'Applications',
                data: dailyStats.map(d => d.count),
                backgroundColor: '#6366f1',
                borderRadius: 4
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
    });
}

// ── APPLICATIONS TABLE ────────────────────────────────────────
async function loadApplications(page = 1, statusFilter = '') {
    currentPage = page;
    currentStatusFilter = statusFilter;
    const tbody = document.getElementById('apps-tbody');

    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted)">Loading applications...</td></tr>`;

    try {
        const params = new URLSearchParams({
            page, per_page: 20,
            ...(statusFilter && statusFilter !== 'all' ? { status: statusFilter } : {})
        });

        const res = await fetch(`/admin/applications?${params}`, { headers: authHeaders() });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        const apps = data.applications || [];
        const total = data.total || 0;

        if (apps.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center;padding:60px;color:var(--text-muted)">
                        <div style="font-size:48px;margin-bottom:12px">📋</div>
                        <div>No applications found</div>
                    </td>
                </tr>`;
            renderPagination(1, 0, page);
            return;
        }

        tbody.innerHTML = '';
        apps.forEach(app => {
            const row = document.createElement('tr');
            row.style.cursor = 'pointer';
            row.onclick = () => openAppDrawer(app);

            let amtDisplay = 'N/A';
            try {
                const amt = parseFloat(String(app.loan_amount).replace(/,/g, ''));
                if (amt > 0) amtDisplay = '₹' + formatIndian(amt);
            } catch(e) {}

            let dateDisplay = 'N/A';
            try {
                if (app.created_at && app.created_at !== 'N/A') {
                    const d = new Date(app.created_at);
                    dateDisplay = isNaN(d) ? app.created_at.slice(0, 10) : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
                }
            } catch(e) {}

            const status = (app.status || 'pending').toLowerCase();
            const statusBadge = `<span class="status-badge status-${status}">${status.charAt(0).toUpperCase() + status.slice(1)}</span>`;

            row.innerHTML = `
                <td><div style="font-weight:500">${escHtml(app.customer_name || 'Unknown')}</div><div style="font-size:12px;color:var(--text-muted)">${escHtml(String(app.application_id || '').slice(0, 8))}...</div></td>
                <td>${amtDisplay}</td>
                <td>${statusBadge}</td>
                <td>${escHtml(app.loan_type || 'Personal')}</td>
                <td>${escHtml(dateDisplay)}</td>
                <td><button class="btn-view" onclick="event.stopPropagation(); openAppDrawer(${JSON.stringify(app).replace(/"/g, '&quot;')})">View</button></td>
            `;
            tbody.appendChild(row);
        });

        renderPagination(data.total_pages || 1, total, page);

    } catch (err) {
        console.error('[ADMIN] loadApplications failed:', err);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--danger)">Failed to load applications. <button onclick="loadApplications()">Retry</button></td></tr>`;
    }
}

function renderPagination(totalPages, total, activePage) {
    const container = document.getElementById('pagination');
    if (!container) return;
    container.innerHTML = '';
    if (totalPages <= 1 && total === 0) return;

    const prev = document.createElement('button');
    prev.textContent = '←';
    prev.disabled = activePage <= 1;
    prev.onclick = () => loadApplications(activePage - 1, currentStatusFilter);
    container.appendChild(prev);

    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        btn.classList.toggle('active', i === activePage);
        btn.onclick = () => loadApplications(i, currentStatusFilter);
        container.appendChild(btn);
    }

    const next = document.createElement('button');
    next.textContent = '→';
    next.disabled = activePage >= totalPages;
    next.onclick = () => loadApplications(activePage + 1, currentStatusFilter);
    container.appendChild(next);

    const info = document.createElement('span');
    info.style.cssText = 'margin-left:12px;font-size:13px;color:var(--text-muted)';
    info.textContent = `${total} total`;
    container.appendChild(info);
}

function applyStatusFilter() {
    const sel = document.getElementById('filter-status');
    currentStatusFilter = sel ? sel.value : '';
    loadApplications(1, currentStatusFilter);
}

// ── APP DRAWER ────────────────────────────────────────────────
function openAppDrawer(app) {
    if (typeof app === 'string') { try { app = JSON.parse(app); } catch(e) { return; } }

    let drawer = document.getElementById('app-drawer');
    let backdrop = document.getElementById('drawer-backdrop');

    if (!drawer) {
        backdrop = document.createElement('div');
        backdrop.id = 'drawer-backdrop';
        backdrop.onclick = closeAppDrawer;
        document.body.appendChild(backdrop);
        drawer = document.createElement('div');
        drawer.id = 'app-drawer';
        document.body.appendChild(drawer);
    }

    const status = (app.status || 'pending').toLowerCase();
    const amt = parseFloat(String(app.loan_amount || 0).replace(/,/g,''));

    drawer.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
            <h3 style="margin:0">Application Detail</h3>
            <button onclick="closeAppDrawer()" style="background:none;border:none;font-size:24px;cursor:pointer;color:var(--text-secondary)">×</button>
        </div>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
            <span class="status-badge status-${status}" style="font-size:14px;padding:5px 14px">${status.charAt(0).toUpperCase() + status.slice(1)}</span>
            <span style="font-size:12px;color:var(--text-muted)">${escHtml(app.application_id)}</span>
        </div>
        <div class="drawer-section">
            <div class="drawer-label">Customer</div>
            <div class="drawer-row"><span>Name</span><strong>${escHtml(app.customer_name||'N/A')}</strong></div>
            <div class="drawer-row"><span>Phone</span><strong>${escHtml(app.phone||'N/A')}</strong></div>
            <div class="drawer-row"><span>Email</span><strong>${escHtml(app.email||'N/A')}</strong></div>
            <div class="drawer-row"><span>City</span><strong>${escHtml(app.city||'N/A')}</strong></div>
        </div>
        <div class="drawer-section">
            <div class="drawer-label">Loan Details</div>
            <div class="drawer-row"><span>Amount</span><strong>${amt > 0 ? '₹' + formatIndian(amt) : 'N/A'}</strong></div>
            <div class="drawer-row"><span>Type</span><strong>${escHtml(app.loan_type||'personal')}</strong></div>
            <div class="drawer-row"><span>Applied On</span><strong>${escHtml(String(app.created_at||'N/A').slice(0,10))}</strong></div>
            ${app.rejection_reason ? `<div class="drawer-row"><span>Rejection Reason</span><strong style="color:var(--danger)">${escHtml(app.rejection_reason)}</strong></div>` : ''}
        </div>
    `;

    backdrop.style.display = 'block';
    setTimeout(() => { backdrop.style.opacity = '1'; drawer.style.transform = 'translateX(0)'; }, 10);
}

function closeAppDrawer() {
    const drawer = document.getElementById('app-drawer');
    const backdrop = document.getElementById('drawer-backdrop');
    if (drawer) drawer.style.transform = 'translateX(100%)';
    if (backdrop) { backdrop.style.opacity = '0'; setTimeout(() => backdrop.style.display = 'none', 300); }
}

function exportCSV() {
    const token = sessionStorage.getItem('admin_token');
    const params = new URLSearchParams({ status: currentStatusFilter || '' });
    const url = `/admin/export/applications?${params}`;
    window.open(url, '_blank');
}

// ── AI TUNING ─────────────────────────────────────────────────
async function loadTuning() {
    try {
        const resp = await fetch('/admin/tune', { headers: authHeaders() });
        // This is a list in new logic, but UI expects a single block. 
        // For now, let's just get the last one if it was a GET. 
        // The original route only had POST. I'll stick to what was there or what's needed.
    } catch (e) {}
}

async function saveTuning() {
    const content = document.getElementById('tuning-content').value;
    const msg = document.getElementById('tuning-msg');
    try {
        const resp = await fetch('/admin/tune', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ content }) });
        msg.textContent = resp.ok ? '✅ Context saved successfully' : '❌ Failed to save';
        msg.classList.remove('hidden');
    } catch (e) { }
}

async function logout() {
    sessionStorage.clear();
    window.location.href = '/admin/login';
}

async function changePassword() {
    const old = document.getElementById('old-password').value;
    const newPw = document.getElementById('new-password').value;
    const msg = document.getElementById('settings-msg');
    try {
        const resp = await fetch('/auth/change-password', { method: 'PUT', headers: authHeaders(), body: JSON.stringify({ old_password: old, new_password: newPw }) });
        const data = await resp.json();
        msg.textContent = data.message;
        msg.classList.remove('hidden');
    } catch (e) { }
}
