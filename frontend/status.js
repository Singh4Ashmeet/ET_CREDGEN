document.addEventListener('DOMContentLoaded', () => {
    const lookupForm = document.getElementById('lookup-form');
    const statusResult = document.getElementById('status-result');
    const checkBtn = document.getElementById('check-status-btn');
    const errorContainer = document.getElementById('error-container');

    const phoneInput = document.getElementById('status-phone');
    const panInput = document.getElementById('status-pan');

    const appIdEl = document.getElementById('app-id');
    const appDateEl = document.getElementById('app-date');
    const statusBadge = document.getElementById('status-badge');
    const resAmount = document.getElementById('res-amount');
    const resType = document.getElementById('res-type');
    const timelineEl = document.getElementById('status-timeline');
    const actionContainer = document.getElementById('action-container');

    const formatIndian = (n) => {
        const x = n.toString();
        let lastThree = x.substring(x.length - 3);
        const otherNumbers = x.substring(0, x.length - 3);
        if (otherNumbers !== '') lastThree = ',' + lastThree;
        return otherNumbers.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + lastThree;
    };

    const stages = [
        "Application Submitted",
        "KYC Verified",
        "Fraud Check Cleared",
        "Underwriting Complete",
        "Offer Presented",
        "Sanctioned",
        "Disbursed"
    ];

    checkBtn.addEventListener('click', async () => {
        const phone = phoneInput.value.trim();
        const pan = panInput.value.trim().toUpperCase();

        if (phone.length !== 10 || pan.length !== 10) {
            showError("Please enter a valid 10-digit phone number and PAN.");
            return;
        }

        checkBtn.disabled = true;
        checkBtn.textContent = "Checking...";
        errorContainer.classList.add('hidden');

        try {
            // Mocking the API call as per requirements (logical flow)
            // In a real app, this would be: await fetch(`/api/status?phone=${phone}&pan=${pan}`)
            const response = await fetch(`/status/lookup?phone=${phone}&pan=${pan}`);
            
            if (!response.ok) {
                throw new Error("Application not found.");
            }

            const data = await response.json();
            renderStatus(data);
        } catch (err) {
            showError(err.message || "No application found for these details. Please check and try again.");
            checkBtn.disabled = false;
            checkBtn.textContent = "Check Status →";
        }
    });

    const showError = (msg) => {
        errorContainer.textContent = msg;
        errorContainer.classList.remove('hidden');
    };

    const renderStatus = (data) => {
        lookupForm.classList.add('hidden');
        statusResult.classList.remove('hidden');

        appIdEl.textContent = data.application_id || `APP-${Math.floor(Math.random()*900000 + 100000)}`;
        appDateEl.textContent = data.created_at || "22 Mar 2026";
        
        const status = (data.status || 'pending').toLowerCase();
        statusBadge.textContent = status;
        statusBadge.className = `status-badge badge-${status}`;

        resAmount.textContent = `₹${formatIndian(data.amount || 500000)}`;
        resType.textContent = `${data.loan_purpose || 'Personal'} Loan`;

        // Timeline Logic
        const currentStageIdx = stages.indexOf(data.current_stage_name || "Application Submitted");
        timelineEl.innerHTML = '';

        stages.forEach((stage, idx) => {
            const item = document.createElement('div');
            item.className = 'timeline-item';
            if (idx < currentStageIdx) item.classList.add('complete');
            if (idx === currentStageIdx) item.classList.add('active');

            item.innerHTML = `
                <div class="timeline-content">
                    <h5>${stage}</h5>
                    <p>${idx <= currentStageIdx ? 'Completed' : 'Pending'}</p>
                </div>
            `;
            timelineEl.appendChild(item);
        });

        // Actions
        actionContainer.innerHTML = '';
        if (status === 'sanctioned' || status === 'disbursed') {
            actionContainer.innerHTML = `
                <button class="primary-btn" style="width: 100%;">⬇ Download Sanction Letter</button>
            `;
        } else if (status === 'rejected') {
            actionContainer.innerHTML = `
                <div style="background: rgba(220, 38, 38, 0.1); padding: 16px; border-radius: 8px; margin-bottom: 16px;">
                    <p style="color: var(--brand-danger); font-size: 0.9rem;">Reason: ${data.rejection_reason || 'Credit criteria not met'}</p>
                </div>
                <button class="primary-btn" onclick="window.location.href='index.html'" style="width: 100%;">+ Apply Again</button>
            `;
        }
    };
});
