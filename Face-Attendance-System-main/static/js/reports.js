(function () {
  const $ = (id) => document.getElementById(id);
  let chart = null;
  const today = new Date().toISOString().slice(0, 10);
  $('rDate').value = today; $('rMonth').value = today.slice(0, 7);
  $('rFrom').value = today.slice(0, 8) + '01'; $('rTo').value = today;

  function toggle() {
    const t = $('rType').value;
    document.querySelectorAll('.f-daily').forEach((e) => e.classList.toggle('d-none', t !== 'daily'));
    document.querySelectorAll('.f-monthly').forEach((e) => e.classList.toggle('d-none', t !== 'monthly'));
    document.querySelectorAll('.f-individual').forEach((e) => e.classList.toggle('d-none', t !== 'individual'));
    document.querySelectorAll('.f-range').forEach((e) => e.classList.toggle('d-none', !(t === 'individual' || t === 'department')));
  }
  function params() {
    const t = $('rType').value, p = new URLSearchParams({ type: t });
    if (t === 'daily') { p.set('date', $('rDate').value); if ($('rDept').value) p.set('department', $('rDept').value); }
    if (t === 'monthly') p.set('month', $('rMonth').value);
    if (t === 'individual') { p.set('student', $('rStudent').value); p.set('from', $('rFrom').value); p.set('to', $('rTo').value); }
    if (t === 'department') { p.set('from', $('rFrom').value); p.set('to', $('rTo').value); }
    return p.toString();
  }
  function drawChart(c) {
    const dark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    Chart.defaults.color = dark ? '#aeb8cc' : '#5b667a'; Chart.defaults.borderColor = dark ? '#2a3550' : '#e2e6ec';
    chart?.destroy();
    chart = new Chart($('reportChart'), { type: 'bar',
      data: { labels: c.labels, datasets: [{ label: c.label, data: c.values, backgroundColor: '#0f9d8a', borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
  }

  $('rType').addEventListener('change', toggle);
  $('reportForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = params();
    try {
      const d = await api('/api/reports/data?' + q);
      $('reportCard').classList.remove('d-none');
      $('reportTitle').textContent = d.title;
      $('reportHead').innerHTML = '<tr>' + d.columns.map((c) => `<th>${esc(c)}</th>`).join('') + '</tr>';
      $('reportBody').innerHTML = d.rows.length ? d.rows.map((r) => '<tr>' + r.map((v, i) =>
        `<td>${d.columns[i] === 'Status' ? pill(v) : esc(String(v))}</td>`).join('') + '</tr>').join('')
        : `<tr><td colspan="${d.columns.length}" class="text-center text-secondary py-4">No data for this selection.</td></tr>`;
      $('dlCsv').href = '/reports/export/csv?' + q; $('dlXlsx').href = '/reports/export/xlsx?' + q; $('dlPdf').href = '/reports/export/pdf?' + q;
      drawChart(d.chart);
    } catch (err) { toast(err.message, 'danger'); }
  });
  window.addEventListener('themechange', () => { if (chart) { chart.destroy(); chart = null; } });
  toggle();
})();
