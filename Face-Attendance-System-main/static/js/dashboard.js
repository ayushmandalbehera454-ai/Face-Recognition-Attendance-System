(function () {
  const $ = (id) => document.getElementById(id);
  let data = null, period = 'daily', charts = {};

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function make(id, cfg) {
    charts[id]?.destroy();
    charts[id] = new Chart($(id), cfg);
  }
  function theme() {
    const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    Chart.defaults.color = dark ? '#aeb8cc' : '#5b667a';
    Chart.defaults.borderColor = dark ? '#2a3550' : '#e2e6ec';
    Chart.defaults.font.family = '"Source Sans 3", sans-serif';
  }

  function render() {
    if (!data) return;
    theme();
    const t = data.today, teal = '#0f9d8a', amber = '#e3a008', rose = '#d1495b';
    $('sTotal').textContent = t.total; $('sPresent').textContent = t.attended; $('sAbsent').textContent = t.absent;
    $('sPct').textContent = t.percentage + '%'; $('sBar').style.width = t.percentage + '%';
    $('sLate').textContent = t.late ? `${t.late} of them late` : '';

    const s = data[period];
    make('trendChart', { type: period === 'daily' ? 'line' : 'bar',
      data: { labels: s.labels, datasets: [{ label: 'People attended', data: s.values, borderColor: teal, backgroundColor: period === 'daily' ? 'rgba(15,157,138,.15)' : teal, fill: period === 'daily', tension: .35, borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } } });

    make('statusChart', { type: 'doughnut',
      data: { labels: ['On time', 'Late', 'Not marked'], datasets: [{ data: [t.present, t.late, t.absent], backgroundColor: [teal, amber, rose], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'bottom' } } } });

    make('deptChart', { type: 'bar',
      data: { labels: data.departments.labels, datasets: [{ label: '% attended', data: data.departments.values, backgroundColor: teal, borderRadius: 6 }] },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, max: 100 } } } });

    $('recentBody').innerHTML = data.recent.length ? data.recent.map((r) =>
      `<tr><td>${esc(r.name)}</td><td>${esc(r.date)}</td><td>${esc(r.time)}</td><td>${pill(r.status)}</td><td>${esc(r.method)}</td></tr>`).join('')
      : '<tr><td colspan="5" class="text-center text-secondary py-3">No attendance yet. Open Attendance and start recognition.</td></tr>';
  }

  async function load() { try { data = await api('/api/dashboard/stats'); render(); } catch (e) { toast(e.message, 'danger'); } }

  document.querySelectorAll('[data-period]').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('[data-period]').forEach((x) => x.classList.remove('active'));
    b.classList.add('active'); period = b.dataset.period; render();
  }));
  window.addEventListener('themechange', render);
  window.addEventListener('attendance-new', load);
  load();
  setInterval(load, 60000);
})();
