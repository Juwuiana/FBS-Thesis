/**
 * static/js/nurse_base.js
 */
document.addEventListener('DOMContentLoaded', () => {
    // ---- Flash messages ("Welcome back", "Screening saved", ...) ----------
    // They sit over the top of the page, so they fade out on their own instead
    // of covering the notification bell. Errors stay a little longer. Click to
    // dismiss now; hovering pauses the timer so a message can still be read.
    const flashBox = document.querySelector('.app-flash-messages');
    if (flashBox) {
        const dismissFlash = (el) => {
            if (el.dataset.dismissing) return;
            el.dataset.dismissing = '1';
            el.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateY(-6px)';
            setTimeout(() => {
                el.remove();
                if (!flashBox.querySelector('.app-flash')) flashBox.remove();
            }, 400);
        };
        flashBox.querySelectorAll('.app-flash').forEach((el) => {
            const isError = el.classList.contains('app-flash-error') || el.classList.contains('app-flash-danger');
            let timer = setTimeout(() => dismissFlash(el), isError ? 8000 : 4000);
            el.style.cursor = 'pointer';
            el.title = 'Click to dismiss';
            el.addEventListener('click', () => { clearTimeout(timer); dismissFlash(el); });
            el.addEventListener('mouseenter', () => clearTimeout(timer));
            el.addEventListener('mouseleave', () => { timer = setTimeout(() => dismissFlash(el), 1500); });
        });
    }

    // ---- Notification bell: records a patient edited from the portal ----
    const bellWrap  = document.getElementById('nurseBellWrap');
    const bellBtn   = document.getElementById('nurseBellBtn');
    const bellPanel = document.getElementById('nurseBellPanel');
    const bellBadge = document.getElementById('nurseBellBadge');
    const bellList  = document.getElementById('nurseBellList');
    let bellLoaded = false;

    const escapeHtml = (v) => String(v ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
    
    // 1. Add all patient profile and demographic fields here:
    const FIELD_LABELS = { 
        location: 'Address / location',
        address: 'Address / location',
        civil_status: 'Civil status',
        occupation: 'Occupation',
        barangay_id: 'Barangay',
        bp_systolic: 'BP (systolic)', 
        bp_diastolic: 'BP (diastolic)', 
        heart_rate: 'Heart rate',
        respiratory_rate: 'Respiratory rate', 
        height_cm: 'Height', 
        weight_kg: 'Weight', 
        bmi: 'BMI', 
        obesity_class: 'BMI class',
        smoking_status: 'Smoking status',
        alcohol_intake: 'Alcohol intake',
        illicit_drug_use: 'Illicit drug use',
        physical_activity: 'Physical activity',
        diabetes_diagnosis: 'Diabetes diagnosis',
        past_surgical_history: 'Surgical history'
    };

    function setBadge(n) {
        if (!bellBadge) return;
        bellBadge.textContent = n > 99 ? '99+' : String(n);
        bellBadge.hidden = !n;
    }
    if (bellBadge && typeof window.__pendingPatientEditsCount === 'number') {
        setBadge(window.__pendingPatientEditsCount);
    }

    const SECTION_STYLE = 'padding:0.5rem 1.25rem; font-size:0.7rem; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; ';

    // Patients who asked for account help from the login page (forgot
    // password / lost ID / locked out). Opening one lands on the Portal
    // Access card of their file, where the nurse reissues credentials --
    // which also resolves the request. Dismiss is for duplicates.
    function renderAccountHelp(requests) {
        if (!requests.length) return '';
        return `<div class="nurse-bell-section" style="${SECTION_STYLE}color:#92400e; background:#fef3c7;">Account action required (${requests.length})</div>` +
            requests.map(r => {
                const when = r.requested_at ? new Date(r.requested_at.replace(' ', 'T') + 'Z').toLocaleString() : '';
                return `<div class="nurse-bell-item" data-patient-id="${r.patient_id}">
                    <a href="${escapeHtml(r.patient_file_url)}#portalAccessCard" style="text-decoration:none; color:inherit; display:block;">
                        <div class="nurse-bell-name">${escapeHtml(r.patient_name)}<span class="nurse-bell-code">${escapeHtml(r.patient_code)}</span></div>
                        <div class="nurse-bell-fields">${r.reason_code === 'self_deactivated'
                            ? 'Account deactivated: reactivate portal access once verified'
                            : escapeHtml(r.reason) + ': portal access needs to be reissued'}</div>
                        <div class="nurse-bell-time">${escapeHtml(when)}</div>
                    </a>
                    <button type="button" class="nurse-bell-ack nurse-bell-dismiss" data-patient-id="${r.patient_id}" title="Mark as handled without reissuing access">Dismiss</button>
                </div>`;
            }).join('');
    }

    function renderBellList(edits, requests = []) {
        if (!bellList) return;
        if (!edits.length && !requests.length) { bellList.innerHTML = '<p class="nurse-bell-empty">No pending updates.</p>'; return; }
        const helpHtml = renderAccountHelp(requests);
        const editsHeader = (helpHtml && edits.length)
            ? `<div class="nurse-bell-section" style="${SECTION_STYLE}color:#4b5563; background:#f3f4f6;">Records updated by patients (${edits.length})</div>`
            : '';
        bellList.innerHTML = helpHtml + editsHeader + edits.map(e => {
            // 2. Map through FIELD_LABELS or humanize unknown keys, avoiding the 'Vitals' default:
            const rawFields = e.fields || [];
            const mappedList = [...new Set(rawFields.map(f => FIELD_LABELS[f] || f.replace(/_/g, ' ')))];
            const fields = mappedList.length > 0 ? mappedList.join(', ') : 'Profile / Details';

            const when = e.edited_at ? new Date(e.edited_at.replace(' ', 'T') + 'Z').toLocaleString() : '';
            return `<div class="nurse-bell-item" data-visit-id="${e.visit_id}">
                <a href="${e.patient_file_url}" style="text-decoration:none; color:inherit; display:block;">
                    <div class="nurse-bell-name">${escapeHtml(e.patient_name)}<span class="nurse-bell-code">${escapeHtml(e.patient_code)}</span></div>
                    <div class="nurse-bell-fields">Updated: ${escapeHtml(fields)}</div>
                    <div class="nurse-bell-time">${escapeHtml(when)}</div>
                </a>
                <button type="button" class="nurse-bell-ack" data-visit-id="${e.visit_id}">Mark reviewed</button>
            </div>`;
        }).join('');
    }

    async function loadBell() {
        if (!bellList) return;
        try {
            const [editsRes, helpRes] = await Promise.all([
                fetch('/nurse/patient-edits'),
                // If this one fails it must not hide the edits list, so it falls back to "none".
                fetch('/nurse/account-help-requests').catch(() => null),
            ]);
            if (!editsRes.ok) throw new Error('bad status');
            const editsData = await editsRes.json();
            let helpData = { count: 0, requests: [] };
            if (helpRes && helpRes.ok) helpData = await helpRes.json().catch(() => helpData);
            setBadge((editsData.count || 0) + (helpData.count || 0));
            renderBellList(editsData.edits || [], helpData.requests || []);
            bellLoaded = true;
        } catch (e) {
            bellList.innerHTML = '<p class="nurse-bell-empty">Could not load updates.</p>';
        }
    }

    if (bellBtn && bellPanel) {
        bellBtn.addEventListener('click', () => {
            const open = bellPanel.hidden;
            bellPanel.hidden = !open;
            bellBtn.setAttribute('aria-expanded', String(open));
            if (open && !bellLoaded) loadBell();
        });
        document.addEventListener('click', (e) => {
            if (bellWrap && !bellWrap.contains(e.target)) { bellPanel.hidden = true; bellBtn.setAttribute('aria-expanded', 'false'); }
        });
        bellList && bellList.addEventListener('click', async (e) => {
            const dismiss = e.target.closest('.nurse-bell-dismiss');
            if (dismiss) {
                e.preventDefault();
                dismiss.disabled = true;
                try {
                    const res = await fetch(`/nurse/account-help-requests/${dismiss.dataset.patientId}/resolve`, { method: 'POST' });
                    if (!res.ok) throw new Error('bad status');
                    bellLoaded = false;
                    loadBell();
                } catch (err) { dismiss.disabled = false; }
                return;
            }
            const btn = e.target.closest('.nurse-bell-ack');
            if (!btn) return;
            e.preventDefault();
            const visitId = btn.dataset.visitId;
            btn.disabled = true;
            try {
                await fetch(`/nurse/patient-edits/${visitId}/acknowledge`, { method: 'POST' });
                bellLoaded = false;
                loadBell();
            } catch (err) { btn.disabled = false; }
        });
        // refresh periodically so the badge doesn't go stale on a page left open
        setInterval(() => { if (bellPanel.hidden) loadBell(); }, 60000);
    }

    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    const backToTopBtn = document.getElementById('backToTop');

    window.addEventListener('scroll', () => {
        if (window.scrollY > 300) {
            backToTopBtn.classList.add('show');
        } else {
            backToTopBtn.classList.remove('show');
        }
    });

    if (backToTopBtn) {
        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.add('active');
            overlay.classList.add('active');
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
        });
    }

    const userMenuToggle  = document.getElementById('userMenuToggle');
    const userDropdown    = document.getElementById('userDropdown');
    const userMenuCaret   = document.getElementById('userMenuCaret');
    const avatarFileInput = document.getElementById('avatarFileInput');
    const avatarUploadForm = document.getElementById('avatarUploadForm');

    function openUserMenu() {
        userDropdown.classList.add('open');
        userMenuCaret.textContent = '▼';
    }
    function closeUserMenu() {
        userDropdown.classList.remove('open');
        userMenuCaret.textContent = '▲';
    }

    if (userMenuToggle) {
        userMenuToggle.addEventListener('click', () => {
            userDropdown.classList.contains('open') ? closeUserMenu() : openUserMenu();
        });
        userMenuToggle.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); userMenuToggle.click(); }
        });
    }

    document.addEventListener('click', e => {
        if (userDropdown && userMenuToggle && !userMenuToggle.contains(e.target) && !userDropdown.contains(e.target)) {
            closeUserMenu();
        }
    });

    if (avatarFileInput) {
        avatarFileInput.addEventListener('change', () => {
            if (avatarFileInput.files.length) avatarUploadForm.submit();
        });
    }

    let touchStartX = 0;
    let touchEndX = 0;

    // Record where the finger first touches the screen
    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    // Record where the finger leaves the screen and calculate
    document.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });

    function handleSwipe() {
        if (sidebar.classList.contains('active')) {
            if (touchStartX - touchEndX > 50) {
                // Close the sidebar!
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            }
        }
    }
});