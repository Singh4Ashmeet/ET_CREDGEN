/* ═══════════════════════════════════════════════════════════════
   CREDGEN — CHAT.JS  (complete rewrite)
   ═══════════════════════════════════════════════════════════════ */

// ─── STATE ───────────────────────────────────────────────────────
let sessionId = null;
let currentStage = 'collecting_details';
let isDark = true; // Default dark-first theme
let calculatorOpen = false;
let isProcessing = false;

// ─── DOM REFS ────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const landingPage = $('landing-page');
const chatApp = $('chat-app');
const messagesContainer = $('messages-container');
const typingIndicator = $('typing-indicator');
const chipsContainer = $('chips-container');
const userInput = $('user-input');
const charCounter = $('char-counter');
const panelBody = $('panel-body');
const panelTitle = $('panel-title');
const inputHint = $('input-hint');
const calcPanel = $('calculator-panel');

// ─── STAGE → STEP MAPPING ───────────────────────────────────────
const STAGE_STEP_MAP = {
    greeting: 0,
    collecting_details: 0,
    kyc_collection: 1,
    fraud_check: 2,
    underwriting: 3,
    offer_presentation: 4,
    rejection_counseling: 4,
    documentation: 5,
    closed: 5,
};

// ═══════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════

function startApplication() {
    sessionStorage.setItem('landingScrollY', window.scrollY);

    const landing = document.getElementById('landing-page');
    const chatApp = document.getElementById('chat-app');
    if (landing) {
        landing.style.opacity = '0';
        landing.style.transition = 'opacity 0.4s ease';
        setTimeout(() => {
            landing.style.display = 'none';
        }, 400);
    }
    if (chatApp) {
        setTimeout(() => {
            chatApp.classList.remove('hidden');
            chatApp.style.display = 'flex';
            chatApp.style.opacity = '0';
            chatApp.style.transition = 'opacity 0.4s ease';
            setTimeout(() => {
                chatApp.style.opacity = '1';
            }, 50);
        }, 400);
    }
    initChat();
}

function initChat() {
    if (!sessionId) {
        sessionId = 'session_' + Date.now() + '_'
            + Math.random().toString(36).slice(2, 10);
        localStorage.setItem('credgen_session_id', sessionId);
    }
    // Show welcome message locally — NO fetch call
    addMessage(
        "Welcome to CredGen AI!\n\n"
        + "I'm your AI loan assistant. I'll help you get a loan "
        + "in just a few minutes — no branch visits, no paperwork.\n\n"
        + "What kind of loan are you looking for?",
        'bot'
    );
    showChips([
        'Personal loan',
        'Home loan',
        'Business loan',
        'Education loan'
    ]);
    enableInput();
    updateProgressTracker('collecting_details', 0);
}

function toggleContextPanel() {
    const panel = $('context-panel');
    if (panel) {
        panel.classList.toggle('show');
    }
}

function backToLanding() {
    chatApp.classList.add('hidden');
    chatApp.style.display = 'none';
    chatApp.style.opacity = '0';

    landingPage.classList.remove('hidden');
    landingPage.style.display = 'block';

    setTimeout(() => {
        landingPage.style.opacity = '1';
        window.scrollTo({
            top: parseInt(sessionStorage.getItem('landingScrollY') || '0'),
            behavior: 'auto'
        });
    }, 50);
}

// ═══════════════════════════════════════════════════════════════
// THEME
// ═══════════════════════════════════════════════════════════════

function toggleTheme() {
    isDark = !isDark;
    const theme = isDark ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', isDark ? '' : 'light');
    localStorage.setItem('credgen_theme', theme);

    // Update both toggle buttons (if they exist)
    const buttons = [$('theme-toggle'), $('btn-theme')];
    buttons.forEach(btn => {
        if (!btn) return;
        const icon = btn.querySelector('i');
        if (icon) {
            icon.className = isDark ? 'bi bi-moon-stars' : 'bi bi-sun-fill';
        }
    });

    console.log(`[CredGen] Theme toggled to: ${theme}`);
}

// ═══════════════════════════════════════════════════════════════
// MESSAGE RENDERING  (BUG 1 FIX)
// ═══════════════════════════════════════════════════════════════

function addMessage(text, role, extras) {
    if (!text && role === 'bot') {
        console.warn('[CredGen] Empty bot message, skipping render');
        return;
    }

    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    if (role === 'bot') {
        avatar.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>';
    } else {
        avatar.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
    }

    const content = document.createElement('div');
    content.className = 'msg-content';

    // Strip markdown bold (**text**) for cleaner display
    const cleaned = (text || '').replace(/\*\*(.*?)\*\*/g, '$1');
    content.textContent = cleaned;

    const time = document.createElement('span');
    time.className = 'msg-time';
    time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    msg.appendChild(avatar);
    const wrapper = document.createElement('div');
    wrapper.appendChild(content);
    wrapper.appendChild(time);
    msg.appendChild(wrapper);

    messagesContainer.appendChild(msg);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showTyping() {
    typingIndicator.classList.remove('hidden');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function hideTyping() {
    typingIndicator.classList.add('hidden');
}

// ═══════════════════════════════════════════════════════════════
// CHIPS
// ═══════════════════════════════════════════════════════════════

function showChips(suggestions) {
    if (!suggestions || suggestions.length === 0) {
        chipsContainer.classList.add('hidden');
        return;
    }
    chipsContainer.innerHTML = '';

    const chipValueMap = {
        '₹1 lakh': '1 lakh',
        '₹3 lakh': '3 lakh',
        '₹5 lakh': '5 lakh',
        '₹10 lakh': '10 lakh',
        '₹25,000/month': '25000',
        '₹50,000/month': '50000',
        '₹1 lakh/month': '100000',
        'Personal use': 'personal',
        'Home purchase': 'home',
        'Salaried': 'salaried',
        'Self-employed': 'self employed',
        'Business owner': 'business owner',
        'Retired': 'retired',
        '1 year': '12 months',
        '2 years': '24 months',
        '3 years': '36 months',
        '5 years': '60 months',
        'Skip email': 'skip',
    };

    suggestions.forEach(text => {
        const chip = document.createElement('button');
        chip.className = 'chip';
        chip.textContent = text;
        chip.onclick = () => {
            if (isProcessing) return;

            chipsContainer.querySelectorAll('.chip').forEach(c => {
                c.disabled = true;
                c.classList.add('used');
            });
            chip.classList.add('selected');
            chip.textContent = '✓ ' + text;

            const sendValue = chipValueMap[text] || text;

            addMessage(text, 'user');
            userInput.value = '';
            if (typeof updateCharCounter === 'function') updateCharCounter();

            setTimeout(() => {
                chipsContainer.classList.add('hidden');
            }, 400);

            sendToBackend(sendValue);
        };
        chipsContainer.appendChild(chip);
    });
    chipsContainer.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════
// PROGRESS TRACKER
// ═══════════════════════════════════════════════════════════════

function updateProgressTracker(stage, progress) {
    const stageToStep = {
        'collecting_details': 0,
        'COLLECTING_DETAILS': 0,
        'greeting': 0,
        'kyc_collection': 1,
        'kyc_pending': 1,
        'KYC_COLLECTION': 1,
        'fraud_check': 2,
        'FRAUD_CHECK': 2,
        'underwriting': 3,
        'UNDERWRITING': 3,
        'offer_presentation': 4,
        'OFFER_PRESENTATION': 4,
        'offer_presented': 4,
        'rejection_counseling': 4,
        'REJECTION_COUNSELING': 4,
        'documentation': 5,
        'DOCUMENTATION': 5,
        'closed': 5,
        'CLOSED': 5,
    };

    const activeStep = stageToStep[stage] || 0;

    // Support both class structures
    const steps = document.querySelectorAll('.tracker-step, .step');
    const lines = document.querySelectorAll('.tracker-line, .step-line');

    steps.forEach((el, index) => {
        el.classList.remove('active', 'complete', 'completed');
        if (index < activeStep) {
            el.classList.add('complete', 'completed');
            const circle = el.querySelector('.step-circle');
            if (circle) circle.textContent = '✓';
        } else if (index === activeStep) {
            el.classList.add('active');
        }
    });
    lines.forEach((el, index) => {
        const isComplete = index < activeStep;
        el.classList.toggle('filled', isComplete);
        el.classList.toggle('completed', isComplete);
    });
}

// ═══════════════════════════════════════════════════════════════
// CONTEXT PANEL
// ═══════════════════════════════════════════════════════════════

function updateContextPanel(response) {
    const stage = response.stage || currentStage;
    const entities = response.entities_collected || {};
    const missing = response.missing_fields || [];
    const missingKyc = response.missing_kyc_fields || [];

    if (stage === 'collecting_details' || stage === 'greeting') {
        panelTitle.textContent = 'Application Checklist';
        const allFields = ['loan_amount', 'purpose', 'name', 'age', 'employment_type', 'income', 'tenure'];
        const labels = {
            loan_amount: 'Loan Amount', purpose: 'Purpose', name: 'Full Name',
            age: 'Age', employment_type: 'Employment', income: 'Income', tenure: 'Tenure'
        };
        let html = '<ul class="checklist">';
        allFields.forEach(f => {
            const done = !!entities[f];
            const icon = done ? '✓' : '○';
            const cls = done ? 'done' : 'pending';
            const val = done ? ` — ${formatValue(f, entities[f])}` : '';
            html += `<li><span class="check-icon ${cls}">${icon}</span>${labels[f] || f}${val}</li>`;
        });
        html += '</ul>';
        panelBody.innerHTML = html;

    } else if (stage === 'kyc_collection') {
        panelTitle.textContent = 'KYC Verification';
        const kycFields = ['pan', 'aadhaar', 'address', 'pincode'];
        const labels = { pan: 'PAN Card', aadhaar: 'Aadhaar', address: 'Address', pincode: 'Pincode' };
        let html = '<ul class="checklist">';
        kycFields.forEach(f => {
            const done = !!entities[f];
            const icon = done ? '✓' : '○';
            const cls = done ? 'done' : 'pending';
            html += `<li><span class="check-icon ${cls}">${icon}</span>${labels[f] || f}</li>`;
        });
        html += '</ul>';
        panelBody.innerHTML = html;

    } else if (stage === 'fraud_check' || stage === 'underwriting') {
        panelTitle.textContent = 'Processing';
        panelBody.innerHTML = `
            <div class="processing-card">
                <div class="spinner"></div>
                <p>${stage === 'fraud_check' ? 'Running security verification...' : 'Analyzing your application...'}</p>
            </div>
        `;

    } else if (stage === 'offer_presentation') {
        panelTitle.textContent = 'Your Loan Offer';
        const offer = response.offer || {};
        if (offer.loan_amount) {
            panelBody.innerHTML = `
                <div class="offer-card">
                    <h4>Loan Offer</h4>
                    <div class="offer-row"><span class="label">Amount</span><span class="value">₹${fmtINR(offer.loan_amount)}</span></div>
                    <div class="offer-row"><span class="label">Rate</span><span class="value">${offer.interest_rate}% p.a.</span></div>
                    <div class="offer-row"><span class="label">Tenure</span><span class="value">${offer.tenure_months} months</span></div>
                    <div class="offer-row"><span class="label">EMI</span><span class="value">₹${fmtINR(offer.monthly_emi)}</span></div>
                    <div class="offer-row"><span class="label">Processing Fee</span><span class="value">₹${fmtINR(offer.processing_fee)}</span></div>
                </div>
            `;
        }

    } else if (stage === 'documentation' || stage === 'closed') {
        panelTitle.textContent = 'Sanction Letter';
        const details = response.sanction_details || {};
        panelBody.innerHTML = `
            <div class="sanction-card">
                <h4>Sanction Letter Ready</h4>
                <p>${details.applicant_name || 'Applicant'}</p>
                <p>₹${fmtINR(details.amount || 0)}</p>
                <a class="btn-download" href="${response.download_url || '#'}" target="_blank">Download PDF</a>
            </div>
        `;
    }
}

function formatValue(field, value) {
    if (field === 'loan_amount' || field === 'income') return '₹' + fmtINR(value);
    if (field === 'tenure') return value + ' months';
    if (field === 'age') return value + ' yrs';
    return value;
}

function fmtINR(n) {
    try {
        n = Math.round(Number(n));
        const s = String(n);
        if (s.length <= 3) return s;
        const last = s.slice(-3);
        let rest = s.slice(0, -3);
        const parts = [];
        while (rest.length) { parts.unshift(rest.slice(-2)); rest = rest.slice(0, -2); }
        return parts.join(',') + ',' + last;
    } catch { return String(n); }
}

// ═══════════════════════════════════════════════════════════════
// SEND MESSAGE
// ═══════════════════════════════════════════════════════════════

function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isProcessing) return;

    addMessage(text, 'user');
    userInput.value = '';
    updateCharCounter();
    chipsContainer.classList.add('hidden');

    sendToBackend(text);
}

async function sendToBackend(text) {
    isProcessing = true;
    showTyping();

    try {
        const resp = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId,
            },
            body: JSON.stringify({ message: text }),
        });

        const data = await resp.json();
        console.log('[CredGen] API response:', data);

        // BUG 1 guard: ensure we have a message
        const botText = data.message || data.msg || '';
        if (botText) {
            hideTyping();
            addMessage(botText, 'bot');
        } else {
            hideTyping();
            addMessage('I received your message. Let me process that.', 'bot');
        }

        // Update session ID from header if present
        const newSession = resp.headers.get('X-Session-ID');
        if (newSession) sessionId = newSession;

        // Update stage
        if (data.stage) {
            currentStage = data.stage;
            updateProgressTracker(currentStage, data.workflow_progress);
        }

        // Show suggestions
        if (data.suggestions && data.suggestions.length > 0) {
            showChips(data.suggestions);
        }

        // Update context panel
        updateContextPanel(data);

        // Auto-trigger worker actions
        if (data.worker && data.worker !== 'none' && data.action && data.action !== 'none') {
            triggerWorker(data.worker, data.action);
        } else {
            enableInput();
        }

    } catch (err) {
        console.error('[CredGen] Fetch error:', err);
        hideTyping();
        addMessage('Sorry, there was a connection issue. Please try again.', 'bot');
        enableInput();
    }
    // No finally block modifying isProcessing, worker triggers handle their own lock.
}

// ═══════════════════════════════════════════════════════════════
// WORKER ACTIONS  (fraud, underwriting, sales, documentation)
// ═══════════════════════════════════════════════════════════════

function enableInput() {
    isProcessing = false;
    userInput.focus();
}

function showProcessingCard(worker) {
    showTyping(); // ensure user sees action is happening
    try {
        const panel = document.getElementById('panel-body');
        if (!panel) return;

        const labels = {
            'fraud': 'Running security verification...',
            'underwriting': 'Assessing your creditworthiness...',
            'documentation': 'Generating your sanction letter...',
            'sales': 'Preparing your loan offer...',
        };
        const label = labels[worker] || 'Processing...';

        panel.innerHTML = `
            <div class="processing-card">
                <div class="spinner"></div>
                <p>${label}</p>
                <small id="elapsed-timer">0s</small>
            </div>`;

        // Elapsed time counter
        let seconds = 0;
        window._processingTimer = setInterval(() => {
            seconds++;
            const el = document.getElementById('elapsed-timer');
            if (el) el.textContent = seconds + 's';
        }, 1000);
    } catch (e) {
        console.warn('[UI] showProcessingCard failed:', e);
    }
}

function hideProcessingCard() {
    hideTyping();
    try {
        if (window._processingTimer) {
            clearInterval(window._processingTimer);
            window._processingTimer = null;
        }
    } catch (e) {
        console.warn('[UI] hideProcessingCard failed:', e);
    }
}

async function triggerWorker(worker, action) {
    if (worker === 'none') return;

    isProcessing = true;
    showProcessingCard(worker);

    try {
        const endpointMap = {
            'call_fraud_api': '/fraud',
            'call_underwriting_api': '/underwrite',
            'call_sales_api': '/sales',
            'call_documentation_api': '/documentation',
            'fraud': '/fraud',
            'underwriting': '/underwrite',
            'sales': '/sales',
            'documentation': '/documentation'
        };

        let url = endpointMap[action] || endpointMap[worker];
        if (!url) {
            console.warn('[WORKER] No URL for action:', action);
            hideProcessingCard();
            enableInput();
            return;
        }

        console.log(`[WORKER] Calling ${url} for worker: ${worker}, action: ${action}`);

        const controller = new AbortController();
        const timer = setTimeout(() => {
            console.warn(`[WORKER] ${url} timed out after 30s`);
            controller.abort();
        }, 30000);

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId
            },
            body: JSON.stringify({ action: 'generate' }),
            signal: controller.signal
        });
        clearTimeout(timer);

        console.log(`[WORKER] ${url} responded with status:`, response.status);

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errText.slice(0, 200)}`);
        }

        // Robust JSON parsing fallback
        let data;
        try {
            data = await response.json();
        } catch (je) {
            throw new Error("Server returned non-JSON response (likely a crash logs page).");
        }

        console.log(`[WORKER] ${url} data:`, data);

        hideProcessingCard();

        // Always show the worker's text
        if (data.message) {
            addMessage(data.message, 'bot');
        } else {
            addMessage(`${worker.charAt(0).toUpperCase() + worker.slice(1)} check completed.`, 'bot');
        }

        if (data.stage) {
            currentStage = data.stage;
            updateProgressTracker(data.stage, data.workflow_progress || 0);
        }

        updateContextPanel(data);

        // Special UI handling for specific step outputs
        if (url === '/sales' && data.offer) {
            updateContextPanel({ stage: 'offer_presentation', offer: data.offer });
            if (data.offer.suggestions) {
                showChips(data.offer.suggestions);
            } else {
                showChips(['Accept Offer', 'Negotiate Rate', 'Decline']);
            }
        } else if (url === '/documentation' && data.pdf_path) {
            updateContextPanel({
                stage: 'documentation',
                sanction_details: data.sanction_details,
                download_url: data.download_url
            });
        }

        // ── CHAIN TO NEXT WORKER ──────────────────────────────────
        // Explicit chaining — don't rely on generic condition alone
        const nextAction = data.action;
        const nextWorker = data.worker;

        console.log(`[WORKER] Next: worker=${nextWorker}, action=${nextAction}`);

        const shouldChain = nextAction
            && nextAction !== 'none'
            && nextAction !== 'wait_for_offer_decision'
            && endpointMap[nextAction];

        if (shouldChain) {
            console.log(`[WORKER] Chaining to: ${nextAction} in 1.5s`);
            setTimeout(() => triggerWorker(nextWorker, nextAction), 1500);
        } else if (nextWorker && nextWorker !== 'none') {
            if (nextWorker !== worker) {
                console.log(`[WORKER] Chaining (fallback) to: worker=${nextWorker} in 1.5s`);
                setTimeout(() => triggerWorker(nextWorker, 'generate'), 1500);
            } else {
                enableInput();
            }
        } else {
            console.log('[WORKER] No chaining — waiting for user input');
            enableInput();
        }

    } catch (error) {
        hideProcessingCard();
        console.error(`[WORKER] ${worker} failed:`, error);
        addMessage(`Process taking longer than expected or ran into an issue. Retrying...`, 'bot');
        if (error.name !== 'AbortError') {
            setTimeout(() => triggerWorker(worker, action), 2000);
        } else {
            enableInput();
        }
    }
}


// ═══════════════════════════════════════════════════════════════
// EMI CALCULATOR (BUG 2 + BUG 3 FIX)
// ═══════════════════════════════════════════════════════════════

function toggleCalculator() {
    calculatorOpen = !calculatorOpen;
    calcPanel.classList.toggle('hidden', !calculatorOpen);
    if (calculatorOpen) calculateEMI();
}

function calculateEMI() {
    const P = parseFloat($('calc-amount').value);
    const annualRate = parseFloat($('calc-rate').value);
    const N = parseFloat($('calc-tenure').value);

    $('calc-amount-val').textContent = fmtINR(P);
    $('calc-rate-val').textContent = annualRate.toFixed(1);
    $('calc-tenure-val').textContent = N;

    if (P > 0 && annualRate > 0 && N > 0) {
        const r = annualRate / 12 / 100;
        const emi = P * r * Math.pow(1 + r, N) / (Math.pow(1 + r, N) - 1);
        const total = emi * N;
        const interest = total - P;

        $('calc-emi').textContent = '₹' + fmtINR(Math.round(emi));
        $('calc-total').textContent = '₹' + fmtINR(Math.round(total));
        $('calc-interest').textContent = '₹' + fmtINR(Math.round(interest));
    }
}

// ═══════════════════════════════════════════════════════════════
// INPUT INTELLIGENCE
// ═══════════════════════════════════════════════════════════════

function checkInputIntelligence(text) {
    if (!text) {
        inputHint.classList.add('hidden');
        return;
    }

    // Phone detection
    const phoneMatch = text.match(/\b[6-9]\d{9}\b/);
    if (phoneMatch) {
        showHint('Phone number detected', 'valid');
        return;
    }

    // PAN detection
    const panMatch = text.toUpperCase().match(/\b[A-Z]{5}\d{4}[A-Z]\b/);
    if (panMatch) {
        showHint('PAN number detected', 'valid');
        return;
    }

    // Aadhaar detection
    const aadhaarMatch = text.match(/\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/);
    if (aadhaarMatch) {
        showHint('Aadhaar number detected', 'valid');
        return;
    }

    // Pincode detection
    const pincodeMatch = text.match(/\b\d{6}\b/);
    if (pincodeMatch && !aadhaarMatch) {
        showHint('Pincode detected', 'valid');
        return;
    }

    // Amount detection
    const amountMatch = text.match(/(?:₹|rs\.?\s*)?(\d[\d,]*)\s*(?:lakh|lac|l)/i);
    if (amountMatch) {
        const val = parseFloat(amountMatch[1].replace(/,/g, '')) * 100000;
        showHint(`₹${fmtINR(val)}`, 'valid');
        return;
    }

    inputHint.classList.add('hidden');
}

function showHint(text, type) {
    inputHint.textContent = text;
    inputHint.className = `input-hint ${type}`;
    inputHint.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════
// INPUT HANDLERS
// ═══════════════════════════════════════════════════════════════

function updateCharCounter() {
    const len = userInput.value.length;
    charCounter.textContent = `${len}/1000`;
}

function autoGrowTextarea() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
}

// ═══════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // Input event listeners
    userInput.addEventListener('input', () => {
        updateCharCounter();
        autoGrowTextarea();
        checkInputIntelligence(userInput.value);
    });

    userInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-uppercase PAN in input
    userInput.addEventListener('input', () => {
        const val = userInput.value;
        if (/^[A-Za-z]{1,5}\d{0,4}[A-Za-z]?$/.test(val) && val.length <= 10) {
            userInput.value = val.toUpperCase();
        }
    });

    // Calculator slider listeners (BUG 2 FIX)
    const calcSliders = ['calc-amount', 'calc-rate', 'calc-tenure'];
    calcSliders.forEach(id => {
        const el = $(id);
        if (el) el.addEventListener('input', calculateEMI);
    });

    // Calculator is CLOSED by default (BUG 3 FIX)
    // Already hidden via HTML class

    // Load saved inputs to prevent data loss
    const savedInput = sessionStorage.getItem('credgen_user_input');
    if (savedInput && userInput) {
        userInput.value = savedInput;
        updateCharCounter();
        autoGrowTextarea();
    }

    userInput.addEventListener('input', () => {
        sessionStorage.setItem('credgen_user_input', userInput.value);
    });

    // Handle Theme on load
    const savedTheme = localStorage.getItem('credgen_theme');
    if (savedTheme === 'light') {
        isDark = false;
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        isDark = true;
        document.documentElement.removeAttribute('data-theme');
    }
    
    // Sync all theme icons
    [document.getElementById('theme-toggle'), document.getElementById('btn-theme')].forEach(btn => {
        if (!btn) return;
        const icon = btn.querySelector('i');
        if (icon) icon.className = isDark ? 'bi bi-moon-stars' : 'bi bi-sun-fill';
    });
    // File input handling
    const fileInput = $('file-input');
    if (fileInput) {
        fileInput.addEventListener('change', e => {
            const files = e.target.files;
            if (files && files.length > 0) {
                const names = Array.from(files).map(f => f.name).join(', ');
                addMessage(`Paperclip: Attached ${files.length} file(s): ${names}`, 'user');

                // Show a bot confirmation
                setTimeout(() => {
                    addMessage("I've received your documents. I'll analyze them as we proceed with the application.", 'bot');
                }, 800);
            }
        });
    }
});
