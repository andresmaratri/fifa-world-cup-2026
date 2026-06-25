const API_BASE = 'https://wcup2026.org/api/data.php';

async function fetchAction(action) {
  const url = `${API_BASE}?action=${encodeURIComponent(action)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${action}`);
  }
  const data = await res.json();
  if (!data.ok) {
    throw new Error(data.error || `API error for ${action}`);
  }
  return data;
}

export async function fetchStandings() {
  const data = await fetchAction('standings');
  return data.standings;
}

export async function fetchAllMatches() {
  const data = await fetchAction('all');
  return data.matches;
}

export async function fetchData() {
  const [standings, matches] = await Promise.all([
    fetchStandings(),
    fetchAllMatches(),
  ]);
  return { standings, matches, updatedAt: new Date().toISOString() };
}
