// ─── View router ──────────────────────────────────────────────────────────────
const VIEWS = ['upload', 'processing', 'identify', 'transcript', 'history', 'profiles'];

function showView(name) {
  VIEWS.forEach(v => {
    const el = document.getElementById(`view-${v}`);
    if (el) el.classList.toggle('hidden', v !== name);
  });
  document.querySelectorAll('.sidebar-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === name);
  });
}

// ─── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

// ─── History view ──────────────────────────────────────────────────────────────
async function loadHistory() {
  const container = document.getElementById('history-list');
  container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><div>Cargando...</div></div>';
  try {
    const recordings = await API.getRecordings();
    if (!recordings.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📂</div>
          <div class="empty-state-title">Sin grabaciones</div>
          <div class="empty-state-desc">Procesa tu primera grabación para verla aquí</div>
        </div>`;
      return;
    }

    container.innerHTML = '';
    recordings.forEach(rec => {
      const row = document.createElement('div');
      row.className = 'recording-row';

      const statusBadge = {
        done: '<span class="badge badge-green">Listo</span>',
        processing: '<span class="badge badge-blue">Procesando</span>',
        error: '<span class="badge badge-red">Error</span>',
        identifying: '<span class="badge badge-orange">Pendiente</span>',
        uploaded: '<span class="badge badge-gray">Subido</span>',
      }[rec.status] || `<span class="badge badge-gray">${rec.status}</span>`;

      const dur = rec.duration_seconds ? fmtDurationShort(rec.duration_seconds) : '—';
      const date = rec.created_at ? new Date(rec.created_at).toLocaleDateString('es-ES') : '—';
      const spks = rec.speaker_count ? `${rec.speaker_count} voces` : '';

      row.innerHTML = `
        <div class="recording-icon">🎙️</div>
        <div class="recording-info">
          <div class="recording-name">${escHtml(rec.filename)}</div>
          <div class="recording-meta">${date} · ${dur}${spks ? ' · ' + spks : ''} · ${rec.language_detected || ''}</div>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          ${statusBadge}
        </div>
        <div class="recording-actions">
          ${rec.status === 'done' || rec.status === 'identifying'
            ? `<button class="btn btn-sm btn-primary" onclick="openRecording(${rec.id}, '${rec.status}')" aria-label="Ver transcripción">Ver</button>`
            : ''}
          <button class="btn btn-sm btn-danger" onclick="deleteRecording(${rec.id})" aria-label="Eliminar grabación">🗑</button>
        </div>`;
      container.appendChild(row);
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">❌</div><div>${escHtml(err.message)}</div></div>`;
  }
}

async function openRecording(id, status) {
  if (status === 'identifying') {
    showView('identify');
    await Identify.load(id, (recId) => {
      showView('transcript');
      Transcript.load(recId);
    });
  } else {
    showView('transcript');
    await Transcript.load(id);
  }
}

async function deleteRecording(id) {
  if (!confirm('¿Eliminar esta grabación y su transcripción?')) return;
  try {
    await API.deleteRecording(id);
    showToast('Grabación eliminada.', 'success');
    loadHistory();
  } catch (err) {
    showToast('Error al eliminar: ' + err.message, 'error');
  }
}

// ─── Profiles view ─────────────────────────────────────────────────────────────
async function loadProfiles() {
  const container = document.getElementById('profiles-list');
  container.innerHTML = '<div class="empty-state"><div>Cargando...</div></div>';
  try {
    const speakers = await API.getSpeakers();
    if (!speakers.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">👤</div>
          <div class="empty-state-title">Sin perfiles de voz</div>
          <div class="empty-state-desc">Los perfiles se crean automáticamente al procesar grabaciones</div>
        </div>`;
      return;
    }

    const COLORS = ['spk-color-0','spk-color-1','spk-color-2','spk-color-3',
                    'spk-color-4','spk-color-5','spk-color-6','spk-color-7'];
    container.innerHTML = '';
    speakers.forEach((s, idx) => {
      const row = document.createElement('div');
      row.className = 'profile-row';
      const colorClass = COLORS[idx % COLORS.length];
      const initial = s.display_name[0].toUpperCase();
      const date = s.created_at ? new Date(s.created_at).toLocaleDateString('es-ES') : '—';

      row.innerHTML = `
        <div class="profile-avatar-sm ${colorClass}">${escHtml(initial)}</div>
        <div class="profile-info">
          <div class="profile-name">${escHtml(s.display_name)}</div>
          <div class="profile-meta">${s.recording_count} grabación(es) · desde ${date} · ${s.embedding_count} muestra(s)</div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-sm btn-secondary" onclick="editProfile(${s.id}, '${escHtml(s.display_name)}')" aria-label="Editar nombre">✏️ Editar</button>
          <button class="btn btn-sm btn-danger" onclick="deleteProfile(${s.id})" aria-label="Eliminar perfil">🗑</button>
        </div>`;
      container.appendChild(row);
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><div>${escHtml(err.message)}</div></div>`;
  }
}

async function editProfile(id, currentName) {
  const newName = prompt('Nuevo nombre para este perfil:', currentName);
  if (!newName || newName.trim() === currentName) return;
  try {
    await API.updateSpeaker(id, { display_name: newName.trim() });
    showToast('Perfil actualizado.', 'success');
    loadProfiles();
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

async function deleteProfile(id) {
  if (!confirm('¿Eliminar este perfil de voz? Esta acción no se puede deshacer.')) return;
  try {
    await API.deleteSpeaker(id);
    showToast('Perfil eliminado.', 'success');
    loadProfiles();
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

// ─── Helpers ───────────────────────────────────────────────────────────────────
function fmtDurationShort(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── Bootstrap ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Sidebar navigation
  document.querySelectorAll('.sidebar-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      showView(view);
      if (view === 'history') loadHistory();
      if (view === 'profiles') loadProfiles();
    });
  });

  // Upload flow
  Upload.init((recordingId, filename) => {
    showView('processing');
    Process.start(recordingId, filename,
      (recId) => {
        showView('identify');
        Identify.load(recId, (id) => {
          showView('transcript');
          Transcript.load(id);
        });
      },
      (errMsg) => {
        showToast('Error de procesamiento: ' + errMsg, 'error');
        showView('upload');
      }
    );
  });

  // Generate transcript button
  document.getElementById('generate-transcript-btn').addEventListener('click', () => {
    Identify.generate();
  });

  // Transcript search / filter
  document.getElementById('transcript-search').addEventListener('input', () => Transcript.onSearch());
  document.getElementById('speaker-filter').addEventListener('change', () => Transcript.onFilter());

  // Start on upload view
  showView('upload');
});
