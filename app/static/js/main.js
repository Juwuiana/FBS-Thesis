// ==========================================================
// FBS-Based Diabetes Risk Prediction — Shared JS
// ==========================================================

Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = false;

// ── Dashboard: Donut Chart ──
function initDonutChart(data) {
  const el = document.getElementById('donutChart');
  if (!el) return;
  const values = data
    ? [data.low.pct, data.moderate.pct, data.high.pct]
    : [72.1, 17.0, 5.9];
  new Chart(el, {
    type: 'doughnut',
    data: {
      labels: ['Low Risk', 'Moderate Risk', 'High Risk'],
      datasets: [{
        data: values,
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
function initLineChart(data) {
  const el = document.getElementById('lineChart');
  if (!el) return;
  const labels = data ? data.labels : ['May 14', 'May 16', 'May 18', 'May 20', 'May 22', 'May 24', 'May 27'];
  const totalScreened = data ? data.totalScreened : [310, 295, 320, 305, 315, 300, 312];
  const atRisk = data ? data.atRisk : [155, 148, 162, 152, 158, 150, 156];
  new Chart(el, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Total Screened',
          data: totalScreened,
          borderColor: '#4caf50', backgroundColor: 'rgba(76,175,80,.08)',
          fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2
        },
        {
          label: 'At Risk',
          data: atRisk,
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
function initRadarChart(data) {
  const el = document.getElementById('radarChart');
  if (!el) return;
  const values = data
    ? [data.accuracy / 100, data.precision, data.recall, data.f1_score, data.roc_auc]
    : [0.893, 0.87, 0.88, 0.87, 0.93];
  new Chart(el, {
    type: 'radar',
    data: {
      labels: ['Accuracy', 'Precision', 'Recall', 'F1-Score', 'ROC-AUC'],
      datasets: [{
        label: 'Current Model',
        data: values,
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

// ── Entry point called from dashboard/index.html's block scripts ──
function initAdminDashboardCharts(data) {
  initDonutChart(data ? data.riskDistribution : null);
  initLineChart(data ? data.timeline : null);
  initRadarChart(data ? data.modelPerformance : null);
}
window.initAdminDashboardCharts = initAdminDashboardCharts;

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

function initSessionTimeout() {
  const body = document.body;
  if (!body) return;

  const timeoutMinutes = Number(body.dataset.sessionTimeoutMinutes || 30);
  if (!Number.isFinite(timeoutMinutes) || timeoutMinutes <= 0) return;

  const timeoutMs = timeoutMinutes * 60 * 1000;
  const warningMs = 20 * 1000;
  const logoutUrl = body.dataset.logoutUrl || '/logout';
  let inactivityTimer = null;
  let warningTimer = null;
  let warningInterval = null;
  let warningEl = null;

  const logoutUser = () => {
    if (document.visibilityState === 'hidden') {
      window.location.replace(logoutUrl);
      return;
    }
    window.location.href = logoutUrl;
  };

  const clearWarning = () => {
    if (warningInterval) clearInterval(warningInterval);
    warningInterval = null;
    if (warningEl) {
      warningEl.remove();
      warningEl = null;
    }
  };

  const showWarning = deadline => {
    clearWarning();

    warningEl = document.createElement('div');
    warningEl.style.position = 'fixed';
    warningEl.style.top = '16px';
    warningEl.style.left = '50%';
    warningEl.style.transform = 'translateX(-50%)';
    warningEl.style.zIndex = '99999';
    warningEl.style.background = '#fff3cd';
    warningEl.style.border = '1px solid #f0c36d';
    warningEl.style.color = '#7a4a00';
    warningEl.style.padding = '10px 18px';
    warningEl.style.borderRadius = '999px';
    warningEl.style.boxShadow = '0 8px 20px rgba(0,0,0,0.12)';
    warningEl.style.fontSize = '14px';
    warningEl.style.fontWeight = '600';
    warningEl.style.lineHeight = '1.3';
    warningEl.style.textAlign = 'center';

    const countdownLabel = document.createElement('span');
    warningEl.appendChild(countdownLabel);
    document.body.appendChild(warningEl);

    const updateWarning = () => {
      const remainingMs = Math.max(0, deadline - Date.now());
      const remainingSeconds = Math.ceil(remainingMs / 1000);
      countdownLabel.textContent = `Your session will expire in ${remainingSeconds} second${remainingSeconds === 1 ? '' : 's'}.`;
      if (remainingMs <= 0) {
        clearWarning();
      }
    };

    updateWarning();
    warningInterval = setInterval(updateWarning, 1000);
  };

  const resetTimer = () => {
    if (inactivityTimer) clearTimeout(inactivityTimer);
    if (warningTimer) clearTimeout(warningTimer);
    clearWarning();

    const deadline = Date.now() + timeoutMs;
    inactivityTimer = setTimeout(logoutUser, timeoutMs);

    const warningDelay = Math.max(0, timeoutMs - warningMs);
    warningTimer = setTimeout(() => showWarning(deadline), warningDelay);
  };

  const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart', 'touchmove', 'pointerdown'];
  activityEvents.forEach(eventName => {
    document.addEventListener(eventName, resetTimer, { passive: true });
  });

  resetTimer();
}

document.addEventListener('DOMContentLoaded', () => {
  initSidebarToggle();
  initSessionTimeout();
});