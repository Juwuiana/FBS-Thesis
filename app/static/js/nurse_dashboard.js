document.addEventListener('DOMContentLoaded', async function () {
    // ─── Colours ────────────────────────────────────────────────────────────────
    const green        = '#27ae60';
    const yellow       = '#f59e0b';
    const red          = '#ef4444';
    const mutedText    = '#475569';

    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = "'DM Sans', sans-serif";
        Chart.defaults.color       = mutedText;
    }

    const baseOpts = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'bottom',
                labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } }
            }
        }
    };

    const barangaySelect = document.getElementById('barangayFilterSelect');
    const barangayPatientList = document.getElementById('barangayPatientList');

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>'"]/g, character => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        }[character]));
    }

    // FBS value coloured by clinical range (same cut-offs as the legend)
    function fbsCell(value) {
        const n = Number(value);
        if (value === null || value === undefined || value === '' || Number.isNaN(n)) return '—';
        const cls = n >= 126 ? 'fbs-diabetic' : n >= 100 ? 'fbs-pre' : 'fbs-normal';
        const tip = n >= 126 ? 'Diabetic range (126 or higher)' : n >= 100 ? 'Pre-diabetic range (100 to 125)' : 'Normal range (below 100)';
        return `<span class="fbs-val ${cls} has-tip" tabindex="0" data-tip="${tip}">${escapeHtml(value)}</span>`;
    }

    function renderBarangayPatients(patients) {
        if (!patients.length) {
            barangayPatientList.innerHTML = '<p style="font-size:0.8rem; color:var(--text-muted);">No patients found in this barangay yet.</p>';
            return;
        }

        const urlTemplate = window.__dashboardData.patientFileUrlTemplate;
        const rows = patients.map(patient => {
            const patientUrl = urlTemplate.replace('__PATIENT_ID__', encodeURIComponent(patient.patient_code));
            const riskClass = patient.risk === 'High' ? 'badge-danger' : patient.risk === 'Moderate' ? 'badge-warning' : patient.risk === 'Low' ? 'badge-success' : '';
            const risk = riskClass
                ? `<span class="risk-badge ${riskClass}">${escapeHtml(patient.risk)}</span>`
                : `<span style="color:var(--text-muted);">${escapeHtml(patient.risk || 'Pending')}</span>`;
            return `<tr>
                <td><a class="patient-name-link" href="${patientUrl}">${escapeHtml(patient.last_name)}, ${escapeHtml(patient.first_name)}</a></td>
                <td class="col-hide-sm">${escapeHtml(patient.age)} / ${escapeHtml(patient.sex)}</td>
                <td class="col-hide-sm">${escapeHtml(patient.date || '—')}</td>
                <td>${fbsCell(patient.fbs)}</td>
                <td>${risk}</td>
            </tr>`;
        }).join('');

        barangayPatientList.innerHTML = `<table class="data-table dash-table">
                <thead><tr><th>Name</th><th class="col-hide-sm">Age / Sex</th><th class="col-hide-sm">Date</th><th>FBS</th><th>Risk</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>`;
    }

    if (barangaySelect && barangayPatientList) {
        barangaySelect.addEventListener('change', async function () {
            const barangay = this.value;
            if (!barangay) {
                barangayPatientList.innerHTML = '<p style="font-size:0.8rem; color:var(--text-muted);">Select a barangay to view its patients.</p>';
                return;
            }
            barangayPatientList.innerHTML = '<p style="font-size:0.8rem; color:var(--text-muted);">Loading patients…</p>';
            try {
                const response = await fetch(`/nurse_dashboard/barangay-patients?barangay=${encodeURIComponent(barangay)}`);
                if (!response.ok) throw new Error('Unable to load patients');
                const data = await response.json();
                renderBarangayPatients(data.patients || []);
            } catch (error) {
                barangayPatientList.innerHTML = '<p style="font-size:0.8rem; color:var(--text-muted);">Unable to load patients right now.</p>';
            }
        });
    }

    const toggleDataHubBtn = document.getElementById('toggleDataHubBtn');
    const dataHubWrapper   = document.getElementById('dataHubWrapper');
    const hubToggleLabel   = document.getElementById('hubToggleLabel');
    const hubToggleIcon    = document.getElementById('hubToggleIcon');

    if (toggleDataHubBtn && dataHubWrapper) {
        toggleDataHubBtn.addEventListener('click', function () {
            const isOpen = !dataHubWrapper.classList.contains('collapsed');
            dataHubWrapper.classList.toggle('collapsed', isOpen);
            toggleDataHubBtn.classList.toggle('collapsed', isOpen);
            if (hubToggleLabel) hubToggleLabel.textContent = isOpen ? 'Show Import / Export Tools' : 'Hide Import / Export Tools';
            if (hubToggleIcon) hubToggleIcon.textContent  = isOpen ? '▼' : '▲';
        });
    }

    const toggleSchemaBtn        = document.getElementById('toggleSchemaBtn');
    const schemaAccordionContent = document.getElementById('schemaAccordionContent');

    if (toggleSchemaBtn && schemaAccordionContent) {
        toggleSchemaBtn.addEventListener('click', function () {
            const isOpen = schemaAccordionContent.classList.contains('open');
            schemaAccordionContent.classList.toggle('open', !isOpen);
            toggleSchemaBtn.classList.toggle('active', !isOpen);
            const label = toggleSchemaBtn.querySelector('span:first-child');
            if (label) label.textContent = isOpen ? 'View Required Schema Instructions' : 'Hide Schema Instructions';
        });
    }

    if (typeof Chart === 'undefined') return;

    if (window.__dashboardData) {
        const { riskData, timeline, topBarangays, actualPredicted } = window.__dashboardData;

        const ctxDonut = document.getElementById('riskDonutChart');
        if (ctxDonut) {
            new Chart(ctxDonut, {
                type: 'doughnut',
                data: {
                    labels: ['Low Risk', 'Moderate Risk', 'High Risk'],
                    datasets: [{ data: riskData, backgroundColor: [green, yellow, red], borderWidth: 2, borderColor: '#ffffff' }]
                },
                options: { responsive: true, maintainAspectRatio: false, cutout: '70%',
                    plugins: { legend: { position: 'right', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } } } }
            });
        }

        // ---------------------------------------------------------------
        // Screening Volume Timeline: year -> month -> week drill-down.
        // `timeline` (from the server) is the year-level data for the
        // initial paint; drilling in fetches the next level from
        // /nurse_dashboard/screening-volume instead of reloading the page.
        // ---------------------------------------------------------------
        const ctxLine = document.getElementById('screeningsLineChart');
        if (ctxLine) {
            const MONTH_ABBR = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            const breadcrumbEl = document.getElementById('volumeBreadcrumb');
            const hintEl = document.getElementById('volumeHint');
            const chartBox = ctxLine.closest('.chart-container');
            let volumeChart = null;
            let path = []; // [] = year level; [{level:'year',...}] = viewing one year's months; + month step = viewing one month's weeks

            function volumeUrl(level, year, month) {
                const p = new URLSearchParams({ level });
                if (year) p.set('year', year);
                if (month) p.set('month', month);
                return `/nurse_dashboard/screening-volume?${p.toString()}`;
            }

            function displayLabels(labels, level) {
                if (level !== 'month') return labels;
                return labels.map(l => MONTH_ABBR[Number(l.split('-')[1])] || l);
            }

            function renderBreadcrumb() {
                const crumbs = [{ label: 'All Years' }, ...path.map(s => ({ label: s.label }))];
                breadcrumbEl.innerHTML = crumbs.map((c, i) => {
                    const isLast = i === crumbs.length - 1;
                    const text = `<button type="button" class="crumb${isLast ? ' current' : ''}" data-i="${i}" ${isLast ? 'disabled' : ''}>${escapeHtml(c.label)}</button>`;
                    return i === 0 ? text : `<span class="crumb-sep">›</span>${text}`;
                }).join('');
                breadcrumbEl.querySelectorAll('button.crumb:not(.current)').forEach(btn => {
                    btn.addEventListener('click', () => goTo(path.slice(0, Number(btn.dataset.i))));
                });
                if (hintEl) hintEl.textContent = path.length < 2 ? 'Click a point to zoom in.' : 'Most zoomed in — click a crumb above to zoom back out.';
            }

            function drawChart(labels, values, level) {
                if (volumeChart) volumeChart.destroy();
                volumeChart = new Chart(ctxLine, {
                    type: 'line',
                    data: {
                        labels: displayLabels(labels, level),
                        datasets: [{
                            label: 'Screenings', data: values,
                            borderColor: green, backgroundColor: 'rgba(39,174,96,0.05)',
                            tension: 0.3, fill: true, borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
                        }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#e2e8f0' } },
                            x: { grid: { display: false } }
                        },
                        onHover: (evt, elements) => {
                            ctxLine.style.cursor = (level !== 'week' && elements.length) ? 'pointer' : 'default';
                        },
                        onClick: (evt, elements) => {
                            if (level === 'week' || !elements.length) return;
                            const label = labels[elements[0].index];
                            if (level === 'year') {
                                goTo([{ level: 'year', value: label, label }]);
                            } else {
                                const [y, m] = label.split('-');
                                goTo([...path, { level: 'month', value: m, year: y, label: `${MONTH_ABBR[Number(m)]} ${y}` }]);
                            }
                        },
                    },
                });
            }

            async function goTo(newPath) {
                path = newPath;
                renderBreadcrumb();
                if (!path.length) {
                    drawChart(Object.keys(timeline), Object.values(timeline), 'year');
                    return;
                }
                const last = path[path.length - 1];
                const level = last.level === 'year' ? 'month' : 'week';
                const year = last.level === 'year' ? last.value : last.year;
                const month = last.level === 'month' ? last.value : undefined;
                if (chartBox) chartBox.style.opacity = '0.5';
                try {
                    const res = await fetch(volumeUrl(level, year, month));
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    const json = await res.json();
                    drawChart(json.labels || [], json.values || [], json.level || level);
                } catch (err) {
                    console.error('Could not load screening volume breakdown', err);
                } finally {
                    if (chartBox) chartBox.style.opacity = '1';
                }
            }

            renderBreadcrumb();
            drawChart(Object.keys(timeline), Object.values(timeline), 'year');
        }

        // Actual (solid) vs model-predicted (dashed), per month
        const ctxAvp = document.getElementById('avpLineChart');
        if (ctxAvp && actualPredicted && actualPredicted.monthly && actualPredicted.monthly.length) {
            const months = actualPredicted.monthly;
            const metrics = {
                at_risk: { label: 'at risk', color: yellow, actual: 'actual_at_risk', predicted: 'predicted_at_risk' },
                high:    { label: 'high risk', color: red,  actual: 'actual_high',    predicted: 'predicted_high' },
            };
            const avpChart = new Chart(ctxAvp, {
                type: 'line',
                data: { labels: months.map(m => m.month), datasets: [] },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } } },
                    scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#e2e8f0' } }, x: { grid: { display: false } } }
                }
            });
            function drawAvp(key) {
                const m = metrics[key] || metrics.at_risk;
                avpChart.data.datasets = [
                    { label: 'Actual ' + m.label, data: months.map(r => r[m.actual]), borderColor: m.color, backgroundColor: m.color, tension: 0.3, borderWidth: 2, pointRadius: 3 },
                    { label: 'Predicted ' + m.label, data: months.map(r => r[m.predicted]), borderColor: m.color, backgroundColor: '#ffffff', borderDash: [6, 4], tension: 0.3, borderWidth: 2, pointRadius: 4 },
                ];
                avpChart.update();
            }
            drawAvp('at_risk');
            const avpSelect = document.getElementById('avpMetric');
            if (avpSelect) avpSelect.addEventListener('change', e => drawAvp(e.target.value));
        }

        const ctxBar = document.getElementById('barangayBarChart');
        if (ctxBar) {
            new Chart(ctxBar, {
                type: 'bar',
                data: {
                    labels: Object.keys(topBarangays),
                    datasets: [{ label: 'Screenings', data: Object.values(topBarangays), backgroundColor: green, borderRadius: 4 }]
                },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true, grid: { color: '#e2e8f0' } }, y: { grid: { display: false } } }
                }
            });
        }
    }

    const dynamicAttrCanvas = document.getElementById('dynamicAttributeChart');
    if (dynamicAttrCanvas) {
        const res = await fetch('/api/analytics/health_results');
        const data = await res.json();

        const ATTRIBUTE_LABELS = {
            fbs: 'Fasting Blood Sugar Levels', status: 'Predicted Diabetes Risk Status',
            age: 'Age Distribution', sex: 'Sex Distribution', bmi: 'BMI Classification',
            bp: 'Blood Pressure Segments', hypertension: 'Hypertension History',
            waist: 'Waist Circumference', smoking: 'Smoking Status', family: 'Family History of Diabetes',
        };

        let attributeChartInstance = null;
        function renderAttrChart(key) {
            if (attributeChartInstance) attributeChartInstance.destroy();
            const dist = data[key] || {};
            const labels = Object.keys(dist);
            const values = Object.values(dist);

            attributeChartInstance = new Chart(dynamicAttrCanvas, {
                type: 'bar',
                data: { labels, datasets: [{ label: ATTRIBUTE_LABELS[key], data: values, backgroundColor: green, borderRadius: 4 }] },
                options: { ...baseOpts, plugins: { legend: { display: false } },
                    scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: '#e2e8f0' } } } }
            });
        }

        renderAttrChart('fbs');
        const selector = document.getElementById('attributeSelector');
        if (selector) selector.addEventListener('change', e => renderAttrChart(e.target.value));

        const ctxFullBarangay = document.getElementById('fullBarangayBarChart');
        if (ctxFullBarangay) {
            const barangayLabels = Object.keys(data.barangay_matrix);
            new Chart(ctxFullBarangay, {
                type: 'bar',
                data: {
                    labels: barangayLabels,
                    datasets: [
                        { label: 'Low', data: barangayLabels.map(b => data.barangay_matrix[b].Low), backgroundColor: green },
                        { label: 'Moderate', data: barangayLabels.map(b => data.barangay_matrix[b].Moderate), backgroundColor: yellow },
                        { label: 'High', data: barangayLabels.map(b => data.barangay_matrix[b].High), backgroundColor: red },
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true, grid: { display: false }, ticks: { font: { size: 9 }, maxRotation: 45 } },
                        y: { stacked: true, grid: { color: '#e2e8f0' } }
                    },
                    plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10, font: { size: 11 } } } }
                }
            });
        }

        const ctxSexSplit = document.getElementById('riskBySexChart');
        if (ctxSexSplit) {
            const sexLabels = Object.keys(data.risk_by_sex);
            new Chart(ctxSexSplit, {
                type: 'bar',
                data: {
                    labels: sexLabels,
                    datasets: [
                        { label: 'Low Risk', data: sexLabels.map(s => data.risk_by_sex[s].Low), backgroundColor: '#e8f5e9' },
                        { label: 'Moderate Risk', data: sexLabels.map(s => data.risk_by_sex[s].Moderate), backgroundColor: '#fef3c7' },
                        { label: 'High Risk', data: sexLabels.map(s => data.risk_by_sex[s].High), backgroundColor: '#fee2e2' },
                    ]
                },
                options: baseOpts
            });
        }

        const ctxAgeSplit = document.getElementById('riskByAgeChart');
        if (ctxAgeSplit) {
            const ageLabels = Object.keys(data.risk_by_age);
            new Chart(ctxAgeSplit, {
                type: 'bar',
                data: {
                    labels: ageLabels,
                    datasets: [
                        { label: 'Low Risk', data: ageLabels.map(a => data.risk_by_age[a].Low), backgroundColor: green },
                        { label: 'Moderate Risk', data: ageLabels.map(a => data.risk_by_age[a].Moderate), backgroundColor: yellow },
                        { label: 'High Risk', data: ageLabels.map(a => data.risk_by_age[a].High), backgroundColor: red },
                    ]
                },
                options: baseOpts
            });
        }
    }
});