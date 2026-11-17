/* Shared helpers: CSRF-aware fetch, toasts, theme, menu, notifications */
const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || '';

async function api(url, { method = 'GET', body } = {}) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF, 'Accept': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (res.status === 401) { window.location = '/login'; throw new Error('Please log in.'); }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function toast(message, type = 'success') {
  const box = document.getElementById('toasts');
  if (!box) return;
  const el = document.createElement('div');
  el.className = `toast align-items-center text-bg-${type} border-0`;
  el.setAttribute('role', 'status');
  el.innerHTML = '<div class="d-flex"><div class="toast-body"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>';
  el.querySelector('.toast-body').textContent = message;   // textContent: no HTML injection
  box.appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 4000 });
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function pill(status) { return `<span class="st st-${esc(status)}">${esc(status)}</span>`; }

// Theme
(function () {
  const btn = document.getElementById('themeBtn');
  if (!btn) return;
  const icon = btn.querySelector('i');
  const apply = (t) => {
    document.documentElement.setAttribute('data-bs-theme', t);
    localStorage.setItem('theme', t);
    icon.className = t === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
    window.dispatchEvent(new Event('themechange'));
  };
  icon.className = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
  btn.addEventListener('click', () => apply(document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark'));
})();

// Mobile menu
document.getElementById('menuBtn')?.addEventListener('click', () => document.getElementById('sidebar').classList.toggle('open'));
document.addEventListener('click', (e) => {
  const sb = document.getElementById('sidebar');
  if (sb && sb.classList.contains('open') && !sb.contains(e.target) && !e.target.closest('#menuBtn')) sb.classList.remove('open');
});

// Real-time notifications: poll for new attendance records
(function () {
  if (!document.body.dataset.auth) return;
  let lastId = null, count = 0;
  const badge = document.getElementById('bellCount');
  document.getElementById('bellBtn')?.addEventListener('click', () => { count = 0; badge.classList.add('d-none'); });
  async function poll() {
    if (document.hidden) return;
    try {
      const d = await api(lastId === null ? '/api/attendance/recent' : `/api/attendance/recent?after=${lastId}`);
      if (lastId !== null) {
        d.records.forEach((r) => {
          toast(`${r.name} marked ${r.status} at ${r.time} (${r.method})`, r.status === 'Late' ? 'warning' : 'success');
          count++;
        });
        if (count) { badge.textContent = count; badge.classList.remove('d-none'); }
        if (d.records.length) window.dispatchEvent(new CustomEvent('attendance-new'));
      }
      lastId = d.last_id;
    } catch (e) { /* ignore network blips */ }
  }
  poll();
  setInterval(poll, 5000);
})();
