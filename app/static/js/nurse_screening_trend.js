// Screenings over time: year > month > day drill-down, three lines
// (Normal / Prediabetic / Diabetic by FBS). Click a legend item to show or
// hide a line; click a point to zoom in; click a breadcrumb to zoom out.
document.addEventListener('DOMContentLoaded', function () {
    const canvas = document.getElementById('screeningTrendChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const COLORS = { Normal: '#27ae60', Prediabetic: '#f59e0b', Diabetic: '#ef4444' };
    const LABELS = { Normal: 'Normal (<100)', Prediabetic: 'Prediabetic (100-125)', Diabetic: 'Diabetic (126+)' };
    const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const breadcrumbEl = document.getElementById('trendBreadcrumb');
    const hintEl = document.getElementById('trendHint');
    const box = document.getElementById('trendChartBox') || canvas.parentElement;

    let chart = null;
    let path = [];                 // [] = years; [{year}] = months; [{year},{month}] = days
    const hidden = new Set();      // lines the nurse switched off; survives zooming
    let requestId = 0;             // ignore stale responses if she clicks quickly

    function url(level, year, month) {
        const p = new URLSearchParams({ level });
        if (year) p.set('year', year);
        if (month) p.set('month', month);
        return `/api/analytics/screening_trend?${p.toString()}`;
    }

    function tickLabel(label, level) {
        if (level === 'month') return MONTHS[Number(label.split('-')[1])] || label;
        if (level === 'day') return String(Number(label.split('-')[2]));
        return label;
    }

    function renderBreadcrumb() {
        const crumbs = [{ text: 'All Years' }];
        if (path[0]) crumbs.push({ text: path[0].year });
        if (path[1]) crumbs.push({ text: `${MONTHS[Number(path[1].month)]} ${path[1].year}` });
        breadcrumbEl.replaceChildren();
        crumbs.forEach((c, i) => {
            if (i) {
                const sep = document.createElement('span');
                sep.className = 'crumb-sep';
                sep.textContent = '›';
                breadcrumbEl.appendChild(sep);
            }
            const btn = document.createElement('button');
            const last = i === crumbs.length - 1;
            btn.type = 'button';
            btn.className = 'crumb' + (last ? ' current' : '');
            btn.disabled = last;
            btn.textContent = c.text;
            if (!last) btn.addEventListener('click', () => goTo(path.slice(0, i)));
            breadcrumbEl.appendChild(btn);
        });
        if (hintEl) {
            hintEl.textContent = path.length < 2
                ? 'Click a point to zoom in. Click a legend item to show or hide a line.'
                : 'Most zoomed in. Click a crumb above to zoom out.';
        }
    }

    function draw(json) {
        const { level, labels, series } = json;
        if (chart) chart.destroy();
        chart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels.map(l => tickLabel(l, level)),
                datasets: Object.keys(COLORS).map(key => ({
                    label: LABELS[key],
                    data: series[key] || [],
                    borderColor: COLORS[key],
                    backgroundColor: COLORS[key],
                    tension: 0.3, borderWidth: 2,
                    pointRadius: level === 'day' ? 2 : 4, pointHoverRadius: 6,
                    hidden: hidden.has(key),
                    _key: key,
                })),
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } },
                        // default click toggles the line; remember it across zoom levels
                        onClick: (e, item, legend) => {
                            const ds = legend.chart.data.datasets[item.datasetIndex];
                            Chart.defaults.plugins.legend.onClick(e, item, legend);
                            if (legend.chart.isDatasetVisible(item.datasetIndex)) hidden.delete(ds._key);
                            else hidden.add(ds._key);
                        },
                        onHover: e => { e.native.target.style.cursor = 'pointer'; },
                        onLeave: e => { e.native.target.style.cursor = 'default'; },
                    },
                    tooltip: { callbacks: { title: items => labels[items[0].dataIndex] } },
                },
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#e2e8f0' } },
                    x: { grid: { display: false } },
                },
                onHover: (evt, els) => {
                    canvas.style.cursor = level !== 'day' && els.length ? 'pointer' : 'default';
                },
                onClick: (evt, els) => {
                    if (level === 'day' || !els.length) return;
                    const label = labels[els[0].index];
                    if (level === 'year') goTo([{ year: label }]);
                    else goTo([path[0], { year: path[0].year, month: String(Number(label.split('-')[1])) }]);
                },
            },
        });
    }

    async function goTo(newPath) {
        path = newPath;
        renderBreadcrumb();
        const level = path.length === 0 ? 'year' : path.length === 1 ? 'month' : 'day';
        const my = ++requestId;
        if (box) box.style.opacity = '0.5';
        try {
            const res = await fetch(url(level, path[0] && path[0].year, path[1] && path[1].month));
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const json = await res.json();
            if (my === requestId) draw(json);
        } catch (err) {
            console.error('Could not load screening trend', err);
        } finally {
            if (my === requestId && box) box.style.opacity = '1';
        }
    }

    goTo([]);
});