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
                <td>${escapeHtml(patient.age)} / ${escapeHtml(patient.sex)}</td>
                <td>${escapeHtml(patient.date || '—')}</td>
                <td>${escapeHtml(patient.fbs ?? '—')}</td>
                <td>${risk}</td>
            </tr>`;
        }).join('');

        barangayPatientList.innerHTML = `<div style="overflow-x:auto;">
            <table class="data-table" style="min-width:520px;">
                <thead><tr><th>Name</th><th>Age / Sex</th><th>Date</th><th>FBS</th><th>Risk</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
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
        const { riskData, timeline, topBarangays } = window.__dashboardData;

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

        const ctxLine = document.getElementById('screeningsLineChart');
        if (ctxLine) {
            new Chart(ctxLine, {
                type: 'line',
                data: {
                    labels: Object.keys(timeline),
                    datasets: [{
                        label: 'Screenings', data: Object.values(timeline),
                        borderColor: green, backgroundColor: 'rgba(39,174,96,0.05)',
                        tension: 0.3, fill: true, borderWidth: 2
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true, grid: { color: '#e2e8f0' } }, x: { grid: { display: false } } }
                }
            });
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