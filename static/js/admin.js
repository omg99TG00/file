const $ = (s) => document.querySelector(s);

$('#logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  location.href = '/';
});

async function loadSlots() {
  const r = await fetch('/api/admin/slots');
  const j = await r.json();
  $('#slotPill').textContent = `${j.count} / ${j.cap}`;
  const pauseBtn = $('#pauseBtn');
  pauseBtn.textContent = j.global_pause ? 'Resume global' : 'Global pause';
  pauseBtn.dataset.paused = j.global_pause ? '1' : '0';
  const list = $('#slotList');
  list.innerHTML = '';
  if (!j.active.length) {
    list.innerHTML = '<p class="muted">No active farms.</p>';
    return;
  }
  j.active.forEach((s) => {
    const el = document.createElement('div');
    el.className = 'dep-card';
    el.innerHTML = `<div><strong>${s.name || s.deployment_id}</strong>
      <div class="muted">${s.username || ''} · ends ${s.ends_at || ''}</div></div>
      <button class="btn danger sm" data-id="${s.deployment_id}">Force stop</button>`;
    el.querySelector('button').addEventListener('click', async () => {
      await fetch('/api/admin/force-stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deployment_id: s.deployment_id, skip_cooldown: false }),
      });
      loadSlots();
      loadUsers();
    });
    list.appendChild(el);
  });
}

$('#refreshSlots').addEventListener('click', loadSlots);
$('#pauseBtn').addEventListener('click', async () => {
  const paused = $('#pauseBtn').dataset.paused === '1';
  await fetch('/api/admin/global-pause', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pause: !paused, stop_all: !paused }),
  });
  loadSlots();
});

async function loadUsers() {
  const r = await fetch('/api/admin/users');
  const j = await r.json();
  const wrap = $('#userList');
  let html = `<table><thead><tr>
    <th>User</th><th>Role</th><th>Status</th><th>Deployment</th><th>Actions</th>
  </tr></thead><tbody>`;
  (j.users || []).forEach((u) => {
    const d = u.deployment;
    html += `<tr>
      <td>${u.username}</td>
      <td>${u.role}</td>
      <td>${u.disabled ? 'disabled' : 'active'}</td>
      <td>${d ? `${d.name} · farm ${d.farm_on ? 'on' : 'off'} · ${d.speed}` : '—'}</td>
      <td>
        <button class="btn sm ghost" data-act="toggle" data-id="${u.id}" data-dis="${u.disabled ? 0 : 1}">${u.disabled ? 'Enable' : 'Disable'}</button>
        ${d ? `<button class="btn sm danger" data-act="deldep" data-did="${d.id}">Del dep</button>
        <button class="btn sm ghost" data-act="cd" data-did="${d.id}">Clear CD</button>` : ''}
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
  wrap.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const act = btn.dataset.act;
      if (act === 'toggle') {
        await fetch('/api/admin/user-disable', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: Number(btn.dataset.id), disabled: btn.dataset.dis === '1' }),
        });
      } else if (act === 'deldep') {
        await fetch('/api/admin/force-delete-deployment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ deployment_id: Number(btn.dataset.did) }),
        });
      } else if (act === 'cd') {
        await fetch('/api/admin/clear-cooldown', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ deployment_id: Number(btn.dataset.did) }),
        });
      }
      loadUsers();
      loadSlots();
    });
  });
}

async function loadAudit() {
  const r = await fetch('/api/admin/audit');
  const j = await r.json();
  $('#auditList').innerHTML = (j.logs || [])
    .map((l) => `<div><code>${l.created_at || ''}</code> · <strong>${l.actor || ''}</strong> · ${l.action} · ${l.detail || ''}</div>`)
    .join('');
}

loadSlots();
loadUsers();
loadAudit();
setInterval(loadSlots, 15000);
