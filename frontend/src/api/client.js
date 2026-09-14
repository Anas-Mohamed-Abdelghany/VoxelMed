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
  const payload = Array.isArray(organs)
    ? { organs, sectors }
    : { organs: [], sectors: [] };
  // Both /api/segment and /api/segmentation/run will now work
  const { data } = await api.post('/api/segmentation/run', payload);
  return data;
}
export async function toggleMotionRestoration() {
  return apiFetch('/restore/toggle', { method: 'POST' });
}

export async function getVolumeData() {
  return apiFetch('/volume/data');
}
