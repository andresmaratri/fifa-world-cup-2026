import { enrichMatches, buildTeamFlagMap } from './resolve.js';

/* ─────────────────────────────────────────────────────────────────────
   Bracket wiring — all IDs are the API's 0-indexed match `id` field.
   Fixture "number" N (used in W-codes) = API id N-1.

   LEFT bracket  (columns left→right): R32 | R16 | QF | SF → Final
   RIGHT bracket (columns left→right): SF  | QF  | R16 | R32

   Each `pairs` entry is [topMatchId, bottomMatchId].
   ───────────────────────────────────────────────────────────────────── */

const LEFT_ROUNDS = [
  {
    label: 'Round of 32', side: 'r32',
    pairs: [
      [73, 76],   // M74 (1E vs 3x) & M77 (1I vs 3x)  → R16 id 88
      [72, 74],   // M73 (2A vs 2B) & M75 (1F vs 2C)   → R16 id 89
      [82, 83],   // M83 (2K vs 2L) & M84 (1H vs 2J)   → R16 id 92
      [80, 81],   // M81 (1D vs 3x) & M82 (1G vs 3x)   → R16 id 93
    ],
  },
  {
    label: 'Round of 16', side: 'r16',
    pairs: [
      [88, 89],   // M89 (W74 vs W77) & M90 (W73 vs W75) → QF id 96
      [92, 93],   // M93 (W83 vs W84) & M94 (W81 vs W82) → QF id 97
    ],
  },
  {
    label: 'Quarter-finals', side: 'qf',
    pairs: [
      [96, 97],   // M97 (W89 vs W90) & M98 (W93 vs W94) → SF id 100
    ],
  },
  { label: 'Semi-finals', side: 'sf', single: 100 },  // M101 → Final
];

const RIGHT_ROUNDS = [
  { label: 'Semi-finals', side: 'sf', single: 101 },  // M102 → Final
  {
    label: 'Quarter-finals', side: 'qf',
    pairs: [
      [98, 99],   // M99 (W91 vs W92) & M100 (W95 vs W96) ← from R16 below
    ],
  },
  {
    label: 'Round of 16', side: 'r16',
    pairs: [
      [90, 91],   // M91 (W76 vs W78) & M92 (W79 vs W80) ← from R32 below
      [94, 95],   // M95 (W86 vs W88) & M96 (W85 vs W87)
    ],
  },
  {
    label: 'Round of 32', side: 'r32',
    pairs: [
      [75, 77],   // M76 (1C vs 2F) & M78 (2E vs 2I)      → R16 id 90
      [78, 79],   // M79 (1A vs 3x) & M80 (1L vs 3x)      → R16 id 91
      [85, 87],   // M86 (1J vs 2H) & M88 (2D vs 2G)      → R16 id 94
      [84, 86],   // M85 (1B vs 3x) & M87 (1K vs 3x)      → R16 id 95
    ],
  },
];

const FINAL_ID = 103;   // W101 vs W102
const THIRD_ID = 102;   // L101 vs L102

const GROUP_ORDER = 'ABCDEFGHIJKL'.split('').map((l) => `Group ${l}`);

/* ── DOM helpers ───────────────────────────────────────────────────── */

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function formatDate(d) {
  if (!d) return '';
  return new Date(`${d}T12:00:00`).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric',
  });
}

function renderFlag(flagMap, name) {
  const url = flagMap[name];
  if (!url) return el('span', 'flag flag--empty');
  const img = document.createElement('img');
  img.className = 'flag';
  img.src = url;
  img.alt = '';
  img.loading = 'lazy';
  return img;
}

/* ── Group stage ───────────────────────────────────────────────────── */

function renderGroupCard(groupName, rows, flagMap) {
  const card = el('div', 'group-card');
  card.appendChild(el('h3', 'group-card__title', groupName));

  const table = el('table', 'group-table');
  const thead = el('thead');
  const hr = el('tr');
  ['Team', 'P', 'W', 'D', 'L', 'GF', 'GA', 'GD', 'Pts'].forEach((h) =>
    hr.appendChild(el('th', null, h)),
  );
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = el('tbody');
  rows.forEach((row, i) => {
    const tr = el('tr');
    if (i < 2) tr.classList.add('qualifier');
    else if (i === 2) tr.classList.add('third-place');

    const tc = el('td', 'team-cell');
    tc.appendChild(renderFlag(flagMap, row.team));
    tc.appendChild(el('span', 'team-name', row.team));
    tr.appendChild(tc);

    [row.p, row.w, row.d, row.l, row.gf, row.ga, row.gd, row.pts].forEach((v) =>
      tr.appendChild(el('td', null, String(v))),
    );
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  card.appendChild(table);
  return card;
}

/* ── Knockout match card ───────────────────────────────────────────── */

function getMatch(matches, id) {
  return (
    matches.find((m) => m.id === id) || {
      id,
      resolvedTeam1: 'TBD',
      resolvedTeam2: 'TBD',
      status: 'scheduled',
      score: null,
      date: null,
    }
  );
}

function renderKOMatch(match, flagMap, extraClass) {
  const card = el('article', `ko-match${extraClass ? ' ' + extraClass : ''}`);
  if (match.status === 'live') card.classList.add('ko-match--live');
  if (match.status === 'finished') card.classList.add('ko-match--done');

  const makeRow = (name, score) => {
    const row = el('div', 'ko-team');
    row.appendChild(renderFlag(flagMap, name));
    row.appendChild(el('span', 'ko-name', name));
    const sc = el('span', 'ko-score', score != null ? String(score) : '');
    if (score == null) sc.classList.add('ko-score--empty');
    row.appendChild(sc);
    return row;
  };

  card.appendChild(makeRow(match.resolvedTeam1, match.score ? match.score[0] : null));
  card.appendChild(el('hr', 'ko-divider'));
  card.appendChild(makeRow(match.resolvedTeam2, match.score ? match.score[1] : null));

  const meta = el('div', 'ko-meta', formatDate(match.date));
  if (match.status === 'live') {
    meta.appendChild(
      el('span', 'ko-live-badge', match.live_minute ? `${match.live_minute}'` : 'LIVE'),
    );
  }
  card.appendChild(meta);
  return card;
}

/* ── Bracket pair (2 vertically stacked matches with CSS connector) ── */

function renderKOPair(ids, matches, flagMap) {
  const pair = el('div', 'ko-pair');
  ids.forEach((id) => pair.appendChild(renderKOMatch(getMatch(matches, id), flagMap)));
  return pair;
}

/* ── Round column ──────────────────────────────────────────────────── */

function renderRoundCol(round, matches, flagMap) {
  const col = el('div', `ko-col ko-col--${round.side}`);
  col.appendChild(el('div', 'ko-col-title', round.label));

  const body = el('div', 'ko-col-body');
  if (round.single !== undefined) {
    body.appendChild(renderKOMatch(getMatch(matches, round.single), flagMap));
  } else {
    round.pairs.forEach((ids) => body.appendChild(renderKOPair(ids, matches, flagMap)));
  }
  col.appendChild(body);
  return col;
}

/* ── Full knockout bracket ─────────────────────────────────────────── */

function renderBracket(matches, flagMap) {
  const wrap = el('div', 'ko-bracket');

  /* Left half: R32 → R16 → QF → SF */
  const leftHalf = el('div', 'ko-half ko-half--left');
  LEFT_ROUNDS.forEach((r) => leftHalf.appendChild(renderRoundCol(r, matches, flagMap)));
  wrap.appendChild(leftHalf);

  /* Center: Final + 3rd place */
  const center = el('div', 'ko-center');

  const finalSection = el('div', 'ko-final-section');
  finalSection.appendChild(el('div', 'ko-col-title ko-col-title--final', 'Final'));
  const finalBody = el('div', 'ko-final-body');
  finalBody.appendChild(renderKOMatch(getMatch(matches, FINAL_ID), flagMap, 'ko-match--final'));
  finalSection.appendChild(finalBody);
  center.appendChild(finalSection);

  const thirdSection = el('div', 'ko-third-section');
  thirdSection.appendChild(el('div', 'ko-col-title ko-col-title--third', '3rd Place'));
  thirdSection.appendChild(renderKOMatch(getMatch(matches, THIRD_ID), flagMap));
  center.appendChild(thirdSection);

  wrap.appendChild(center);

  /* Right half: SF → QF → R16 → R32 */
  const rightHalf = el('div', 'ko-half ko-half--right');
  RIGHT_ROUNDS.forEach((r) => rightHalf.appendChild(renderRoundCol(r, matches, flagMap)));
  wrap.appendChild(rightHalf);

  return wrap;
}

/* ── Main export ───────────────────────────────────────────────────── */

export function renderWallChart({ standings, matches }) {
  const enriched = enrichMatches(matches, standings);
  const flagMap = buildTeamFlagMap(enriched);

  const groupsGrid = document.getElementById('groups-grid');
  groupsGrid.replaceChildren();
  GROUP_ORDER.forEach((g) => {
    const rows = standings[g];
    if (rows) groupsGrid.appendChild(renderGroupCard(g, rows, flagMap));
  });

  const bracketEl = document.getElementById('bracket');
  bracketEl.replaceChildren();
  bracketEl.appendChild(renderBracket(enriched, flagMap));
}
