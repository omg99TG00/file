const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const menuBtn = $('#menuBtn');
const sidePanel = $('#sidePanel');
const overlay = $('#overlay');
let currentDep = null;
let timerIv = null;

function openMenu() {
  sidePanel.hidden = false;
  overlay.hidden = false;
}
function closeMenu() {
  sidePanel.hidden = true;
  overlay.hidden = true;
}
menuBtn.addEventListener('click', () => (sidePanel.hidden ? openMenu() : closeMenu()));
overlay.addEventListener('click', closeMenu);

$$('.side-link').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('.side-link').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    ['deployments', 'support', 'info'].forEach((t) => {
      const el = document.getElementById('tab-' + t);
      if (el) el.hidden = t !== tab;
    });
    closeMenu();
    if (tab === 'deployments') loadDeployment();
  });
});

$('#logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  location.href = '/';
});

async function loadDeployment() {
  const res = await fetch('/api/deployment');
  const data = await res.json();
  const empty = $('#depEmpty');
  const list = $('#depList');
  const detail = $('#depDetail');
  list.innerHTML = '';
  detail.hidden = true;
  currentDep = data.deployment;
  if (!data.deployment) {
    empty.hidden = false;
    $('#newDepBtn').disabled = false;
    return;
  }
  empty.hidden = true;
  $('#newDepBtn').disabled = true;
  const d = data.deployment;
  const card = document.createElement('div');
  card.className = 'dep-card';
  card.innerHTML = `<div><strong>${escapeHtml(d.name)}</strong><div class="muted">Channel ${escapeHtml(d.channel_id)}</div></div>
    <span class="pill ${d.farm_on || d.live ? 'on' : 'off'}">${d.live ? 'FARMING' : d.farm_on ? 'SCHEDULED' : 'IDLE'}</span>`;
  card.addEventListener('click', () => showDetail(d));
  list.appendChild(card);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showDetail(d) {
  const detail = $('#depDetail');
  detail.hidden = false;
  const cdLocked = d.cooldown_ends_at && new Date(d.cooldown_ends_at) > new Date();
  detail.innerHTML = `
    <h3>${escapeHtml(d.name)}</h3>
    <p class="muted">Channel <code>${escapeHtml(d.channel_id)}</code></p>
    <div class="setting-row">
      <span>HuntBot</span>
      <button class="toggle ${d.huntbot ? 'on' : ''}" id="huntToggle" aria-label="HuntBot"></button>
    </div>
    <div class="setting-row">
      <span>Speed</span>
      <select id="speedSel">
        ${['efficient','fast','durable','lifetime'].map(s => `<option value="${s}" ${d.speed===s?'selected':''}>${s}</option>`).join('')}
      </select>
    </div>
    <div class="setting-row">
      <span>Farm <span class="timer" id="farmTimer"></span></span>
      <button class="toggle ${d.live || d.farm_on ? 'on' : ''}" id="farmToggle" ${cdLocked ? 'disabled' : ''} aria-label="Farm"></button>
    </div>
    <p class="error" id="farmErr" hidden></p>
    <div class="row">
      <button class="btn danger" id="deleteBtn">DELETE DEPLOYMENT</button>
    </div>`;

  $('#huntToggle').addEventListener('click', async () => {
    const on = !$('#huntToggle').classList.contains('on');
    const r = await fetch('/api/deployment/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ huntbot: on }),
    });
    const j = await r.json();
    if (j.ok) $('#huntToggle').classList.toggle('on', on);
  });

  $('#speedSel').addEventListener('change', async (e) => {
    await fetch('/api/deployment/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speed: e.target.value }),
    });
  });

  $('#farmToggle').addEventListener('click', async () => {
    const wantOn = !$('#farmToggle').classList.contains('on');
    const err = $('#farmErr');
    err.hidden = true;
    const r = await fetch('/api/deployment/farm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on: wantOn }),
    });
    const j = await r.json();
    if (!j.ok) {
      err.textContent = j.error || 'Could not change farm state.';
      err.hidden = false;
      return;
    }
    await loadDeployment();
    if (currentDep) showDetail(currentDep);
  });

  $('#deleteBtn').addEventListener('click', () => {
    $('#modalDel').hidden = false;
  });

  if (timerIv) clearInterval(timerIv);
  tickTimer(d);
  timerIv = setInterval(() => tickTimer(currentDep || d), 1000);
}

function tickTimer(d) {
  const el = $('#farmTimer');
  if (!el || !d) return;
  const now = Date.now();
  if (d.farm_ends_at && new Date(d.farm_ends_at) > now) {
    const left = Math.max(0, Math.floor((new Date(d.farm_ends_at) - now) / 1000));
    el.textContent = '· ' + fmt(left) + ' left';
  } else if (d.cooldown_ends_at && new Date(d.cooldown_ends_at) > now) {
    const left = Math.max(0, Math.floor((new Date(d.cooldown_ends_at) - now) / 1000));
    el.textContent = '· cooldown ' + fmt(left);
  } else {
    el.textContent = '';
  }
}

function fmt(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

// modal new
$('#newDepBtn').addEventListener('click', () => {
  $('#modalErr').hidden = true;
  $('#tokInput').value = '';
  $('#chInput').value = '';
  $('#modalNew').hidden = false;
});
$('#modalCancel').addEventListener('click', () => ($('#modalNew').hidden = true));
$('#modalAdd').addEventListener('click', async () => {
  const err = $('#modalErr');
  err.hidden = true;
  const btn = $('#modalAdd');
  btn.disabled = true;
  btn.textContent = 'Validating…';
  try {
    const r = await fetch('/api/deployment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token: $('#tokInput').value,
        channel_id: $('#chInput').value,
      }),
    });
    const j = await r.json();
    if (!j.ok) {
      err.textContent = j.error || 'Failed.';
      err.hidden = false;
    } else {
      $('#modalNew').hidden = true;
      await loadDeployment();
    }
  } catch (e) {
    err.textContent = 'Network error.';
    err.hidden = false;
  }
  btn.disabled = false;
  btn.textContent = 'ADD WORKER';
});

$('#delCancel').addEventListener('click', () => ($('#modalDel').hidden = true));
$('#delConfirm').addEventListener('click', async () => {
  await fetch('/api/deployment', { method: 'DELETE' });
  $('#modalDel').hidden = true;
  await loadDeployment();
});

loadDeployment();
