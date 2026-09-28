/* PATIENT PORTAL — patient_scripts.js */

document.addEventListener('DOMContentLoaded', () => {

    /* 1. MOBILE SIDEBAR TOGGLE  (all pages)*/
    const menuBtn       = document.getElementById('menuBtn');
    const sidebar       = document.getElementById('sidebar');
    const mobileOverlay = document.getElementById('mobileOverlay');

    if (menuBtn && sidebar) {
        menuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('active');
            mobileOverlay.classList.toggle('active');
        });
    }
    if (mobileOverlay) {
        mobileOverlay.addEventListener('click', () => {
            sidebar.classList.remove('active');
            mobileOverlay.classList.remove('active');
        });
    }

    let touchStartX = 0;
    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });
    document.addEventListener('touchend', e => {
        if (sidebar && sidebar.classList.contains('active') &&
            (touchStartX - e.changedTouches[0].screenX) > 50) {
            sidebar.classList.remove('active');
            if (mobileOverlay) mobileOverlay.classList.remove('active');
        }
    }, { passive: true });

    /* 1b. LOGIN PAGE: Patient ID auto-format + password toggle */
    const patientCodeInput = document.getElementById('patient_code');
    if (patientCodeInput) {
        patientCodeInput.addEventListener('input', e => {
            let raw = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            const match = raw.match(/^([A-Z]+)(\d{0,4})(\d*)$/);
            if (!match) { e.target.value = raw; return; }
            const [, prefix, year, sequence] = match;
            let formatted = prefix;
            if (year) formatted += '-' + year;
            if (sequence) formatted += '-' + sequence;
            e.target.value = formatted;
        });
    }

    const loginPwInput  = document.getElementById('password');
    const loginPwToggle = document.getElementById('togglePatientLoginPassword');
    if (loginPwInput && loginPwToggle) {
        loginPwToggle.addEventListener('click', () => {
            const isHidden = loginPwInput.type === 'password';
            loginPwInput.type = isHidden ? 'text' : 'password';
            loginPwToggle.textContent = isHidden ? 'Hide' : 'Show';
        });
    }

    /* 2. AVATAR UPLOAD  (all pages — sidebar + settings) */

    // Sidebar avatar (patient_base.html)
    const sidebarAvatarUpload   = document.getElementById('avatarUpload');
    const sidebarAvatarImg      = document.getElementById('userAvatar');
    const sidebarAvatarFallback = document.getElementById('userAvatarFallback');

    // Settings page avatar (patient_settings.html)
    const settingsAvatarUpload   = document.getElementById('settingsAvatarUpload');
    const settingsAvatarImg      = document.getElementById('settingsAvatarImg');
    const settingsAvatarFallback = document.getElementById('settingsAvatarFallback');

    function applyAvatar(dataUrl) {
        [
            [sidebarAvatarImg,   sidebarAvatarFallback],
            [settingsAvatarImg,  settingsAvatarFallback],
        ].forEach(([img, fallback]) => {
            if (img) {
                img.src = dataUrl;
                img.style.display = 'block';
                if (fallback) fallback.style.display = 'none';
            }
        });
    }

    // Restore saved avatar on every page load
    try {
        const saved = localStorage.getItem('patientAvatar');
        if (saved) applyAvatar(saved);
    } catch (e) {}

    function handleAvatarUpload(input) {
        if (!input) return;
        input.addEventListener('change', e => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = ev => {
                applyAvatar(ev.target.result);
                try { localStorage.setItem('patientAvatar', ev.target.result); } catch (err) {}
                if (settingsAvatarImg) showToast('Profile photo updated.');
            };
            reader.readAsDataURL(file);
        });
    }
    handleAvatarUpload(sidebarAvatarUpload);
    handleAvatarUpload(settingsAvatarUpload);


    /* 3. SCROLL-TO-TOP BUTTON  (all pages) Always tracks window scroll — same as nurse base. */
    const scrollTopBtn = document.getElementById('scrollTopBtn');
    if (scrollTopBtn) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 300) {
                scrollTopBtn.classList.add('visible');
            } else {
                scrollTopBtn.classList.remove('visible');
            }
        }, { passive: true });

        scrollTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }


    /*  4. DASHBOARD: Download PDF button */
    const downloadPdfBtn = document.getElementById('downloadPdfBtn');
    if (downloadPdfBtn) {
        downloadPdfBtn.addEventListener('click', () => window.print());
    }


    /*  5. RESULTS PAGE: showDetail + print/download */

    // Attach click handlers to all screening cards
    document.querySelectorAll('.screening-card').forEach(card => {
        card.addEventListener('click', () => showDetail(card.dataset.id));
    });

    // Attach print/download buttons inside detail views
    document.querySelectorAll('[data-print-id]').forEach(btn => {
        btn.addEventListener('click', () => printDetail(btn.dataset.printId));
    });
    document.querySelectorAll('[data-download-id]').forEach(btn => {
        btn.addEventListener('click', () => printDetail(btn.dataset.downloadId));
    });

    // Print All / Download All buttons
    const printAllBtn    = document.getElementById('printAllBtn');
    const downloadAllBtn = document.getElementById('downloadAllBtn');
    if (printAllBtn)    printAllBtn.addEventListener('click',    () => window.print());
    if (downloadAllBtn) downloadAllBtn.addEventListener('click', () => window.print());

    const params = new URLSearchParams(window.location.search);
    const visitParam = params.get('visit');
    if (visitParam) showDetail('visit-' + visitParam);

    const backToListBtn = document.getElementById('backToListBtn');
    if (backToListBtn) {
        backToListBtn.addEventListener('click', () => {
            document.getElementById('detailPanel').classList.remove('mobile-open');
            document.querySelector('.history-list-panel').classList.remove('mobile-hidden');
        });
    }


    /* 6. SETTINGS PAGE */

    // Tab switching
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Password show/hide toggles
    const EYE_OPEN = `<svg class="pw-eye-icon" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M1 10C3.5 5.5 7 3 10 3s6.5 2.5 9 7c-2.5 4.5-6 7-9 7s-6.5-2.5-9-7z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.5"/></svg>`;
    const EYE_SHUT = `<svg class="pw-eye-icon" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path d="M1 10C3.5 5.5 7 3 10 3s6.5 2.5 9 7c-2.5 4.5-6 7-9 7s-6.5-2.5-9-7z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="10" cy="10" r="2.5" stroke="currentColor" stroke-width="1.5"/><line x1="3" y1="3" x2="17" y2="17" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;

    document.querySelectorAll('.pw-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const input = document.getElementById(btn.dataset.pwTarget);
            if (!input) return;
            if (input.type === 'password') {
                input.type = 'text';
                btn.innerHTML = EYE_SHUT;
            } else {
                input.type = 'password';
                btn.innerHTML = EYE_OPEN;
            }
        });
    });

    // Password strength meter
    const pwNewInput = document.getElementById('pwNew');
    if (pwNewInput) {
        pwNewInput.addEventListener('input', () => checkPwStrength(pwNewInput.value));
    }

    // Password change submit
    const pwChangeBtn = document.getElementById('pwChangeBtn');
    if (pwChangeBtn) {
        pwChangeBtn.addEventListener('click', handlePwChange);
    }

    // Save buttons (contact, notifications, emergency contact)
    document.querySelectorAll('[data-save-toast]').forEach(btn => {
        btn.addEventListener('click', () => showToast(btn.dataset.saveToast));
    });

    // Revoke session buttons
    document.querySelectorAll('.btn-revoke').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.la-item').style.opacity = '0.4';
            btn.disabled = true;
            showToast('Session revoked.');
        });
    });

    // Deactivate modal
    const deactivateBtn   = document.getElementById('deactivateBtn');
    const deactivateModal = document.getElementById('deactivateModal');
    const modalCancelBtn  = document.getElementById('modalCancelBtn');
    const modalConfirmBtn = document.getElementById('modalConfirmBtn');

    if (deactivateBtn)   deactivateBtn.addEventListener('click',   () => { deactivateModal.style.display = 'flex'; });
    if (modalCancelBtn)  modalCancelBtn.addEventListener('click',  () => { deactivateModal.style.display = 'none'; });
    if (modalConfirmBtn) modalConfirmBtn.addEventListener('click', () => {
        showToast('Account deactivation request submitted.');
        deactivateModal.style.display = 'none';
    });

    // Sign-out-all button
    const signOutAllBtn = document.getElementById('signOutAllBtn');
    if (signOutAllBtn) {
        signOutAllBtn.addEventListener('click', () => showToast('All other sessions signed out.'));
    }

    // Download data button
    const downloadDataBtn = document.getElementById('downloadDataBtn');
    if (downloadDataBtn) {
        downloadDataBtn.addEventListener('click', () => window.print());
    }

    const viewPrivacyBtn = document.getElementById('viewPrivacyBtn');
    const legalModal = document.getElementById('legalModal');
    const closeLegalModal = document.getElementById('closeLegalModal');
    if (viewPrivacyBtn && legalModal) {
        viewPrivacyBtn.addEventListener('click', e => {
            e.preventDefault();
            document.getElementById('modal-title').textContent = 'Privacy Policy';
            document.getElementById('modal-body').innerHTML = `
                <p>1. <strong>Collection:</strong> We collect health data for screening purposes.</p>
                <p>2. <strong>Security:</strong> Data is stored securely on local LHU hardware.</p>
                <p>3. <strong>Patient Rights:</strong> Patients have rights under RA 10173 to access their records.</p>
            `;
            legalModal.style.display = 'flex';
        });
        closeLegalModal.addEventListener('click', () => legalModal.style.display = 'none');
        legalModal.addEventListener('click', e => { if (e.target === legalModal) legalModal.style.display = 'none'; });
    }

    const consentToggle = document.getElementById('consentResearch');
    if (consentToggle) {
        consentToggle.addEventListener('change', async () => {
            try {
                const res = await fetch('/patient_update_consent', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ consent: consentToggle.checked }),
                });
                if (!res.ok) throw new Error('Failed');
                showToast(consentToggle.checked ? 'Consent enabled.' : 'Consent withdrawn.');
            } catch (err) {
                consentToggle.checked = !consentToggle.checked; // revert on failure
                showToast('Could not update consent. Try again.', 'warn');
            }
        });
}

});


/*  RESULTS: showDetail (global — called by page init)*/
function showDetail(id) {
    // Update list cards
    document.querySelectorAll('.screening-card').forEach(c => c.classList.remove('active'));
    const card = document.querySelector('[data-id="' + id + '"]');
    if (card) card.classList.add('active');

    // Update detail views
    document.querySelectorAll('.detail-view').forEach(d => d.classList.remove('active'));
    const detail = document.getElementById('detail-' + id);
    if (detail) detail.classList.add('active');

    // Mobile: show detail panel, hide list
    if (window.innerWidth < 768) {
        const detailPanel = document.getElementById('detailPanel');
        const listPanel   = document.querySelector('.history-list-panel');
        if (detailPanel) detailPanel.classList.add('mobile-open');
        if (listPanel)   listPanel.classList.add('mobile-hidden');
    }
}


/* RESULTS: printDetail */
function printDetail(id) {
    const el = document.getElementById('detail-' + id);
    if (!el) return;
    // Clone so collapsed <details> sections are expanded in the printed report
    const clone = el.cloneNode(true);
    clone.querySelectorAll('details').forEach(d => d.setAttribute('open', ''));
    const content = clone.innerHTML;
    const win = window.open('', '_blank');
    win.document.write(`<!DOCTYPE html><html lang="en"><head>
        <meta charset="UTF-8">
        <title>Assessment Report</title>
        <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body { font-family:'DM Sans',sans-serif; padding:2rem; color:#1e293b; font-size:13px; }
            .detail-actions,.detail-footer,.back-btn { display:none !important; }
            .detail-date { font-size:1.3rem; font-weight:700; }
            .detail-id   { color:#94a3b8; font-size:0.85rem; margin-bottom:1.25rem; }
            .detail-cards-row { display:flex; gap:1rem; margin-bottom:1.25rem; }
            .detail-metric-card { flex:1; border:1px solid #e2e8f0; border-radius:8px; padding:1rem; }
            .warn-card { border-top:3px solid #f59e0b; background:#fef3c7; }
            .low-card  { border-top:3px solid #27ae60; background:#e8f5e9; }
            .dm-label  { font-size:0.72rem; color:#94a3b8; margin-bottom:0.4rem; text-transform:uppercase; }
            .dm-value  { font-size:1.8rem; font-weight:700; }
            .dm-value span { font-size:0.9rem; color:#94a3b8; }
            .ds-label  { font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#94a3b8; margin-bottom:.6rem; padding-bottom:.3rem; border-bottom:1px solid #e2e8f0; }
            .detail-section { margin-bottom:1.25rem; }
            .detail-data-grid { display:grid; grid-template-columns:1fr 1fr; gap:.4rem 1rem; }
            .dd-item { display:flex; flex-direction:column; }
            .dd-key  { font-size:.7rem; color:#94a3b8; margin-bottom:.1rem; }
            .dd-val  { font-size:.85rem; font-weight:600; }
            .recommendation-box { padding:.875rem 1rem; border-radius:8px; font-size:.85rem; line-height:1.6; }
            .warn-rec { border-left:4px solid #f59e0b; background:#fef3c7; }
            .low-rec  { border-left:4px solid #27ae60; background:#e8f5e9; }
            .score-bar,.range-track { height:8px; border-radius:4px; background:#e2e8f0; position:relative; display:flex; margin-bottom:.35rem; }
            .score-fill { height:100%; border-radius:4px; }
            .moderate-fill { background:#f59e0b; }
            .low-fill      { background:#27ae60; }
            .range-normal  { flex:3; background:#27ae60; border-radius:4px 0 0 4px; }
            .range-pre     { flex:2; background:#f59e0b; }
            .range-diabetic{ flex:2; background:#ef4444; border-radius:0 4px 4px 0; }
            .range-marker  { position:absolute; bottom:-2px; transform:translateX(-50%); font-size:.7rem; color:#f59e0b; }
            .range-labels  { display:flex; justify-content:space-between; font-size:.65rem; }
            .rl-normal { color:#27ae60; } .rl-pre { color:#f59e0b; } .rl-diabetic { color:#ef4444; }
            .rf-pill { display:inline-block; padding:.2rem .55rem; border-radius:20px; font-size:.72rem; margin:.15rem; }
            .warn-pill   { background:#fef3c7; color:#b45309; }
            .danger-pill { background:#fee2e2; color:#ef4444; }
            .ok-pill     { background:#e8f5e9; color:#133c20; }
            .risk-factors-grid { display:flex; flex-wrap:wrap; }
            .range-badge { display:inline-block; padding:.2rem .55rem; border-radius:5px; font-size:.72rem; font-weight:600; }
            .pre-diabetic { background:#fef3c7; color:#b45309; }
            .normal       { background:#e8f5e9; color:#133c20; }
            .diabetic     { background:#fee2e2; color:#ef4444; }
            .moderate-text { color:#f59e0b; }
            .low-text      { color:#27ae60; }
            .followup-date { color:#27ae60; font-weight:700; }
            .cvd-table { border:1px solid #e2e8f0; border-radius:6px; overflow:hidden; }
            .cvd-row   { display:flex; justify-content:space-between; align-items:center; padding:.4rem .75rem; border-bottom:1px solid #e2e8f0; font-size:.78rem; }
            .cvd-row:last-child { border-bottom:none; }
            .cvd-row-alert { background:#fff7ed; }
            .cvd-q { flex:1; color:#475569; }
            .cvd-a { font-weight:700; padding:.15rem .5rem; border-radius:4px; font-size:.72rem; }
            .cvd-no  { background:#e8f5e9; color:#133c20; }
            .cvd-yes { background:#fee2e2; color:#ef4444; }
            summary { list-style:none; }
            summary::-webkit-details-marker { display:none; }
            .detail-collapse { border-top:1px solid #e2e8f0; padding:.5rem 0; }
            .trend-arrow { display:inline-flex; align-items:center; gap:.15rem; font-size:.7rem; font-weight:700; margin-left:.3rem; }
            .trend-arrow svg { width:1.15em; height:1.15em; fill:none; stroke:currentColor; stroke-width:2.6; stroke-linecap:round; stroke-linejoin:round; }
            .trend-up { color:#ef4444; } .trend-down { color:#27ae60; }
        </style></head>
        <body>${content}</body></html>`);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 400);
}


/* SETTINGS: switchTab*/
function switchTab(tab) {
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.settings-pane').forEach(p => p.classList.remove('active'));
    const tabEl = document.querySelector('[data-tab="' + tab + '"]');
    const paneEl = document.getElementById('pane-' + tab);
    if (tabEl)  tabEl.classList.add('active');
    if (paneEl) paneEl.classList.add('active');
}


/* SETTINGS: Password helpers */
function checkPwStrength(val) {
    const fill  = document.getElementById('pwStrengthFill');
    const label = document.getElementById('pwStrengthLabel');
    if (!fill || !label) return;
    let score = 0;
    if (val.length >= 8)           score++;
    if (/[A-Z]/.test(val))         score++;
    if (/[0-9]/.test(val))         score++;
    if (/[^A-Za-z0-9]/.test(val))  score++;
    const levels = [
        { pct: '0%',   color: 'transparent', text: '' },
        { pct: '25%',  color: '#ef4444',     text: 'Weak' },
        { pct: '50%',  color: '#f59e0b',     text: 'Fair' },
        { pct: '75%',  color: '#3b82f6',     text: 'Good' },
        { pct: '100%', color: '#27ae60',     text: 'Strong' },
    ];
    fill.style.width      = levels[score].pct;
    fill.style.background = levels[score].color;
    label.textContent     = levels[score].text;
    label.style.color     = levels[score].color;
}

function handlePwChange() {
    const cur  = document.getElementById('pwCurrent');
    const nw   = document.getElementById('pwNew');
    const conf = document.getElementById('pwConfirm');
    const hint = document.getElementById('pwMatchHint');
    if (!cur || !nw || !conf) return;
    if (!cur.value || !nw.value || !conf.value) {
        showToast('Please fill in all password fields.', 'warn'); return;
    }
    if (nw.value !== conf.value) {
        hint.textContent = 'Passwords do not match.';
        hint.style.color = 'var(--danger)'; return;
    }
    if (nw.value.length < 8) {
        showToast('Password must be at least 8 characters.', 'warn'); return;
    }
    hint.textContent = '';
    showToast('Password updated successfully.');
    [cur, nw, conf].forEach(i => i.value = '');
    checkPwStrength('');
}


/* SHARED: Toast notification */
function showToast(msg, type) {
    const toast = document.getElementById('settingsToast');
    if (!toast) return;
    toast.textContent = (type === 'warn' ? '! ' : '✓ ') + msg;
    toast.className = 'settings-toast show' + (type === 'warn' ? ' warn' : '');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove('show'), 3200);
}