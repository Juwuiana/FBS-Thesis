// Health Results page: tabs, charts, worklist filters, barangay CSV.
document.addEventListener('DOMContentLoaded', async () => {
    const PALETTE = {
        green: '#27ae60', amber: '#f59e0b', red: '#ef4444',
        dark: '#1a2e1a', accent: '#3a7d3a',
        textMuted: '#6b7c6b', grid: '#e0e8e0',
    };
    const NEUTRAL = ['#1a2e1a', '#3a7d3a', '#8fbf8f', '#c9dfc9', '#e0e8e0'];

    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
        Chart.defaults.color = PALETTE.textMuted;
    }
    const esc = (v) => String(v ?? '').replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));

    // ---- Tabs (work even if the analytics fetch fails) ----
    const tabs = Array.from(document.querySelectorAll('.hr-tab'));
    const panels = Array.from(document.querySelectorAll('.hr-panel'));
    function showTab(name) {
        if (!tabs.some(t => t.dataset.tab === name)) name = 'overview';
        tabs.forEach(t => t.setAttribute('aria-selected', String(t.dataset.tab === name)));
        panels.forEach(p => p.classList.toggle('is-active', p.id === 'panel-' + name));
        window.dispatchEvent(new Event('resize'));
    }
    tabs.forEach(t => t.addEventListener('click', () => {
        showTab(t.dataset.tab);
        history.replaceState(null, '', '#' + t.dataset.tab);
    }));
    document.querySelectorAll('[data-tab-target]').forEach(b => b.addEventListener('click', () => {
        showTab(b.dataset.tabTarget);
        history.replaceState(null, '', '#' + b.dataset.tabTarget);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }));
    showTab(location.hash.slice(1) || 'overview');

    // ---- Follow-up worklist filters (rows are server-rendered) ----
    const wlRows = Array.from(document.querySelectorAll('#worklistBody tr[data-risk]'));
    const wl = {
        risk: document.getElementById('worklistRisk'),
        status: document.getElementById('worklistStatus'),
        brgy: document.getElementById('worklistBarangay'),
        search: document.getElementById('worklistSearch'),
        count: document.getElementById('worklistCount'),
        empty: document.getElementById('worklistEmpty'),
    };
    function applyWorklistFilters() {
        const risk = wl.risk ? wl.risk.value : '';
        const status = wl.status ? wl.status.value : '';
        const brgy = wl.brgy ? wl.brgy.value : '';
        const q = wl.search ? wl.search.value.trim().toLowerCase() : '';
        let shown = 0;
        wlRows.forEach(tr => {
            const ok = (!risk || tr.dataset.risk === risk)
                && (!status || tr.dataset.status === status)
                && (!brgy || tr.dataset.barangay === brgy)
                && (!q || tr.dataset.search.includes(q));
            tr.hidden = !ok;
            if (ok) shown++;
        });
        if (wl.count) wl.count.textContent = shown;
        if (wl.empty) wl.empty.hidden = shown > 0;
    }
    [wl.risk, wl.status, wl.brgy].forEach(el => el && el.addEventListener('change', applyWorklistFilters));
    if (wl.search) wl.search.addEventListener('input', applyWorklistFilters);

    // ---- Barangay table -> CSV ----
    const csvBtn = document.getElementById('barangayCsvBtn');
    if (csvBtn) csvBtn.addEventListener('click', () => {
        const table = document.getElementById('barangayTable');
        const lines = Array.from(table.querySelectorAll('tr')).map(tr =>
            Array.from(tr.children).map(c => '"' + c.textContent.trim().replace(/"/g, '""') + '"').join(','));
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' }));
        a.download = 'barangay_summary_' + new Date().toISOString().slice(0, 10) + '.csv';
        a.click();
        URL.revokeObjectURL(a.href);
    });

    // ---- Analytics data ----
    if (typeof Chart === 'undefined') return;
    let data;
    try {
        const res = await fetch('/api/analytics/health_results');
        if (!res.ok) return;
        data = await res.json();
    } catch (e) { return; }

    const yAxis = (extra = {}) => ({ beginAtZero: true, grid: { color: PALETTE.grid }, ticks: { precision: 0 }, ...extra });
    const legendBottom = { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, padding: 14, font: { size: 11 } } };

    // Screenings per month: a line, because it is a trend
    const trendCanvas = document.getElementById('monthlyTrendChart');
    if (trendCanvas && data.monthly_trend) {
        const months = Object.keys(data.monthly_trend);
        const sumOf = (m) => Object.values(data.monthly_trend[m]).reduce((a, b) => a + b, 0);
        new Chart(trendCanvas, {
            type: 'line',
            data: {
                labels: months,
                datasets: [
                    { label: 'All screenings', data: months.map(sumOf), borderColor: PALETTE.dark, backgroundColor: PALETTE.dark, tension: 0.3, borderWidth: 2, pointRadius: 3 },
                    { label: 'High risk', data: months.map(m => data.monthly_trend[m].High || 0), borderColor: PALETTE.red, backgroundColor: PALETTE.red, tension: 0.3, borderWidth: 2, pointRadius: 3 },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: legendBottom },
                scales: { x: { grid: { display: false } }, y: yAxis() },
            },
        });
    }

    // Patient profile: donut for shares, bars only for ordered classes, line for age
    const DONUTS = new Set(['fbs', 'sex', 'hypertension', 'waist', 'family', 'smoking']);
    const NOTES = {
        fbs: 'Latest fasting blood sugar per patient, grouped by clinical range.',
        age: 'Share of patients at moderate or high risk in each age group.',
        sex: 'Patients screened, by sex.',
        bmi: 'Patients by BMI class (Asian cut-offs).',
        bp: 'Latest blood pressure reading, grouped by stage.',
        hypertension: 'Patients with a recorded history of hypertension.',
        waist: 'Waist above 90 cm (men) or 80 cm (women) counts as at risk.',
        smoking: 'Smoking status recorded at the latest visit.',
        family: 'Patients with a family history of diabetes.',
    };
    function sliceColors(key, labels) {
        if (key === 'fbs') return labels.map(l => /^normal/i.test(l) ? PALETTE.green : /^pre/i.test(l) ? PALETTE.amber : PALETTE.red);
        if (key === 'waist') return labels.map(l => /risk/i.test(l) ? PALETTE.red : NEUTRAL[3]);
        return labels.map((_, i) => NEUTRAL[i % NEUTRAL.length]);
    }

    const profileCanvas = document.getElementById('dynamicAttributeChart');
    const profileNote = document.getElementById('profileNote');
    let profileChart = null;
    function renderProfile(key) {
        if (!profileCanvas) return;
        if (profileChart) profileChart.destroy();
        if (profileNote) profileNote.textContent = NOTES[key] || '';

        if (key === 'age') {
            const groups = data.risk_by_age || {};
            const labels = Object.keys(groups);
            const n = labels.map(a => (groups[a].Low || 0) + (groups[a].Moderate || 0) + (groups[a].High || 0));
            const rate = (fn) => labels.map((a, i) => n[i] ? Math.round(fn(groups[a]) / n[i] * 100) : null);
            profileChart = new Chart(profileCanvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        { label: 'Moderate or high', data: rate(g => (g.Moderate || 0) + (g.High || 0)), borderColor: PALETTE.amber, backgroundColor: PALETTE.amber, tension: 0.3, borderWidth: 2, pointRadius: 3 },
                        { label: 'High', data: rate(g => g.High || 0), borderColor: PALETTE.red, backgroundColor: PALETTE.red, tension: 0.3, borderWidth: 2, pointRadius: 3 },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: legendBottom,
                        tooltip: { callbacks: {
                            label: (c) => ` ${c.dataset.label}: ${c.raw ?? 0}%`,
                            afterBody: (items) => `n = ${n[items[0].dataIndex]}`,
                        } },
                    },
                    scales: { x: { grid: { display: false } }, y: yAxis({ max: 100, ticks: { callback: v => v + '%' } }) },
                },
            });
            return;
        }

        const dist = data[key] || {};
        const labels = Object.keys(dist);
        const values = Object.values(dist);
        const total = values.reduce((a, b) => a + b, 0);
        if (!total && profileNote) profileNote.textContent = 'No data recorded yet.';
        const tip = { callbacks: { label: (c) => ` ${c.label}: ${c.raw.toLocaleString()} (${total ? Math.round(c.raw / total * 100) : 0}%)` } };

        if (DONUTS.has(key)) {
            profileChart = new Chart(profileCanvas, {
                type: 'doughnut',
                data: { labels, datasets: [{ data: values, backgroundColor: sliceColors(key, labels), borderColor: '#fff', borderWidth: 2 }] },
                options: { responsive: true, maintainAspectRatio: false, cutout: '62%', plugins: { legend: { ...legendBottom, position: 'right' }, tooltip: tip } },
            });
        } else {
            profileChart = new Chart(profileCanvas, {
                type: 'bar',
                data: { labels, datasets: [{ data: values, backgroundColor: PALETTE.accent, borderRadius: 4, maxBarThickness: 26 }] },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: tip },
                    scales: { x: yAxis(), y: { grid: { display: false } } },
                },
            });
        }
    }
    const selector = document.getElementById('attributeSelector');
    if (selector) selector.addEventListener('change', e => renderProfile(e.target.value));
    renderProfile('fbs');

    // At-risk rate by sex: CSS meters, not another chart
    const sexBox = document.getElementById('sexMeters');
    if (sexBox) {
        const rows = Object.entries(data.risk_by_sex || {}).map(([sex, c]) => {
            const n = (c.Low || 0) + (c.Moderate || 0) + (c.High || 0);
            const pct = n ? Math.round(((c.Moderate || 0) + (c.High || 0)) / n * 100) : 0;
            return `<div class="hr-meter-row">
                <span class="hr-meter-label">${esc(sex)} <small class="hr-muted">(n = ${n})</small></span>
                <div class="hr-meter neutral"><i style="width:${pct}%"></i></div>
                <span class="hr-meter-val">${pct}%</span></div>`;
        });
        sexBox.innerHTML = rows.join('') || '<p class="hr-empty">No data yet.</p>';
    }
});