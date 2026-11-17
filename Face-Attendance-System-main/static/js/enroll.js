/* Face enrolment for the registration page and the re-capture panel */
(function () {
  const cfg = window.ENROLL;
  const $ = (id) => document.getElementById(id);
  const cam = new Camera($('video'));
  const photos = [];
  const prompts = ['Look straight at the camera', 'Turn slightly left', 'Turn slightly right', 'Tilt your head up a little', 'Smile and look straight'];

  function refresh() {
    const consent = $('consent').checked;
    $('photoCount').textContent = photos.length;
    $('startBtn').disabled = !consent;
    $('autoBtn').disabled = !(consent && cam.active);
    $('snapBtn').disabled = !(consent && cam.active);
    $('clearBtn').disabled = photos.length === 0;
    if (cfg.mode === 'recapture') $('saveBtn').disabled = !(consent && photos.length >= cfg.minImages);
  }
  function addPhoto(dataUrl) {
    photos.push(dataUrl);
    const img = document.createElement('img'); img.src = dataUrl; img.alt = `Captured photo ${photos.length}`;
    $('thumbs').appendChild(img);
    refresh();
  }

  $('consent').addEventListener('change', () => {
    if (!$('consent').checked && cam.active) { cam.stop(); $('camHint').style.display = ''; }
    refresh();
  });
  $('startBtn').addEventListener('click', async () => {
    try { await cam.start(); $('camHint').style.display = 'none'; refresh(); }
    catch (e) { toast(e.message, 'danger'); }
  });
  $('snapBtn').addEventListener('click', () => { const d = cam.capture(640, 0.9); if (d) addPhoto(d); });
  $('clearBtn').addEventListener('click', () => { photos.length = 0; $('thumbs').innerHTML = ''; refresh(); });
  $('autoBtn').addEventListener('click', async () => {
    $('autoBtn').disabled = true;
    for (let i = 0; i < 5; i++) {
      $('camHint').style.display = 'flex'; $('camHint').textContent = prompts[i];
      await new Promise((r) => setTimeout(r, 1400));
      $('camHint').style.display = 'none';
      const d = cam.capture(640, 0.9); if (d) addPhoto(d);
      await new Promise((r) => setTimeout(r, 300));
    }
    refresh();
  });

  async function save() {
    const btn = $('saveBtn'); btn.disabled = true;
    const consent = $('consent').checked;
    const body = cfg.mode === 'create'
      ? { name: $('name').value.trim(), student_code: $('student_code').value.trim(), email: $('email').value.trim(),
          department_id: $('department_id').value || null, consent, images: consent ? photos : [] }
      : { consent, images: photos };
    if (cfg.mode === 'create' && consent && photos.length < cfg.minImages) {
      toast(`Capture at least ${cfg.minImages} photos, or untick consent to register without face data.`, 'warning');
      btn.disabled = false; return;
    }
    try {
      btn.textContent = 'Saving...';
      const d = await api(cfg.endpoint, { method: 'POST', body });
      toast(d.message);
      cam.stop();
      setTimeout(() => { window.location = d.redirect; }, 900);
    } catch (e) { toast(e.message, 'danger'); btn.disabled = false; btn.textContent = cfg.mode === 'create' ? 'Register person' : 'Save new face data'; }
  }
  $('saveBtn').addEventListener('click', save);
  window.addEventListener('beforeunload', () => cam.stop());
  refresh();
})();
