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
    setStage(5, 'Iniciando...', '');

    API.startProcess(recordingId).catch(err => onError(err.message));

    const es = API.progressStream(recordingId);

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.percent === -1) {
        es.close();
        onError(data.detail || 'Error desconocido durante el procesamiento.');
        return;
      }
      if (data.percent === -2) {
        es.close();
        onError('Tiempo de espera agotado.');
        return;
      }

      setStage(data.percent, data.stage, data.detail || '');

      if (data.percent === 100) {
        es.close();
        setTimeout(() => onDone(recordingId), 600);
      }
    };

    es.onerror = () => {
      es.close();
      onError('Se perdió la conexión con el servidor.');
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
