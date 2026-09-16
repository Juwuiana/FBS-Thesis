document.addEventListener('DOMContentLoaded', async () => {
    const res = await fetch('/api/analytics/health_results');
    const data = await res.json();

    const ATTRIBUTE_LABELS = {
        fbs: 'Fasting Blood Sugar Levels',
        status: 'Predicted Diabetes Risk Status',
        age: 'Age Distribution',
        sex: 'Sex Distribution',
        bmi: 'BMI Classification',
        bp: 'Blood Pressure Segments',
        hypertension: 'Hypertension History',
        waist: 'Waist Circumference',
        smoking: 'Smoking Status',
        family: 'Family History of Diabetes',
    };

    let attributeChart = null;
    function renderAttributeChart(key) {
        const dist = data[key] || {};
        const labels = Object.keys(dist);
        const values = Object.values(dist);

        if (attributeChart) attributeChart.destroy();
        attributeChart = new Chart(document.getElementById('dynamicAttributeChart'), {
            type: 'bar',
            data: {
                labels,
                datasets: [{ label: ATTRIBUTE_LABELS[key], data: values, backgroundColor: '#27ae60' }],
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
    }

    document.getElementById('attributeSelector').addEventListener('change', (e) => {
        renderAttributeChart(e.target.value);
    });
    renderAttributeChart('fbs');

    // Barangay stratified risk matrix -- stacked bar
    const barangayLabels = Object.keys(data.barangay_matrix);
    new Chart(document.getElementById('fullBarangayBarChart'), {
        type: 'bar',
        data: {
            labels: barangayLabels,
            datasets: [
                { label: 'Low', data: barangayLabels.map(b => data.barangay_matrix[b].Low), backgroundColor: '#4caf50' },
                { label: 'Moderate', data: barangayLabels.map(b => data.barangay_matrix[b].Moderate), backgroundColor: '#f59e0b' },
                { label: 'High', data: barangayLabels.map(b => data.barangay_matrix[b].High), backgroundColor: '#ef4444' },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { x: { stacked: true }, y: { stacked: true } },
        },
    });

    // Risk by sex
    const sexLabels = Object.keys(data.risk_by_sex);
    new Chart(document.getElementById('riskBySexChart'), {
        type: 'bar',
        data: {
            labels: sexLabels,
            datasets: [
                { label: 'Low', data: sexLabels.map(s => data.risk_by_sex[s].Low), backgroundColor: '#4caf50' },
                { label: 'Moderate', data: sexLabels.map(s => data.risk_by_sex[s].Moderate), backgroundColor: '#f59e0b' },
                { label: 'High', data: sexLabels.map(s => data.risk_by_sex[s].High), backgroundColor: '#ef4444' },
            ],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } },
    });

    // Risk by age
    const ageLabels = Object.keys(data.risk_by_age);
    new Chart(document.getElementById('riskByAgeChart'), {
        type: 'bar',
        data: {
            labels: ageLabels,
            datasets: [
                { label: 'Low', data: ageLabels.map(a => data.risk_by_age[a].Low), backgroundColor: '#4caf50' },
                { label: 'Moderate', data: ageLabels.map(a => data.risk_by_age[a].Moderate), backgroundColor: '#f59e0b' },
                { label: 'High', data: ageLabels.map(a => data.risk_by_age[a].High), backgroundColor: '#ef4444' },
            ],
        },
        options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } },
    });
});