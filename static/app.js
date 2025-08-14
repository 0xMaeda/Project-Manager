// static/app.js (robust progress updates)

// ---- Drag & Drop Kanban ----
let draggedId = null;

function dragTask(e){
  draggedId = e.currentTarget.dataset.task;
}

async function dropTask(e){
  const state = e.currentTarget.dataset.state;
  const column = e.currentTarget.querySelector('.list');
  const card = document.querySelector(`[data-task="${draggedId}"]`);
  if(column && card){
    column.prepend(card);
  }

  try{
    await fetch(`/tasks/${draggedId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ state })
    });
  }catch(err){
    console.error('PATCH failed', err);
  }

  refreshWidgets();
  refreshWorkload();
  refreshProgress();
}

// ---- Socket.IO Live Updates ----
const socket = typeof io !== 'undefined' ? io() : null;
if (socket){
  socket.on('task_updated', ({id, state}) => {
    // Move the card if it exists on this page (dashboard)
    const card = document.querySelector(`[data-task="${id}"]`);
    if(card && state){
      const col = document.querySelector(`.col[data-state="${state}"] .list`);
      if(col){ col.prepend(card); }
    }
    // Always refresh widgets and project progress (affects Projects tab too)
    refreshWidgets();
  refreshWorkload();
    refreshProgress();
  });
}

// ---- Widgets (Workload / Due Soon / Blocked) ----
async function refreshWidgets(){
  try{
    // Only present on dashboard
    const aside = document.getElementById('rightAside');
    if(!aside) return;
    const qs = location.search || '';
    const res = await fetch(`/dashboard/widgets${qs}${qs ? '&' : '?'}ts=${Date.now()}`);
    const html = await res.text();
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    const freshAside = wrapper.querySelector('#rightAside');
    if(freshAside) aside.replaceWith(freshAside);
  }catch(e){
    // ok on pages without widgets
  }
}

// ---- Project Progress (Dashboard + Projects tab) ----
async function refreshProgress(){
  try{
    // Progress card exists on dashboard; on Projects tab, only per-row bars exist
    const res = await fetch(`/dashboard/progress.json?ts=${Date.now()}`);
    if(!res.ok) return;
    const items = await res.json();
    for(const p of items){
      // Update dashboard card if present
      const barDash = document.getElementById(`bar-${p.id}`);
      const txtDash = document.getElementById(`txt-${p.id}`);
      if(barDash) barDash.style.width = `${p.pct}%`;
      if(txtDash) txtDash.textContent = `${p.done}/${p.total} (${p.pct}%)`;

      // Update Projects table if present
      const barProj = document.getElementById(`proj-bar-${p.id}`);
      const txtProj = document.getElementById(`proj-txt-${p.id}`);
      if(barProj) barProj.style.width = `${p.pct}%`;
      if(txtProj) txtProj.textContent = `${p.done}/${p.total} (${p.pct}%)`;
    }
  }catch(e){
    console.error('refreshProgress error', e);
  }
}

// ---- Kick off on page load, focus, and as a gentle fallback ----
document.addEventListener('DOMContentLoaded', () => {
  refreshProgress();      // initial
  refreshWidgets();
  refreshWorkload();       // if on dashboard
  // Fallback refresher (5s)
  setInterval(refreshProgress, 5000);
});

document.addEventListener('visibilitychange', () => {
  if(document.visibilityState === 'visible'){
    refreshProgress();
    refreshWidgets();
  refreshWorkload();
  }
});

// Expose for inline handlers
window.dragTask = dragTask;
window.dropTask = dropTask;


async function refreshWorkload(){
  try{
    const qs = location.search || '';
    const res = await fetch(`/dashboard/workload${qs}${qs ? '&' : '?'}ts=${Date.now()}`);
    if(!res.ok) return;
    const html = await res.text();
    const left = document.getElementById('leftAside');
    if(left){
      const wrap = document.createElement('div');
      wrap.innerHTML = html;
      const fresh = wrap.querySelector('#leftAside');
      if(fresh) left.replaceWith(fresh);
    }
  }catch(e){
    console.error('refreshWorkload error', e);
  }
}
