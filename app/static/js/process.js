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

  function getIcon(stage) {
    for (const [key, icon] of Object.entries(STAGE_ICONS)) {
      if (stage.includes(key)) return icon;
    }
    return '⚙️';
  }

  function start(recordingId, filename, onDone, onError) {
    document.getElementById('processing-filename').textContent = filename;
    setStage(5, 'Iniciando...', 'Cargando modelos de IA (puede tardar varios minutos la primera vez)...');

    API.startProcess(recordingId).catch(err => onError(err.message));

    const es = API.progressStream(recordingId);

    es.onmessage = (event) => {
      // Ignore SSE comment lines (keepalives start with ':' but EventSource
      // only fires onmessage for 'data:' lines, so this is just a safety check)
      if (!event.data || event.data.trim() === '') return;

      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // ignore malformed lines
      }

      if (data.percent === -1) {
        es.close();
        onError(data.detail || 'Error desconocido durante el procesamiento.');
        return;
      }

      setStage(data.percent, data.stage, data.detail || '');

      if (data.percent === 100) {
        es.close();
        setTimeout(() => onDone(recordingId), 600);
      }
    };

    es.onerror = () => {
      // Don't treat a dropped SSE connection as a fatal error — the pipeline
      // may still be running. Reconnect silently after a short delay.
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
