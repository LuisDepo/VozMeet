const Process = (() => {
  const STAGE_ICONS = {
    'Extrayendo audio':          '🎵',
    'Audio listo':               '✅',
    'Iniciando transcripción':   '🤖',
    'Transcripción completa':    '📝',
    'Iniciando diarización':     '👥',
    'Diarización completa':      '✔️',
    'Fusionando resultados':     '🔀',
    'Generando huellas vocales': '🔊',
    'Comparando con base de datos': '🔍',
    'Listo para identificación': '🎉',
    'error':                     '❌',
    'Advertencia':               '⚠️',
  };

  let _timerInterval = null;
  let _startTime = null;

  function getIcon(stage) {
    for (const [key, icon] of Object.entries(STAGE_ICONS)) {
      if (stage.includes(key)) return icon;
    }
    return '⚙️';
  }

  function fmtElapsed(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    if (h > 0) return `${h}h ${m.toString().padStart(2,'0')}m ${s.toString().padStart(2,'0')}s`;
    if (m > 0) return `${m}m ${s.toString().padStart(2,'0')}s`;
    return `${s}s`;
  }

  function startTimer() {
    stopTimer();
    _startTime = Date.now();
    const el = document.getElementById('elapsed-time');
    if (el) el.textContent = '0s';
    _timerInterval = setInterval(() => {
      if (!_startTime) return;
      const el = document.getElementById('elapsed-time');
      if (el) el.textContent = fmtElapsed(Date.now() - _startTime);
    }, 1000);
  }

  function stopTimer() {
    if (_timerInterval) {
      clearInterval(_timerInterval);
      _timerInterval = null;
    }
  }

  function start(recordingId, filename, onDone, onError) {
    document.getElementById('processing-filename').textContent = filename;
    setStage(5, 'Iniciando...', 'Cargando modelos de IA (puede tardar varios minutos la primera vez)...');
    startTimer();

    API.startProcess(recordingId).catch(err => {
      stopTimer();
      onError(err.message, recordingId);
    });

    const es = API.progressStream(recordingId);

    es.onmessage = (event) => {
      if (!event.data || event.data.trim() === '') return;

      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      if (data.percent === -1) {
        es.close();
        stopTimer();
        onError(data.detail || 'Error desconocido durante el procesamiento.', recordingId);
        return;
      }

      setStage(data.percent, data.stage, data.detail || '');

      if (data.percent === 100) {
        es.close();
        stopTimer();
        setTimeout(() => onDone(recordingId), 600);
      }
    };

    es.onerror = () => {
      es.close();
      setTimeout(() => {
        const es2 = API.progressStream(recordingId);
        es2.onmessage = es.onmessage;
        es2.onerror = () => es2.close();
      }, 2000);
    };
  }

  function setStage(percent, stage, detail) {
    const pct = Math.max(0, Math.min(100, percent));
    document.getElementById('progress-fill').style.width = pct + '%';
    document.getElementById('progress-percent').textContent = pct + '%';
    document.getElementById('stage-icon').textContent = getIcon(stage);
    document.getElementById('stage-name').textContent = stage;
    document.getElementById('stage-detail').textContent = detail;
  }

  return { start };
})();
