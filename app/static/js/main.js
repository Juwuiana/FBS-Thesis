// ==========================================================
// FBS-Based Diabetes Risk Prediction — Shared JS
// ==========================================================

// Chart.js global defaults for mobile responsiveness
Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = false;

// ── Dashboard: Donut Chart ──
function initDonutChart() {
  const el = document.getElementById('donutChart');
  if (!el) return;
  new Chart(el, {
    type: 'doughnut',
    data: {
      labels: ['Low Risk', 'Moderate Risk', 'High Risk'],
      datasets: [{
        data: [72.1, 17.0, 5.9],
        backgroundColor: ['#4caf50', '#ff9800', '#f44336'],
        borderWidth: 2, borderColor: '#fff', hoverOffset: 4
      }]
    },
    options: {
      cutout: '65%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}%` } }
      },
      responsive: true,
      maintainAspectRatio: true
    }
  });
}

// ── Dashboard: Line Chart ──
function initLineChart() {
  const el = document.getElementById('lineChart');
  if (!el) return;
  const labels = ['May 14', 'May 16', 'May 18', 'May 20', 'May 22', 'May 24', 'May 27'];
  new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Total Screened',
          data: [310, 295, 320, 305, 315, 300, 312],
          borderColor: '#4caf50', backgroundColor: 'rgba(76,175,80,.08)',
          fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2
        },
        {
          label: 'At Risk',
          data: [155, 148, 162, 152, 158, 150, 156],
          borderColor: '#f44336', backgroundColor: 'rgba(244,67,54,.05)',
          fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 }, maxRotation: 45 } },
        y: { grid: { color: '#f0f4f0' }, ticks: { font: { size: 11 } }, beginAtZero: false }
      },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } }
      }
    }
  });
}

// ── Dashboard: Radar Chart ──
function initRadarChart() {
  const el = document.getElementById('radarChart');
  if (!el) return;
  new Chart(el, {
    type: 'radar',
    data: {
      labels: ['Accuracy', 'Precision', 'Recall', 'F1-Score', 'ROC-AUC'],
      datasets: [{
        label: 'Current Model',
        data: [0.893, 0.87, 0.88, 0.87, 0.93],
        backgroundColor: 'rgba(76,175,80,.15)', borderColor: '#4caf50',
        borderWidth: 2, pointBackgroundColor: '#4caf50', pointRadius: 3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        r: {
          min: 0.75, max: 1,
          ticks: { stepSize: 0.05, font: { size: 10 }, backdropColor: 'transparent' },
          grid: { color: '#e0e8e0' },
          pointLabels: { font: { size: 11 }, color: '#4a5a4a' }
        }
      },
      plugins: { legend: { display: false } }
    }
  });
}

// ── Mobile Sidebar Toggle ──
function initSidebarToggle() {
  const toggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!toggle || !sidebar || !overlay) return;

  const closeSidebar = () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
  };

  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
  });
  overlay.addEventListener('click', closeSidebar);
  sidebar.querySelectorAll('.sidebar-nav a').forEach(link => {
    link.addEventListener('click', () => { if (window.innerWidth <= 991) closeSidebar(); });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initSidebarToggle();
  initDonutChart();
  initLineChart();
  initRadarChart();
});