import { resolveThirdPlaceCode, formatThirdPlaceholder } from './thirdPlace.js';

const GROUP_RANK = /^([12])([A-L])$/;
const WINNER = /^W(\d+)$/;
const LOSER = /^L(\d+)$/;
const THIRD = /^3/;

function looksLikeRealTeam(name) {
  if (!name) return false;
  return !GROUP_RANK.test(name) && !WINNER.test(name) && !LOSER.test(name) && !THIRD.test(name);
}

function getGroupLetter(groupName) {
  const match = groupName.match(/Group\s+([A-L])/i);
  return match ? match[1] : null;
}

function getStandingsTeam(standings, groupLetter, rank) {
  const groupKey = `Group ${groupLetter}`;
  const rows = standings[groupKey];
  if (!rows || rows.length < rank) return null;
  return rows[rank - 1].team;
}

function getPenScore(match) {
  if (!match) return null;
  for (const key of ['pen', 'pens', 'penalties', 'penalty', 'score_pen']) {
    const val = match[key];
    if (Array.isArray(val) && val.length >= 2) return [Number(val[0]), Number(val[1])];
  }
  return null;
}

function getEffectiveScore(match) {
  if (!match || match.status !== 'finished' || !match.score) return null;
  const [a, b] = match.score;
  if (a !== b) return match.score;
  const pens = getPenScore(match);
  return pens || match.score;
}

function getMatchWinner(match) {
  const score = getEffectiveScore(match);
  if (!score) return null;
  const [a, b] = score;
  if (a > b) return match.team1;
  if (b > a) return match.team2;
  return null;
}

function getMatchLoser(match) {
  const score = getEffectiveScore(match);
  if (!score) return null;
  const [a, b] = score;
  if (a > b) return match.team2;
  if (b > a) return match.team1;
  return null;
}

function findMatchByFixtureNum(matches, num) {
  const id = Number(num) - 1;
  return matches.find((m) => m.id === id) || null;
}

function formatPlaceholder(code) {
  const groupMatch = code.match(GROUP_RANK);
  if (groupMatch) {
    const rank = groupMatch[1] === '1' ? '1st' : '2nd';
    return `${rank} Group ${groupMatch[2]}`;
  }
  const winMatch = code.match(WINNER);
  if (winMatch) return `Winner M${winMatch[1]}`;
  const loseMatch = code.match(LOSER);
  if (loseMatch) return `Loser M${loseMatch[1]}`;
  if (/^3/.test(code)) return `3rd (${code.slice(1)})`;
  return code;
}

export function resolveTeamName(code, standings, matches, matchId, source) {
  if (looksLikeRealTeam(code)) return code;

  const groupMatch = code.match(GROUP_RANK);
  if (groupMatch) {
    const team = getStandingsTeam(standings, groupMatch[2], Number(groupMatch[1]));
    if (team) return team;
    return formatPlaceholder(code);
  }

  const winMatch = code.match(WINNER);
  if (winMatch) {
    const match = findMatchByFixtureNum(matches, winMatch[1]);
    const winner = match ? getMatchWinner(match) : null;
    if (winner && looksLikeRealTeam(winner)) return winner;
    if (winner) return resolveTeamName(winner, standings, matches, matchId, source);
    return formatPlaceholder(code);
  }

  const loseMatch = code.match(LOSER);
  if (loseMatch) {
    const match = findMatchByFixtureNum(matches, loseMatch[1]);
    const loser = match ? getMatchLoser(match) : null;
    if (loser && looksLikeRealTeam(loser)) return loser;
    if (loser) return resolveTeamName(loser, standings, matches, matchId, source);
    return formatPlaceholder(code);
  }

  if (THIRD.test(code)) {
    const team = resolveThirdPlaceCode(code, standings, matchId, source);
    if (team) return team;
    return formatThirdPlaceholder(code);
  }

  return formatPlaceholder(code);
}

export function enrichMatches(matches, standings, source) {
  const enriched = matches.map((match) => ({
    ...match,
    resolvedTeam1: resolveTeamName(match.team1, standings, matches, match.id, source),
    resolvedTeam2: resolveTeamName(match.team2, standings, matches, match.id, source),
  }));

  enriched
    .filter((m) => m.id >= 72)
    .sort((a, b) => a.id - b.id)
    .forEach((m) => {
      m.resolvedTeam1 = resolveTeamName(m.team1, standings, matches, m.id, source);
      m.resolvedTeam2 = resolveTeamName(m.team2, standings, matches, m.id, source);
    });

  return enriched;
}

export function buildTeamFlagMap(matches) {
  const nameFlags = {};
  for (const m of matches) {
    if (!String(m.group || '').startsWith('Group')) continue;
    if (m.team1 && m.flag1) nameFlags[m.team1] = m.flag1;
    if (m.team2 && m.flag2) nameFlags[m.team2] = m.flag2;
  }

  const map = { ...nameFlags };
  for (const m of matches) {
    if (m.team1 && m.flag1) map[m.team1] = m.flag1;
    if (m.team2 && m.flag2) map[m.team2] = m.flag2;
    if (m.resolvedTeam1 && m.flag1) map[m.resolvedTeam1] = m.flag1;
    if (m.resolvedTeam2 && m.flag2) map[m.resolvedTeam2] = m.flag2;
    if (m.resolvedTeam1 && nameFlags[m.resolvedTeam1]) map[m.resolvedTeam1] = nameFlags[m.resolvedTeam1];
    if (m.resolvedTeam2 && nameFlags[m.resolvedTeam2]) map[m.resolvedTeam2] = nameFlags[m.resolvedTeam2];
  }
  return map;
}

export { getGroupLetter, looksLikeRealTeam };
