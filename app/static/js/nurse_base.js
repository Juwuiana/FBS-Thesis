/**
 * static/js/nurse_base.js
 */
document.addEventListener('DOMContentLoaded', () => {
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

    function renderBellList(edits) {
        if (!bellList) return;
        if (!edits.length) { bellList.innerHTML = '<p class="nurse-bell-empty">No pending updates.</p>'; return; }
        bellList.innerHTML = edits.map(e => {
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
            const res = await fetch('/nurse/patient-edits');
            if (!res.ok) throw new Error('bad status');
            const data = await res.json();
            setBadge(data.count || 0);
            renderBellList(data.edits || []);
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