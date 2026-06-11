/* ── reliability.js ── */
/* Place at: static/js/reliability.js */

function initReliabilityCharts(data) {

  /* ── ROC Curve ── */
  const rocCtx = document.getElementById('rocChart');
  if (rocCtx && data.rocPoints) {
    new Chart(rocCtx, {
      type: 'line',
      data: {
        datasets: [
          {
            label: 'ROC Curve',
            data: data.rocPoints.map(p => ({ x: p.fpr, y: p.tpr })),
            borderColor: '#4caf50',
            backgroundColor: 'rgba(76,175,80,.08)',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2
          },
          {
            label: 'Random',
            data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
            borderColor: '#ccc',
            borderDash: [4, 4],
            pointRadius: 0,
            borderWidth: 1,
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        scales: {
          x: {
            type: 'linear',
            min: 0, max: 1,
            title: { display: true, text: 'FPR', font: { size: 10 } },
            ticks: { font: { size: 10 } },
            grid: { color: '#f0f4f0' }
          },
          y: {
            min: 0, max: 1,
            title: { display: true, text: 'TPR', font: { size: 10 } },
            ticks: { font: { size: 10 } },
            grid: { color: '#f0f4f0' }
          }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }

  /* ── Feature Importance ── */
  const featCtx = document.getElementById('featureChart');
  if (featCtx && data.features) {
    const sorted = [...data.features].sort((a, b) => b.importance - a.importance);
    new Chart(featCtx, {
      type: 'bar',
      data: {
        labels: sorted.map(f => f.name),
        datasets: [{
          label: 'Importance',
          data: sorted.map(f => f.importance),
          backgroundColor: sorted.map((_, i) =>
            i === 0 ? '#4caf50' : 'rgba(76,175,80,.35)'
          ),
          borderRadius: 4,
          borderSkipped: false
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: true,
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: '#f0f4f0' },
            ticks: { font: { size: 11 } }
          },
          y: {
            grid: { display: false },
            ticks: { font: { size: 11 } }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` Importance: ${ctx.parsed.x.toFixed(4)}`
            }
          }
        }
      }
    });
  }

  /* ── Cross-Validation Bar ── */
  const cvCtx = document.getElementById('cvChart');
  if (cvCtx && data.cvScores) {
    const foldLabels = data.cvScores.map((_, i) => `Fold ${i + 1}`);
    const mean = data.cvScores.reduce((a, b) => a + b, 0) / data.cvScores.length;

    new Chart(cvCtx, {
      type: 'bar',
      data: {
        labels: foldLabels,
        datasets: [
          {
            label: 'AUC per Fold',
            data: data.cvScores,
            backgroundColor: data.cvScores.map(v =>
              v >= mean ? 'rgba(76,175,80,.7)' : 'rgba(244,67,54,.5)'
            ),
            borderRadius: 4,
            borderSkipped: false
          },
          {
            label: 'Mean AUC',
            data: Array(data.cvScores.length).fill(mean),
            type: 'line',
            borderColor: '#1a2e1a',
            borderDash: [5, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { size: 11 } }
          },
          y: {
            min: 0.7, max: 1.0,
            grid: { color: '#f0f4f0' },
            ticks: { font: { size: 11 }, stepSize: 0.05 }
          }
        },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { boxWidth: 10, font: { size: 11 } }
          },
          tooltip: {
            callbacks: {
              label: ctx => ` AUC: ${ctx.parsed.y.toFixed(4)}`
            }
          }
        }
      }
    });
  }
}