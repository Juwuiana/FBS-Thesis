document.addEventListener('DOMContentLoaded', () => {
    // Shared Chart Style Declarations
    Chart.defaults.font.family = "'DM Sans', sans-serif";
    Chart.defaults.color = '#475569';
    
    // Config Options for Mobile Viewports
    const responsiveOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { position: 'bottom', labels: { boxWidth: 12, padding: 15, font: { size: 11 } } }
        }
    };

    /* ==========================================================================
       1. INTERACTIVE ATTRIBUTE DYNAMIC GRAPH ENGINE (10 FEATURE SPECIFICATIONS)
       ========================================================================== */
    const attrCtx = document.getElementById('dynamicAttributeChart');
    if (attrCtx) {
        let dynamicChartInstance = null; // Memory anchor to clear active asset pipes

        // Comprehensive data matrices mapping the 10 core clinical feature vectors
        const dataDictionary = {
            fbs: {
                type: 'bar',
                labels: ['Normal (<100 mg/dL)', 'Prediabetic (100-125 mg/dL)', 'Diabetic (>=126 mg/dL)'],
                datasets: [
                    { label: 'Low Risk Profile', data: [680, 42, 5], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [45, 185, 12], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [2, 18, 403], backgroundColor: '#ef4444' }
                ]
            },
            status: {
                type: 'doughnut',
                labels: ['Low Clinical Risk Status', 'Moderate Clinical Risk Status', 'High Clinical Risk Status'],
                datasets: [{
                    data: [727, 242, 423],
                    backgroundColor: ['#27ae60', '#f59e0b', '#ef4444'],
                    borderColor: '#ffffff',
                    borderWidth: 2
                }]
            },
            age: {
                type: 'bar',
                labels: ['18-29 Years', '30-39 Years', '#40-49 Years', '50-59 Years', '60+ Years'],
                datasets: [
                    { label: 'Low Risk Profile', data: [210, 180, 140, 90, 42], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [25, 45, 62, 55, 30], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [5, 12, 38, 72, 84], backgroundColor: '#ef4444' }
                ]
            },
            sex: {
                type: 'bar',
                labels: ['Male Patient Cohort', 'Female Patient Cohort'],
                datasets: [
                    { label: 'Low Risk Profile', data: [310, 417], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [102, 140], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [180, 243], backgroundColor: '#ef4444' }
                ]
            },
            bmi: {
                type: 'bar',
                labels: ['Underweight (<18.5)', 'Normal Weight (18.5-24.9)', 'Overweight (25.0-29.9)', 'Obese (>=30.0)'],
                datasets: [
                    { label: 'Low Risk Profile', data: [45, 620, 52, 10], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [8, 92, 112, 30], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [1, 14, 58, 350], backgroundColor: '#ef4444' }
                ]
            },
            bp: {
                type: 'bar',
                labels: ['Normal Systolic (<120)', 'Elevated Systolic (120-129)', 'Stage 1 Range (130-139)', 'Stage 2 Range (>=140)'],
                datasets: [
                    { label: 'Low Risk Profile', data: [510, 145, 60, 12], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [32, 85, 98, 27], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [4, 22, 114, 283], backgroundColor: '#ef4444' }
                ]
            },
            hypertension: {
                type: 'doughnut',
                labels: ['Diagnosed Hypertensive History', 'No Hypertensive Manifestations'],
                datasets: [{
                    data: [412, 980],
                    backgroundColor: ['#ef4444', '#27ae60'],
                    borderColor: '#ffffff',
                    borderWidth: 2
                }]
            },
            waist: {
                type: 'bar',
                labels: ['Normal Circumference Profile', 'Actionable Abdominal Obesity Cutoff'],
                datasets: [
                    { label: 'Low Risk Profile', data: [612, 115], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [130, 112], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [52, 371], backgroundColor: '#ef4444' }
                ]
            },
            smoking: {
                type: 'bar',
                labels: ['Never Smoked', 'Former Regular Smoker', 'Active Tobacco Smoker'],
                datasets: [
                    { label: 'Low Risk Profile', data: [590, 95, 42], backgroundColor: '#27ae60' },
                    { label: 'Moderate Risk Profile', data: [152, 60, 30], backgroundColor: '#f59e0b' },
                    { label: 'High Risk Profile', data: [180, 114, 129], backgroundColor: '#ef4444' }
                ]
            },
            family: {
                type: 'doughnut',
                labels: ['Zero Diabetes Lineage History', 'Single First-Degree Relative Record', 'Multi-Generational History'],
                datasets: [{
                    data: [640, 482, 270],
                    backgroundColor: ['#27ae60', '#f59e0b', '#ef4444'],
                    borderColor: '#ffffff',
                    borderWidth: 2
                }]
            }
        };

        // Instantiation controller loop method
        function generateDynamicGraph(attributeKey) {
            // Memory verification flush block: prevents graph overlap rendering bugs
            if (dynamicChartInstance) {
                dynamicChartInstance.destroy();
            }

            const targetConfig = dataDictionary[attributeKey];
            let graphOptions = { ...responsiveOptions };

            // Apply standard cartesian scaling handles exclusively if bar matrix parameters are called
            if (targetConfig.type === 'bar') {
                graphOptions.scales = {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#e2e8f0' }, beginAtZero: true }
                };
            } else if (targetConfig.type === 'doughnut') {
                graphOptions.cutout = '65%';
            }

            // Bind new chart context generation stream cleanly to the targeting node point
            dynamicChartInstance = new Chart(attrCtx, {
                type: targetConfig.type,
                data: {
                    labels: targetConfig.labels,
                    datasets: targetConfig.datasets
                },
                options: graphOptions
            });
        }

        // Initialize default view to handle the Fasting Blood Sugar array parameters
        generateDynamicGraph('fbs');

        // Map change listener stream directly to active selector interaction target
        document.getElementById('attributeSelector').addEventListener('change', (event) => {
            generateDynamicGraph(event.target.value);
        });
    }

    /* ==========================================================================
       2. REUSED FIXED COMPONENT MATRIX GENERATORS
       ========================================================================== */
    
    // A. Full 18 Barangay Epidemiological Matrix
    const fullBarangayCtx = document.getElementById('fullBarangayBarChart');
    if (fullBarangayCtx) {
        new Chart(fullBarangayCtx, {
            type: 'bar',
            data: {
                labels: [
                    'Aplaya', 'Balibago', 'Caingin', 'Dila', 'Dita', 'Don Jose', 
                    'Ibaba', 'Kanluran', 'Labas', 'Macabling', 'Malitlit', 'Malusak', 
                    'Market Area', 'Pooc', 'Pulong Sta. Cruz', 'Sto. Domingo', 'Sinalhan', 'Tagapo'
                ],
                datasets: [
                    { label: 'Low Risk Profile', data: [62, 110, 45, 80, 52, 40, 31, 28, 60, 78, 92, 24, 18, 50, 85, 33, 58, 71], backgroundColor: '#27ae60' },
                    { label: 'Elevated Risk Profile', data: [18, 42, 15, 38, 22, 19, 12, 9, 21, 31, 27, 8, 5, 14, 32, 11, 19, 24], backgroundColor: '#ef4444' }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { stacked: true, grid: { display: false }, ticks: { font: { size: 9 }, maxRotation: 45 } },
                    y: { stacked: true, grid: { color: '#e2e8f0' } }
                },
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10 } } }
            }
        });
    }

    // B. Demographic Split: Risk By Sex
    const sexCtx = document.getElementById('riskBySexChart');
    if (sexCtx) {
        new Chart(sexCtx, {
            type: 'bar',
            data: {
                labels: ['Male Cohort Attribute', 'Female Cohort Attribute'],
                datasets: [
                    { label: 'Low Risk', data: [420, 580], backgroundColor: '#e8f5e9' },
                    { label: 'Moderate Risk', data: [110, 140], backgroundColor: '#fef3c7' },
                    { label: 'High Risk', data: [45, 37], backgroundColor: '#fee2e2' }
                ]
            },
            options: responsiveOptions
                });
            }

    // C. Demographic Split: Risk By Age Bands
    const ageCtx = document.getElementById('riskByAgeChart');
    if (ageCtx) {
        new Chart(ageCtx, {
            type: 'bar',
            data: {
                labels: ['18-29', '30-39', '40-49', '50-59', '60+'],
                datasets: [
                    { label: 'Low Risk', data: [210, 180, 140, 90, 42], backgroundColor: '#27ae60' },
                    { label: 'Elevated Risk', data: [15, 29, 54, 68, 72], backgroundColor: '#ef4444' }
                ]
            },
            options: responsiveOptions
        });
    }

    // D. Global Feature Importances Vector (SHAP Attributions)
    const shapCtx = document.getElementById('shapImportanceChart');
    if (shapCtx) {
        new Chart(shapCtx, {
            type: 'bar',
            data: {
                labels: [
                    'Fasting Blood Sugar Score Value', 
                    'Age Chronological Feature Interval', 
                    'Systolic Blood Pressure Vector', 
                    'Body Mass Index (BMI)', 
                    'Family Medical Record Lineage History', 
                    'Physical Exercise Inactivity Variable'
                ],
                datasets: [{
                    label: 'Mean Absolute SHAP Value Attribution Weighting',
                    data: [0.44, 0.21, 0.15, 0.11, 0.06, 0.03],
                    backgroundColor: '#133c20',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: { grid: { color: '#e2e8f0' } },
                    y: { grid: { display: false } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }
});