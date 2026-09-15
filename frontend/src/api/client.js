const API_BASE = '/api';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetch('/upload', { method: 'POST', body: formData });
}

export async function getVolumeInfo() {
  return apiFetch('/volume');
}

export async function getSliceAsBase64(view, sliceIndex, windowCenter, windowWidth) {
  const params = new URLSearchParams({
    view,
    slice_index: sliceIndex,
    window_center: windowCenter,
    window_width: windowWidth,
  });
  return apiFetch(`/slice/${view}/${sliceIndex}/base64?${params}`);
}

export async function getSegmentationSliceAsBase64(view, sliceIndex) {
  return apiFetch(`/segmentation/${view}/${sliceIndex}/base64`);
}

export async function drawSegmentation(view, sliceIndex, payload) {
  return apiFetch('/segmentation/draw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ view, slice_index: sliceIndex, ...payload }),
  });
}

export async function performMeasurement(view, sliceIndex, point1, point2) {
  return apiFetch('/measure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ view, slice_index: sliceIndex, point1, point2 }),
  });
}

export async function runSegmentation(organs = [], sectors = []) {
  const payload = {
    organs: Array.isArray(organs) ? organs : [],
    sectors: Array.isArray(sectors) ? sectors : [],
  };
  return apiFetch('/segmentation/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
export async function toggleMotionRestoration() {
  return apiFetch('/restore/toggle', { method: 'POST' });
}

export async function getVolumeData() {
  return apiFetch('/volume/data');
}

export async function getMontageAsBase64(view, windowCenter, windowWidth) {
  const params = new URLSearchParams({
    window_center: windowCenter,
    window_width: windowWidth,
  });
  return apiFetch(`/slices/montage/${view}/base64?${params}`);
}

export async function askAIReportStream(messages, model = 'openrouter/free', onChunk, onDone, onError) {
  try {
    const res = await fetch(`${API_BASE}/ai/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, model }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      onError(err.detail || 'Request failed');
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') {
            onDone();
            return;
          }
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) {
              onError(parsed.error);
              return;
            }
            const content = parsed.choices?.[0]?.delta?.content;
            if (content) onChunk(content);
          } catch {}
        }
      }
    }
    onDone();
  } catch (err) {
    onError(err.message);
  }
}
