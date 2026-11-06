document.addEventListener('DOMContentLoaded', function () {
    var cfg = window.__adminDash;
    if (!cfg || typeof Chart === 'undefined') return;

    var green = '#27ae60', yellow = '#f59e0b', red = '#ef4444';
    Chart.defaults.color = '#475569';

    function escapeHtml(v) {
        return String(v == null ? '' : v).replace(/[&<>'"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c];
        });
    }

    // Risk donut
    var donut = document.getElementById('adRiskDonut');
    if (donut) {
        new Chart(donut, {
            type: 'doughnut',
            data: {
                labels: ['Low Risk', 'Moderate Risk', 'High Risk'],
                datasets: [{ data: cfg.riskData, backgroundColor: [green, yellow, red], borderWidth: 2, borderColor: '#ffffff' }]
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: '70%',
                plugins: { legend: { position: 'right', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } } } }
        });
    }

    // Screening volume: year -> month -> week drill-down
    var line = document.getElementById('adVolumeLine');
    if (line) {
        var MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        var crumbsEl = document.getElementById('adVolumeCrumbs');
        var hintEl = document.getElementById('adVolumeHint');
        var box = line.parentElement;
        var chart = null;
        var path = [];

        function url(level, year, month) {
            var p = new URLSearchParams({ level: level });
            if (year) p.set('year', year);
            if (month) p.set('month', month);
            return cfg.volumeUrl + '?' + p.toString();
        }
        function shownLabels(labels, level) {
            if (level !== 'month') return labels;
            return labels.map(function (l) { return MONTHS[Number(l.split('-')[1])] || l; });
        }
        function renderCrumbs() {
            var crumbs = [{ label: 'All Years' }].concat(path.map(function (s) { return { label: s.label }; }));
            crumbsEl.innerHTML = crumbs.map(function (c, i) {
                var last = i === crumbs.length - 1;
                var btn = '<button type="button" class="ad-crumb' + (last ? ' current' : '') + '" data-i="' + i + '"' + (last ? ' disabled' : '') + '>' + escapeHtml(c.label) + '</button>';
                return i === 0 ? btn : '<span class="ad-crumb-sep">&rsaquo;</span>' + btn;
            }).join('');
            crumbsEl.querySelectorAll('button.ad-crumb:not(.current)').forEach(function (b) {
                b.addEventListener('click', function () { goTo(path.slice(0, Number(b.dataset.i))); });
            });
            if (hintEl) hintEl.textContent = path.length < 2 ? 'Click a point or a label below the chart to zoom in.' : 'Most zoomed in. Click a label above to zoom back out.';
        }
        var cur = { labels: [], level: 'year' };
        // Which data index is under the pointer? Anywhere in the plot (nearest column) or on the x-axis labels below it.
        function pickIndex(evt) {
            if (!chart || !chart.chartArea) return -1;
            var r = line.getBoundingClientRect(), x = evt.clientX - r.left, y = evt.clientY - r.top, a = chart.chartArea;
            if (x < a.left - 4 || x > a.right + 4 || y < a.top || y > r.height) return -1;
            var best = -1, dist = Infinity;
            for (var i = 0; i < cur.labels.length; i++) {
                var d = Math.abs(chart.scales.x.getPixelForValue(i) - x);
                if (d < dist) { dist = d; best = i; }
            }
            return best;
        }
        function zoomInto(i) {
            var label = cur.labels[i];
            if (cur.level === 'year') {
                goTo([{ level: 'year', value: label, label: label }]);
            } else if (cur.level === 'month') {
                var parts = label.split('-');
                goTo(path.concat([{ level: 'month', value: parts[1], year: parts[0], label: MONTHS[Number(parts[1])] + ' ' + parts[0] }]));
            }
        }
        line.addEventListener('mousemove', function (e) { line.style.cursor = (cur.level !== 'week' && pickIndex(e) >= 0) ? 'pointer' : 'default'; });
        line.addEventListener('click', function (e) { var i = pickIndex(e); if (i >= 0 && cur.level !== 'week') zoomInto(i); });
        function draw(labels, values, level) {
            if (chart) chart.destroy();
            cur = { labels: labels, level: level };
            chart = new Chart(line, {
                type: 'line',
                data: { labels: shownLabels(labels, level),
                    datasets: [{ label: 'Screenings', data: values, borderColor: green, backgroundColor: 'rgba(39,174,96,0.05)',
                        tension: 0.3, fill: true, borderWidth: 2, pointRadius: 4, pointHoverRadius: 6 }] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#e2e8f0' } },
                              x: { grid: { display: false }, ticks: { font: { weight: '600' }, color: level === 'week' ? '#475569' : '#3a7d3a' } } }
                }
            });
        }
        function goTo(newPath) {
            path = newPath;
            renderCrumbs();
            if (!path.length) { draw(Object.keys(cfg.timeline), Object.values(cfg.timeline), 'year'); return; }
            var last = path[path.length - 1];
            var level = last.level === 'year' ? 'month' : 'week';
            var year = last.level === 'year' ? last.value : last.year;
            var month = last.level === 'month' ? last.value : undefined;
            box.style.opacity = '0.5';
            fetch(url(level, year, month), { credentials: 'same-origin' })
                .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
                .then(function (j) { draw(j.labels || [], j.values || [], j.level || level); })
                .catch(function (err) { console.error('Could not load screening volume', err); })
                .then(function () { box.style.opacity = '1'; });
        }
        renderCrumbs();
        draw(Object.keys(cfg.timeline), Object.values(cfg.timeline), 'year');
    }

    // Top barangays (patients)
    var bar = document.getElementById('adBarangayBar');
    if (bar) {
        new Chart(bar, {
            type: 'bar',
            data: { labels: Object.keys(cfg.topBarangays),
                datasets: [{ label: 'Patients', data: Object.values(cfg.topBarangays), backgroundColor: green, borderRadius: 4 }] },
            options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#e2e8f0' } }, y: { grid: { display: false } } } }
        });
    }
});