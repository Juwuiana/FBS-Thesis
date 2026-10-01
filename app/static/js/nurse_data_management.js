document.addEventListener('DOMContentLoaded', () => {
    // --- Filters auto-apply on change, no "Apply Filter" click needed. ---
    // Selecting a barangay/risk/entries value or picking a date submits
    // the filter form immediately. Free-text search is debounced instead
    // of firing on every keystroke, since that would spam requests while
    // still typing a name. "Apply Filter" is left in place too -- it's a
    // harmless no-op once everything already auto-submits, and it's the
    // only way to apply a search with JS disabled.
    const filterForm = document.getElementById('filterForm');
    if (filterForm) {
        ['filterEntries', 'filterBarangay', 'filterRisk', 'filterDate', 'filterStatus'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', () => filterForm.submit());
        });

        const searchInput = document.getElementById('filterSearch');
        if (searchInput) {
            let debounceTimer;
            searchInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => filterForm.submit(), 500);
            });
        }
    }

    const form = document.getElementById('csvImportForm');
    if (!form) return;

    const fileInput = document.getElementById('csvImportFile');
    const submitBtn = form.querySelector('button[type="submit"]');
    let resultDiv = document.getElementById('csvImportResult');
    if (!resultDiv) {
        resultDiv = document.createElement('div');
        resultDiv.id = 'csvImportResult';
        resultDiv.style.cssText = 'margin-top:0.75rem; font-size:0.8rem;';
        form.appendChild(resultDiv);
    }

    // Progress bar: use the markup from the template if present, otherwise build it here
    // so the import never depends on the HTML file having been updated too.
    let progress = document.getElementById('csvProgress');
    if (!progress) {
        progress = document.createElement('div');
        progress.id = 'csvProgress';
        progress.hidden = true;
        progress.style.marginTop = '0.75rem';
        progress.innerHTML =
            '<div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-bottom:0.3rem;">' +
            '<span id="csvProgressLabel">Uploading…</span><span id="csvProgressPct">0%</span></div>' +
            '<div id="csvProgressTrack" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" ' +
            'style="height:8px; border-radius:999px; background:#e0e8e0; overflow:hidden;">' +
            '<div id="csvProgressBar" style="height:100%; width:0; background:#3a7d3a; transition:width .25s ease;"></div></div>';
        form.insertBefore(progress, resultDiv);
    }
    const bar = document.getElementById('csvProgressBar');
    const track = document.getElementById('csvProgressTrack');
    const pctLabel = document.getElementById('csvProgressPct');
    const stageLabel = document.getElementById('csvProgressLabel');

    function setProgress(pct, label) {
        pct = Math.max(0, Math.min(100, Math.round(pct)));
        bar.style.width = pct + '%';
        track.setAttribute('aria-valuenow', pct);
        pctLabel.textContent = pct + '%';
        if (label) stageLabel.textContent = label;
    }

    function showResult({ color, message, errors = [], keepOpen = false }) {
        resultDiv.innerHTML = '';
        resultDiv.style.color = color;
        const msg = document.createElement('div');
        msg.textContent = message;
        resultDiv.appendChild(msg);

        if (errors.length) {
            const box = document.createElement('div');
            box.style.cssText = 'margin-top:0.5rem; max-height:12rem; overflow-y:auto; padding:0.5rem 0.75rem; ' +
                'border:1px solid currentColor; border-radius:6px; background:rgba(0,0,0,0.03);';
            const ul = document.createElement('ul');
            ul.style.cssText = 'margin:0; padding-left:1.1rem;';
            errors.forEach(text => {
                const li = document.createElement('li');
                li.textContent = text;   // textContent: row values from the CSV can't inject HTML
                ul.appendChild(li);
            });
            box.appendChild(ul);
            resultDiv.appendChild(box);
        }

        if (keepOpen) {
            const row = document.createElement('div');
            row.style.cssText = 'margin-top:0.6rem; display:flex; gap:0.5rem;';
            const refresh = document.createElement('button');
            refresh.type = 'button';
            refresh.className = 'btn btn-primary';
            refresh.textContent = 'Done — refresh list';
            refresh.addEventListener('click', () => window.location.reload());
            const dismiss = document.createElement('button');
            dismiss.type = 'button';
            dismiss.className = 'btn btn-secondary';
            dismiss.textContent = 'Dismiss';
            dismiss.addEventListener('click', () => { resultDiv.innerHTML = ''; progress.hidden = true; });
            row.append(refresh, dismiss);
            resultDiv.appendChild(row);
        }
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!fileInput.files.length) return;
        try {
        const file = fileInput.files[0];

        // Row count drives the time estimate for the server-processing phase.
        let rows = 0;
        try { rows = Math.max(0, (await file.text()).split(/\r?\n/).filter(l => l.trim()).length - 1); } catch (_) {}
        const estMs = Math.max(2000, rows * 60);   // rough per-row cost (DB writes + model prediction)

        const formData = new FormData();
        formData.append('csv_import', file);

        resultDiv.innerHTML = '';
        progress.hidden = false;
        submitBtn.disabled = true;
        setProgress(0, 'Uploading…');

        // XHR instead of fetch: fetch cannot report upload progress.
        // Bar plan: 0-30% = upload (real), 30-95% = server processing (estimated,
        // eases toward 95% and never claims to be done early), 100% = response received.
        let creepTimer = null;
        const startCreep = () => {
            const t0 = Date.now();
            setProgress(30, rows ? `Processing ${rows.toLocaleString()} row${rows === 1 ? '' : 's'}…` : 'Processing…');
            creepTimer = setInterval(() => {
                const frac = 1 - Math.exp(-(Date.now() - t0) / estMs);
                setProgress(30 + 65 * frac);
            }, 200);
        };
        const stopCreep = () => { if (creepTimer) clearInterval(creepTimer); creepTimer = null; };

        const xhr = new XMLHttpRequest();
        xhr.open('POST', window.__csvImportUrl);
        xhr.upload.onprogress = (ev) => {
            if (ev.lengthComputable) setProgress((ev.loaded / ev.total) * 30, 'Uploading…');
        };
        xhr.upload.onload = startCreep;

        const fail = (message) => {
            stopCreep();
            submitBtn.disabled = false;
            progress.hidden = true;
            showResult({ color: 'var(--danger)', message });
        };
        xhr.onerror = () => fail('Network error during import.');
        xhr.ontimeout = () => fail('The import timed out.');
        xhr.onload = () => {
            stopCreep();
            submitBtn.disabled = false;
            let data = {};
            try { data = JSON.parse(xhr.responseText); } catch (_) {}

            if (xhr.status < 200 || xhr.status >= 300) {
                return fail(data.error || (xhr.status === 429
                    ? 'Too many imports in a short time. Wait a minute and try again.'
                    : 'Import failed.'));
            }

            setProgress(100, 'Done');
            const errors = data.errors || [];
            const hasIssues = errors.length > 0 || (data.skipped || 0) > 0;
            showResult({
                color: hasIssues ? '#b45309' : 'var(--green-accent)',
                message: data.message || (errors.length ? 'Import finished with problems.' : 'Import complete.'),
                errors,
                keepOpen: hasIssues,   // problems stay on screen until the user dismisses them
            });
            // Clean import: refresh automatically. With errors, never auto-reload --
            // that was wiping the error list 2.5s after it appeared.
            if (!hasIssues && data.created > 0) setTimeout(() => window.location.reload(), 2500);
        };
        xhr.send(formData);
        } catch (err) {
            console.error('CSV import failed before sending', err);
            submitBtn.disabled = false;
            progress.hidden = true;
            showResult({ color: 'var(--danger)', message: 'Import could not start: ' + err.message });
        }
    });
});