const API = {
  base: '',

  async request(method, path, body, isFormData = false) {
    const opts = { method };
    if (body) {
      if (isFormData) {
        opts.body = body;
      } else {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
      }
    }
    const res = await fetch(this.base + path, opts);
    if (!res.ok) {
      let detail = `Error ${res.status}`;
      try { const j = await res.json(); detail = j.detail || detail; } catch {}
      throw new Error(detail);
    }
    const ct = res.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) return res.json();
    if (ct.includes('text/event-stream')) return res;
    return res.blob();
  },

  upload(file) {
    const fd = new FormData();
    fd.append('file', file);
    return this.request('POST', '/api/upload', fd, true);
  },

  startProcess(id)             { return this.request('POST', `/api/process/${id}`); },
  getRecordingSpeakers(id)     { return this.request('GET', `/api/recordings/${id}/speakers`); },
  identifySpeakers(id, data)   { return this.request('POST', `/api/recordings/${id}/identify`, data); },
  getTranscript(id)            { return this.request('GET', `/api/recordings/${id}/transcript`); },
  getRecordings()              { return this.request('GET', '/api/recordings'); },
  deleteRecording(id)          { return this.request('DELETE', `/api/recordings/${id}`); },
  getSpeakers()                { return this.request('GET', '/api/speakers'); },
  updateSpeaker(id, data)      { return this.request('PUT', `/api/speakers/${id}`, data); },
  deleteSpeaker(id)            { return this.request('DELETE', `/api/speakers/${id}`); },

  exportUrl(id, format)        { return `/api/export/${id}?format=${format}`; },
  sampleUrl(filename)          { return `/api/audio/sample/${filename}`; },

  progressStream(id) {
    return new EventSource(`/api/process/${id}/progress`);
  },
};
