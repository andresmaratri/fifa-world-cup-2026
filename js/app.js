import { fetchData } from './api.js';
import { renderWallChart } from './render.js';

const CACHE_KEY = 'fifa2026-wallchart-v1';

const updateBtn = document.getElementById('update-btn');
const statusEl = document.getElementById('status');

function formatTimestamp(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

function setStatus(message) {
  statusEl.textContent = message;
}

function setLoading(loading) {
  updateBtn.disabled = loading;
  updateBtn.textContent = loading ? 'Updating…' : 'Update';
}

function saveCache(data) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
  } catch {
    /* ignore quota errors */
  }
}

function loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function applyData(data, { fromCache = false } = {}) {
  renderWallChart(data);
  const prefix = fromCache ? 'Showing cached data from' : 'Last updated';
  setStatus(`${prefix} ${formatTimestamp(data.updatedAt)}`);
}

async function handleUpdate() {
  setLoading(true);
  setStatus('Updating…');

  try {
    const data = await fetchData();
    saveCache(data);
    applyData(data);
  } catch (err) {
    const cached = loadCache();
    if (cached) {
      applyData(cached, { fromCache: true });
      setStatus(`Update failed (${err.message}). Showing cached data from ${formatTimestamp(cached.updatedAt)}.`);
    } else {
      setStatus(`Update failed: ${err.message}`);
    }
  } finally {
    setLoading(false);
  }
}

function init() {
  const cached = loadCache();
  if (cached) {
    applyData(cached, { fromCache: true });
  }

  updateBtn.addEventListener('click', handleUpdate);
}

init();
