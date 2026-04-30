const Upload = (() => {
  const ALLOWED = ['.mp3', '.mp4', '.m4a', '.wav'];
  const MAX_MB = 500;

  let selectedFile = null;
  let onFileReady = null;

  function init(onReadyCb) {
    onFileReady = onReadyCb;

    const zone  = document.getElementById('drop-zone');
    const input = document.getElementById('file-input');
    const btn   = document.getElementById('select-file-btn');
    const processBtn = document.getElementById('process-btn');

    btn.addEventListener('click', () => input.click());
    zone.addEventListener('click', (e) => {
      if (e.target === btn || btn.contains(e.target)) return;
      input.click();
    });

    input.addEventListener('change', () => {
      if (input.files[0]) handleFile(input.files[0]);
    });

    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    });

    processBtn.addEventListener('click', async () => {
      if (!selectedFile) return;
      processBtn.disabled = true;
      processBtn.textContent = 'Subiendo...';
      try {
        const result = await API.upload(selectedFile);
        onFileReady(result.recording_id, selectedFile.name);
      } catch (err) {
        showToast('Error al subir: ' + err.message, 'error');
        processBtn.disabled = false;
        processBtn.textContent = 'Procesar grabación';
      }
    });
  }

  function handleFile(file) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    const valid = ALLOWED.includes(ext);
    const tooBig = file.size > MAX_MB * 1024 * 1024;

    const zone = document.getElementById('drop-zone');
    const selBox = document.getElementById('selected-file');
    const selName = document.getElementById('selected-file-name');
    const selSize = document.getElementById('selected-file-size');
    const processBtn = document.getElementById('process-btn');

    zone.classList.remove('valid', 'invalid');

    if (!valid) {
      zone.classList.add('invalid');
      showToast(`Formato no soportado: ${ext}. Usa MP3, MP4, M4A o WAV.`, 'error');
      selectedFile = null;
      selBox.classList.remove('show');
      processBtn.classList.add('hidden');
      return;
    }
    if (tooBig) {
      zone.classList.add('invalid');
      showToast(`El archivo supera los ${MAX_MB} MB.`, 'error');
      selectedFile = null;
      selBox.classList.remove('show');
      processBtn.classList.add('hidden');
      return;
    }

    selectedFile = file;
    zone.classList.add('valid');
    selName.textContent = file.name;
    selSize.textContent = formatBytes(file.size);
    selBox.classList.add('show');
    processBtn.classList.remove('hidden');
    processBtn.disabled = false;
    processBtn.textContent = 'Procesar grabación →';
  }

  function formatBytes(b) {
    if (b < 1024) return b + ' B';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB';
    return (b / (1024 * 1024)).toFixed(1) + ' MB';
  }

  return { init };
})();
