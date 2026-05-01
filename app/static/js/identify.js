const Identify = (() => {
  const COLORS = ['spk-color-0','spk-color-1','spk-color-2','spk-color-3',
                  'spk-color-4','spk-color-5','spk-color-6','spk-color-7'];
  const TEXT_COLORS = ['spk-text-0','spk-text-1','spk-text-2','spk-text-3',
                       'spk-text-4','spk-text-5','spk-text-6','spk-text-7'];

  let speakersData = [];
  let assignments = {};
  let knownSpeakers = [];
  let currentAudio = null;
  let recordingId = null;
  let onDoneCb = null;

  async function load(recId, onDone) {
    recordingId = recId;
    onDoneCb = onDone;
    assignments = {};

    try {
      [speakersData, knownSpeakers] = await Promise.all([
        API.getRecordingSpeakers(recId),
        API.getSpeakers(),
      ]);
    } catch (err) {
      showToast('Error al cargar hablantes: ' + err.message, 'error');
      return;
    }

    const container = document.getElementById('speakers-container');
    container.innerHTML = '';

    speakersData.forEach((spk, idx) => {
      const colorIdx = idx % COLORS.length;
      const card = buildSpeakerCard(spk, idx, colorIdx);
      container.appendChild(card);

      const conf = spk.match_confidence || 0;
      if (spk.speaker_id && conf >= 0.85) {
        assignments[spk.raw_label] = {
          raw_label: spk.raw_label,
          speaker_id: spk.speaker_id,
          display_name: spk.display_name,
        };
        markConfirmed(spk.raw_label, spk.display_name);
      }
    });

    updateGenerateBtn();
  }

  function buildSpeakerCard(spk, idx, colorIdx) {
    const conf = spk.match_confidence || 0;
    const confPct = Math.round(conf * 100);
    const talkMin = Math.floor(spk.talk_time / 60);
    const talkSec = Math.round(spk.talk_time % 60);
    const pct = spk.talk_percent || 0;

    const card = document.createElement('div');
    card.className = 'card speaker-card';
    card.dataset.rawLabel = spk.raw_label;

    const initial = spk.display_name ? spk.display_name[0].toUpperCase() : (idx + 1).toString();

    let suggestionHTML = '';
    if (spk.speaker_id && conf >= 0.75 && conf < 0.85) {
      suggestionHTML = `
        <div class="suggestion-box">
          <span>💡 ¿Es <strong>${escHtml(spk.display_name)}</strong>?</span>
          <span class="confidence-med">${confPct}% confianza</span>
          <button class="btn btn-sm btn-primary" onclick="Identify.confirmSuggestion('${spk.raw_label}', ${spk.speaker_id}, '${escHtml(spk.display_name)}')">
            Confirmar
          </button>
        </div>`;
    }

    card.innerHTML = `
      <div class="speaker-card-header">
        <div class="speaker-avatar ${COLORS[colorIdx]}">${escHtml(initial)}</div>
        <div class="speaker-info">
          <div class="speaker-label">Voz ${idx + 1}</div>
          <div class="speaker-stats">Habla el ${pct}% del tiempo (${talkMin}m ${talkSec}s)</div>
        </div>
        ${spk.sample_filename
          ? `<button class="play-btn" id="play-${spk.raw_label}"
               onclick="Identify.togglePlay('${spk.raw_label}', '${spk.sample_filename}')"
               aria-label="Reproducir muestra de voz">▶</button>`
          : ''}
      </div>
      ${suggestionHTML}
      <div class="identity-area" id="identity-area-${spk.raw_label}">
        <div class="identity-input-row">
          <div class="identity-search-wrap">
            <input type="text" class="identity-input"
              id="identity-input-${spk.raw_label}"
              placeholder="Buscar o escribir nombre..."
              autocomplete="off"
              aria-label="Nombre del hablante"
              oninput="Identify.onSearch('${spk.raw_label}', this.value)"
              onkeydown="Identify.onKeyDown(event, '${spk.raw_label}')">
            <div class="identity-dropdown hidden" id="dropdown-${spk.raw_label}"></div>
          </div>
        </div>
      </div>`;

    return card;
  }

  function onSearch(rawLabel, query) {
    const dropdown = document.getElementById(`dropdown-${rawLabel}`);
    if (!query.trim()) {
      dropdown.classList.add('hidden');
      return;
    }

    const q = query.toLowerCase();
    const matches = knownSpeakers.filter(s =>
      s.display_name.toLowerCase().includes(q)
    );

    dropdown.innerHTML = '';
    matches.slice(0, 8).forEach(s => {
      const item = document.createElement('div');
      item.className = 'identity-dropdown-item';
      item.textContent = s.display_name;
      item.addEventListener('mousedown', (e) => {
        e.preventDefault();
        selectSpeaker(rawLabel, s.id, s.display_name);
      });
      dropdown.appendChild(item);
    });

    const newItem = document.createElement('div');
    newItem.className = 'identity-dropdown-item new-profile';
    newItem.textContent = `➕ Crear perfil "${query.trim()}"`;
    newItem.addEventListener('mousedown', (e) => {
      e.preventDefault();
      selectSpeaker(rawLabel, null, query.trim());
    });
    dropdown.appendChild(newItem);

    dropdown.classList.remove('hidden');
  }

  function onKeyDown(event, rawLabel) {
    if (event.key === 'Enter') {
      const input = document.getElementById(`identity-input-${rawLabel}`);
      const val = input.value.trim();
      if (val) selectSpeaker(rawLabel, null, val);
    }
    if (event.key === 'Escape') {
      document.getElementById(`dropdown-${rawLabel}`).classList.add('hidden');
    }
  }

  function selectSpeaker(rawLabel, speakerId, displayName) {
    assignments[rawLabel] = { raw_label: rawLabel, speaker_id: speakerId, display_name: displayName };
    document.getElementById(`dropdown-${rawLabel}`).classList.add('hidden');
    markConfirmed(rawLabel, displayName);
    updateGenerateBtn();
  }

  function markConfirmed(rawLabel, displayName) {
    const area = document.getElementById(`identity-area-${rawLabel}`);
    if (!area) return;
    area.innerHTML = `
      <div class="identity-confirmed">
        <span>✅</span>
        <span>${escHtml(displayName)}</span>
        <button class="btn btn-sm btn-ghost" onclick="Identify.clearAssignment('${rawLabel}')"
          aria-label="Cambiar nombre">Cambiar</button>
      </div>`;
  }

  function clearAssignment(rawLabel) {
    delete assignments[rawLabel];
    const spk = speakersData.find(s => s.raw_label === rawLabel);
    if (!spk) return;
    const idx = speakersData.indexOf(spk);
    const colorIdx = idx % COLORS.length;
    const area = document.getElementById(`identity-area-${rawLabel}`);
    area.innerHTML = `
      <div class="identity-input-row">
        <div class="identity-search-wrap">
          <input type="text" class="identity-input"
            id="identity-input-${rawLabel}"
            placeholder="Buscar o escribir nombre..."
            autocomplete="off"
            aria-label="Nombre del hablante"
            oninput="Identify.onSearch('${rawLabel}', this.value)"
            onkeydown="Identify.onKeyDown(event, '${rawLabel}')">
          <div class="identity-dropdown hidden" id="dropdown-${rawLabel}"></div>
        </div>
      </div>`;
    updateGenerateBtn();
  }

  function confirmSuggestion(rawLabel, speakerId, displayName) {
    selectSpeaker(rawLabel, speakerId, displayName);
  }

  function togglePlay(rawLabel, filename) {
    const btn = document.getElementById(`play-${rawLabel}`);
    if (currentAudio && !currentAudio.paused) {
      currentAudio.pause();
      document.querySelectorAll('.play-btn').forEach(b => {
        b.textContent = '▶';
        b.classList.remove('playing');
      });
      if (btn.dataset.playing === rawLabel) {
        btn.dataset.playing = '';
        return;
      }
    }

    const audio = new Audio(API.sampleUrl(filename));
    currentAudio = audio;
    btn.textContent = '⏹';
    btn.classList.add('playing');
    btn.dataset.playing = rawLabel;

    audio.addEventListener('ended', () => {
      btn.textContent = '▶';
      btn.classList.remove('playing');
    });
    audio.play().catch(() => showToast('No se pudo reproducir la muestra.', 'error'));
  }

  function updateGenerateBtn() {
    const total = speakersData.length;
    const confirmed = Object.keys(assignments).length;
    const btn = document.getElementById('generate-transcript-btn');
    btn.disabled = confirmed < total;
    btn.textContent = confirmed < total
      ? `Identificar todas las voces (${confirmed}/${total})`
      : 'Generar Transcripción →';
  }

  async function generate() {
    const btn = document.getElementById('generate-transcript-btn');
    btn.disabled = true;
    btn.textContent = 'Generando...';
    try {
      const payload = { assignments: Object.values(assignments) };
      await API.identifySpeakers(recordingId, payload);
      onDoneCb(recordingId);
    } catch (err) {
      showToast('Error al generar transcripción: ' + err.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Generar Transcripción →';
    }
  }

  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { load, onSearch, onKeyDown, clearAssignment, confirmSuggestion, togglePlay, generate };
})();
