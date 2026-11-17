/* Live recognition + attendance table */
(function () {
  const $ = (id) => document.getElementById(id);
  const video = $('video'), overlay = $('overlay'), cam = new Camera(video);
  let running = false;

  const COLORS = { marked: '#0f9d8a', already: '#0f9d8a', liveness: '#e3a008', review: '#e3a008', unknown: '#d1495b' };

  function setState(text, cls) { const b = $('liveState'); b.textContent = text; b.className = `badge text-bg-${cls}`; }

  async function start() {
    try {
      const size = await cam.start();
      $('camWrap').style.aspectRatio = `${size.w} / ${size.h}`;
      $('camWrap').classList.add('live');
      running = true; setState('Live', 'success');
      $('startBtn').disabled = true; $('stopBtn').disabled = false;
      tick();
    } catch (e) { toast(e.message, 'danger'); }
  }
  function stop() {
    running = false; cam.stop(); $('camWrap').classList.remove('live');
    overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
    setState('Stopped', 'secondary'); $('startBtn').disabled = false; $('stopBtn').disabled = true;
    $('liveList').innerHTML = '<div class="text-secondary small">No faces detected yet.</div>';
  }

  async function tick() {
    if (!running) return;
    let delay = 150;
    try {
      const img = cam.capture(480, 0.7);
      if (img) { const d = await api('/api/attendance/recognize', { method: 'POST', body: { image: img } }); draw(d.faces); list(d.faces);
        if (d.faces.some((f) => f.state === 'marked')) loadRecords(); }
    } catch (e) { setState('Error', 'danger'); toast(e.message, 'danger'); delay = 3000; }
    if (running) setTimeout(tick, delay);
  }

  function draw(faces) {
    overlay.width = video.clientWidth; overlay.height = video.clientHeight;
    const ctx = overlay.getContext('2d'); ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.lineWidth = 3; ctx.font = '600 14px "Source Sans 3", sans-serif';
    faces.forEach((f) => {
      const x = f.box.x * overlay.width, y = f.box.y * overlay.height, w = f.box.w * overlay.width, h = f.box.h * overlay.height;
      const color = COLORS[f.state] || '#d1495b';
      ctx.strokeStyle = color; ctx.strokeRect(x, y, w, h);
      const label = f.state === 'unknown' ? 'Unregistered' : `${f.name}${f.student_code ? ' (' + f.student_code + ')' : ''}`;
      const sub = f.distance !== null && f.state !== 'unknown' ? `${f.confidence}%  d=${f.distance}` : '';
      const text = sub ? `${label}  ${sub}` : label;
      const tw = ctx.measureText(text).width + 12;
      ctx.fillStyle = color; ctx.fillRect(x, Math.max(0, y - 24), tw, 24);
      ctx.fillStyle = '#fff'; ctx.fillText(text, x + 6, Math.max(16, y - 7));
    });
  }

  function list(faces) {
    if (!faces.length) { $('liveList').innerHTML = '<div class="text-secondary small">No faces detected.</div>'; return; }
    $('liveList').innerHTML = faces.map((f) => `
      <div class="live-item s-${esc(f.state)}">
        <div class="fw-semibold">${esc(f.name)} ${f.student_code ? '<span class="text-secondary fw-normal">' + esc(f.student_code) + '</span>' : ''}</div>
        <div class="small text-secondary">${esc(f.message)}${f.distance !== null && f.state !== 'unknown' ? ` &middot; match ${esc(String(f.confidence))}% (distance ${esc(String(f.distance))})` : ''}</div>
      </div>`).join('');
  }

  // ---- records table
  async function loadRecords() {
    const p = new URLSearchParams();
    [['from', 'fFrom'], ['to', 'fTo'], ['department', 'fDept'], ['status', 'fStatus'], ['q', 'fQ']].forEach(([k, id]) => { const v = $(id).value; if (v) p.set(k, v); });
    try {
      const d = await api('/api/attendance/list?' + p.toString());
      const cols = window.CAN_WRITE ? 9 : 8;
      $('recBody').innerHTML = d.records.length ? d.records.map((r) => `
        <tr><td>${esc(r.student_code)}</td><td>${esc(r.name)}</td><td>${esc(r.department)}</td><td>${esc(r.date)}</td><td>${esc(r.time)}</td>
        <td>${pill(r.status)}</td><td>${esc(r.method)}</td><td>${r.confidence !== null ? esc(String(r.confidence)) : '-'}</td>
        ${window.CAN_WRITE ? `<td class="text-end"><button class="btn btn-sm btn-outline-danger" data-del="${r.id}" aria-label="Delete record"><i class="bi bi-trash"></i></button></td>` : ''}</tr>`).join('')
        : `<tr><td colspan="${cols}" class="text-center text-secondary py-4">No records for these filters.</td></tr>`;
    } catch (e) { toast(e.message, 'danger'); }
  }

  $('filterForm').addEventListener('submit', (e) => { e.preventDefault(); loadRecords(); });
  $('recBody').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-del]'); if (!b) return;
    if (!confirm('Delete this attendance record?')) return;
    try { await api(`/api/attendance/${b.dataset.del}`, { method: 'DELETE' }); toast('Record deleted'); loadRecords(); } catch (err) { toast(err.message, 'danger'); }
  });

  $('mSave')?.addEventListener('click', async () => {
    try {
      const d = await api('/api/attendance/manual', { method: 'POST', body: {
        student_id: $('mStudent').value, date: $('mDate').value, status: $('mStatus').value, note: $('mNote').value } });
      toast(d.message); bootstrap.Modal.getInstance($('manualModal')).hide(); $('mNote').value = ''; loadRecords();
    } catch (e) { toast(e.message, 'danger'); }
  });

  $('startBtn').addEventListener('click', start);
  $('stopBtn').addEventListener('click', stop);
  window.addEventListener('beforeunload', () => cam.stop());
  loadRecords();
})();
