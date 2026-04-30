const Transcript = (() => {
  const SPK_COLORS = ['spk-text-0','spk-text-1','spk-text-2','spk-text-3',
                      'spk-text-4','spk-text-5','spk-text-6','spk-text-7'];

  let transcriptData = null;
  let speakerColorMap = {};
  let allSegments = [];

  async function load(recordingId) {
    try {
      transcriptData = await API.getTranscript(recordingId);
    } catch (err) {
      showToast('Error al cargar transcripción: ' + err.message, 'error');
      return;
    }

    speakerColorMap = {};
    const uniqueSpeakers = [...new Set(transcriptData.segments.map(s => s.speaker))];
    uniqueSpeakers.forEach((name, i) => {
      speakerColorMap[name] = SPK_COLORS[i % SPK_COLORS.length];
    });

    allSegments = transcriptData.segments;

    const rec = transcriptData.recording;
    document.getElementById('transcript-title').textContent = rec.filename || 'Transcripción';
    document.getElementById('transcript-meta').textContent =
      `${transcriptData.participants.join(', ')} · ${fmtDuration(rec.duration_seconds || 0)} · ${rec.language_detected || ''}`;

    populateFilter(transcriptData.participants);
    renderSegments(allSegments, '');
    setupExportBtns(recordingId);
  }

  function populateFilter(participants) {
    const sel = document.getElementById('speaker-filter');
    sel.innerHTML = '<option value="">Todos los participantes</option>';
    participants.forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  }

  function renderSegments(segs, searchQuery) {
    const container = document.getElementById('segments-container');
    container.innerHTML = '';

    if (!segs.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔍</div><div class="empty-state-title">Sin resultados</div></div>';
      return;
    }

    segs.forEach(seg => {
      const div = document.createElement('div');
      div.className = 'segment';

      const colorClass = speakerColorMap[seg.speaker] || 'spk-text-0';
      let textContent = escHtml(seg.text);
      if (searchQuery) {
        const re = new RegExp(escRegex(searchQuery), 'gi');
        textContent = textContent.replace(re, m => `<mark class="highlight">${m}</mark>`);
      }

      div.innerHTML = `
        <div class="segment-ts">${fmtTs(seg.start)}</div>
        <div class="segment-speaker ${colorClass}">${escHtml(seg.speaker)}</div>
        <div class="segment-text">${textContent}</div>`;
      container.appendChild(div);
    });
  }

  function onSearch() {
    const q = document.getElementById('transcript-search').value.trim();
    const spk = document.getElementById('speaker-filter').value;
    filterAndRender(q, spk);
  }

  function onFilter() {
    const q = document.getElementById('transcript-search').value.trim();
    const spk = document.getElementById('speaker-filter').value;
    filterAndRender(q, spk);
  }

  function filterAndRender(q, spk) {
    let segs = allSegments;
    if (spk) segs = segs.filter(s => s.speaker === spk);
    if (q) {
      const ql = q.toLowerCase();
      segs = segs.filter(s => s.text.toLowerCase().includes(ql) || s.speaker.toLowerCase().includes(ql));
    }
    renderSegments(segs, q);
  }

  function setupExportBtns(recordingId) {
    ['txt', 'md', 'json'].forEach(fmt => {
      const btn = document.getElementById(`export-${fmt}-btn`);
      if (btn) {
        btn.onclick = () => {
          const a = document.createElement('a');
          a.href = API.exportUrl(recordingId, fmt);
          a.click();
        };
      }
    });
  }

  function fmtTs(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h) return `${pad(h)}:${pad(m)}:${pad(s)}`;
    return `${pad(m)}:${pad(s)}`;
  }

  function fmtDuration(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h) return `${h}h ${m}m`;
    return `${m}m ${s}s`;
  }

  function pad(n) { return String(n).padStart(2, '0'); }

  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function escRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  return { load, onSearch, onFilter };
})();
