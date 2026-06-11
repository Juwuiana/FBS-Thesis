document.addEventListener('DOMContentLoaded', function () {
    // ─── Colours ────────────────────────────────────────────────────────────────
    const green        = '#27ae60';
    const yellow       = '#f59e0b';
    const red          = '#ef4444';
    const darkGreen    = '#133c20';
    const lightGreenBg = 'rgba(39, 174, 96, 0.2)';
    const mutedText    = '#475569';

    // Guard: only configure Chart.js when it's actually loaded on this page
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

    /* =========================================================================
       SECTION 0 — UI INTERACTIVITY
       Hub toggle and schema accordion live on the Data Management page and do
       NOT need Chart.js, so they run unconditionally.
       ========================================================================= */

    // Hub toggle (show / hide import-export panel)
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

    // Schema accordion
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

    /* =========================================================================
       Everything below requires Chart.js — bail early if it isn't loaded.
       ========================================================================= */
    if (typeof Chart === 'undefined') return;

    /* =========================================================================
       SECTION 1 — DASHBOARD CHARTS
       ========================================================================= */

    // 1. Risk Distribution Donut
    const ctxDonut = document.getElementById('riskDonutChart');
    if (ctxDonut) {
        new Chart(ctxDonut, {
            type: 'doughnut',
            data: {
                labels: ['Low Risk', 'Moderate Risk', 'High Risk'],
                datasets: [{
                    data: [77.1, 17.0, 5.9],
                    backgroundColor: [green, yellow, red],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: { position: 'right', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11 } } }
                }
            }
        });
    }

    // 2. Screenings Over Time Line Chart
    const ctxLine = document.getElementById('screeningsLineChart');
    if (ctxLine) {
        new Chart(ctxLine, {
            type: 'line',
            data: {
                labels: ['May 14', 'May 16', 'May 18', 'May 20', 'May 22', 'May 24', 'May 27'],
                datasets: [
                    {
                        label: 'Total Screened',
                        data: [290, 260, 310, 320, 305, 315, 300],
                        borderColor: green,
                        backgroundColor: 'rgba(39,174,96,0.05)',
                        tension: 0.3, fill: true, borderWidth: 2
                    },
                    {
                        label: 'At Risk',
                        data: [140, 120, 150, 145, 135, 142, 145],
                        borderColor: red,
                        backgroundColor: 'rgba(239,68,68,0.05)',
                        tension: 0.3, fill: true, borderWidth: 2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, font: { size: 11 } } } },
                scales: {
                    y: { beginAtZero: true, max: 400, grid: { color: '#e2e8f0' } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    // 3. Top Barangays Horizontal Bar
    const ctxBar = document.getElementById('barangayBarChart');
    if (ctxBar) {
        new Chart(ctxBar, {
            type: 'bar',
            data: {
                labels: ['Kanluran', 'Market Area', 'Dila', 'Dita', 'Malitlit'],
                datasets: [{
                    label: 'At Risk Count',
                    data: [58, 47, 41, 33, 29],
                    backgroundColor: green,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { beginAtZero: true, max: 60, grid: { color: '#e2e8f0' } },
                    y: { grid: { display: false } }
                }
            }
        });
    }

    // 4. Model Performance Radar
    const ctxRadar = document.getElementById('modelRadarChart');
    if (ctxRadar) {
        new Chart(ctxRadar, {
            type: 'radar',
            data: {
                labels: ['Accuracy', 'Precision', 'Recall', 'F1-Score', 'ROC-AUC'],
                datasets: [{
                    label: 'Current Model',
                    data: [0.89, 0.87, 0.88, 0.87, 0.93],
                    backgroundColor: lightGreenBg,
                    borderColor: green,
                    pointBackgroundColor: green,
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { r: { min: 0.5, max: 1.0, ticks: { display: false } } }
            }
        });
    }

    /* =========================================================================
       SECTION 2 — HEALTH RESULTS CHARTS
       ========================================================================= */

    // Dynamic attribute chart (dropdown-driven)
    const dynamicAttrCanvas = document.getElementById('dynamicAttributeChart');
    if (dynamicAttrCanvas) {
        let attributeChartInstance = null;

        const matrix = {
            fbs: {
                type: 'bar',
                labels: ['Normal (<100 mg/dL)', 'Prediabetic (100-125)', 'Diabetic (≥126)'],
                datasets: [
                    { label: 'Low Risk',      data: [680, 42, 5],   backgroundColor: green  },
                    { label: 'Moderate Risk', data: [45, 185, 12],  backgroundColor: yellow },
                    { label: 'High Risk',     data: [2, 18, 403],   backgroundColor: red    }
                ]
            },
            status: {
                type: 'doughnut',
                labels: ['Low Clinical Risk', 'Moderate Clinical Risk', 'High Clinical Risk'],
                datasets: [{ data: [727, 242, 423], backgroundColor: [green, yellow, red], borderColor: '#ffffff', borderWidth: 2 }]
            },
            age: {
                type: 'bar',
                labels: ['18-29', '30-39', '40-49', '50-59', '60+'],
                datasets: [
                    { label: 'Low Risk',      data: [210, 180, 140, 90, 42], backgroundColor: green  },
                    { label: 'Moderate Risk', data: [25, 45, 62, 55, 30],   backgroundColor: yellow },
                    { label: 'High Risk',     data: [5, 12, 38, 72, 84],    backgroundColor: red    }
                ]
            },
            sex: {
                type: 'bar',
                labels: ['Male', 'Female'],
                datasets: [
                    { label: 'Low Risk',      data: [310, 417], backgroundColor: green  },
                    { label: 'Moderate Risk', data: [102, 140], backgroundColor: yellow },
                    { label: 'High Risk',     data: [180, 243], backgroundColor: red    }
                ]
            },
            bmi: {
                type: 'bar',
                labels: ['Underweight (<18.5)', 'Normal (18.5-24.9)', 'Overweight (25-29.9)', 'Obese (≥30)'],
                datasets: [
                    { label: 'Low Risk',      data: [45, 620, 52, 10],  backgroundColor: green  },
                    { label: 'Moderate Risk', data: [8, 92, 112, 30],   backgroundColor: yellow },
                    { label: 'High Risk',     data: [1, 14, 58, 350],   backgroundColor: red    }
                ]
            },
            bp: {
                type: 'bar',
                labels: ['Normal (<120)', 'Elevated (120-129)', 'Stage 1 (130-139)', 'Stage 2 (≥140)'],
                datasets: [
                    { label: 'Low Risk',      data: [510, 145, 60, 12],  backgroundColor: green  },
                    { label: 'Moderate Risk', data: [32, 85, 98, 27],    backgroundColor: yellow },
                    { label: 'High Risk',     data: [4, 22, 114, 283],   backgroundColor: red    }
                ]
            },
            hypertension: {
                type: 'doughnut',
                labels: ['Hypertensive History', 'No Hypertensive History'],
                datasets: [{ data: [412, 980], backgroundColor: [red, green], borderColor: '#ffffff', borderWidth: 2 }]
            },
            waist: {
                type: 'bar',
                labels: ['Normal Range', 'Abdominal Obesity'],
                datasets: [
                    { label: 'Low Risk',      data: [612, 115], backgroundColor: green  },
                    { label: 'Moderate Risk', data: [130, 112], backgroundColor: yellow },
                    { label: 'High Risk',     data: [52, 371],  backgroundColor: red    }
                ]
            },
            smoking: {
                type: 'bar',
                labels: ['Never Smoked', 'Former Smoker', 'Active Smoker'],
                datasets: [
                    { label: 'Low Risk',      data: [590, 95, 42],  backgroundColor: green  },
                    { label: 'Moderate Risk', data: [152, 60, 30],  backgroundColor: yellow },
                    { label: 'High Risk',     data: [180, 114, 129], backgroundColor: red   }
                ]
            },
            family: {
                type: 'doughnut',
                labels: ['No Family History', 'First-Degree Relative', 'Multi-Generational'],
                datasets: [{ data: [640, 482, 270], backgroundColor: [green, yellow, red], borderColor: '#ffffff', borderWidth: 2 }]
            }
        };

        function renderAttrChart(key) {
            if (attributeChartInstance) attributeChartInstance.destroy();
            const cfg  = matrix[key];
            const opts = { ...baseOpts };
            if (cfg.type === 'bar') {
                opts.scales = { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: '#e2e8f0' } } };
            } else {
                opts.cutout = '65%';
            }
            attributeChartInstance = new Chart(dynamicAttrCanvas, { type: cfg.type, data: { labels: cfg.labels, datasets: cfg.datasets }, options: opts });
        }

        renderAttrChart('fbs');
        const selector = document.getElementById('attributeSelector');
        if (selector) selector.addEventListener('change', e => renderAttrChart(e.target.value));
    }

    // Full 18-barangay stacked bar
    const ctxFullBarangay = document.getElementById('fullBarangayBarChart');
    if (ctxFullBarangay) {
        new Chart(ctxFullBarangay, {
            type: 'bar',
            data: {
                labels: ['Aplaya','Balibago','Caingin','Dila','Dita','Don Jose','Ibaba','Kanluran','Labas','Macabling','Malitlit','Malusak','Market Area','Pooc','Pulong Sta. Cruz','Sto. Domingo','Sinalhan','Tagapo'],
                datasets: [
                    { label: 'Low Risk',      data: [62,110,45,80,52,40,31,28,60,78,92,24,18,50,85,33,58,71], backgroundColor: green },
                    { label: 'Elevated Risk', data: [18,42,15,38,22,19,12,9,21,31,27,8,5,14,32,11,19,24],    backgroundColor: red   }
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

    // Risk by sex
    const ctxSexSplit = document.getElementById('riskBySexChart');
    if (ctxSexSplit) {
        new Chart(ctxSexSplit, {
            type: 'bar',
            data: {
                labels: ['Male', 'Female'],
                datasets: [
                    { label: 'Low Risk',      data: [420, 580], backgroundColor: '#e8f5e9' },
                    { label: 'Moderate Risk', data: [110, 140], backgroundColor: '#fef3c7' },
                    { label: 'High Risk',     data: [45, 37],   backgroundColor: '#fee2e2' }
                ]
            },
            options: baseOpts
        });
    }

    // Risk by age
    const ctxAgeSplit = document.getElementById('riskByAgeChart');
    if (ctxAgeSplit) {
        new Chart(ctxAgeSplit, {
            type: 'bar',
            data: {
                labels: ['18-29', '30-39', '40-49', '50-59', '60+'],
                datasets: [
                    { label: 'Low Risk',      data: [210, 180, 140, 90, 42], backgroundColor: green },
                    { label: 'Elevated Risk', data: [15, 29, 54, 68, 72],   backgroundColor: red   }
                ]
            },
            options: baseOpts
        });
    }

    // SHAP feature importance
    const ctxShap = document.getElementById('shapImportanceChart');
    if (ctxShap) {
        new Chart(ctxShap, {
            type: 'bar',
            data: {
                labels: ['Fasting Blood Sugar','Age','Systolic Blood Pressure','BMI','Family History','Waist Circumference','Smoking Status','Hypertension History'],
                datasets: [{
                    label: 'Mean |SHAP|',
                    data: [0.38, 0.18, 0.14, 0.11, 0.08, 0.06, 0.03, 0.02],
                    backgroundColor: darkGreen,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                indexAxis: 'y',
                scales: { x: { grid: { color: '#e2e8f0' }, beginAtZero: true }, y: { grid: { display: false } } },
                plugins: { legend: { display: false } }
            }
        });
    }
});