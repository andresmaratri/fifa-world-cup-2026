"""Hybrid data loader: OpenFootball GitHub JSON (primary) + wcup2026.org fallback."""

import time
from datetime import datetime, timezone

import requests

OPENFOOTBALL_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
)
WCUP_API = "https://wcup2026.org/api/data.php"
_TIMEOUT = (10, 45)
_RETRIES = 3
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

_TEAM_ISO = {
    "Mexico": "mx",
    "South Africa": "za",
    "South Korea": "kr",
    "Czech Republic": "cz",
    "Canada": "ca",
    "Bosnia & Herzegovina": "ba",
    "Qatar": "qa",
    "Switzerland": "ch",
    "Brazil": "br",
    "Morocco": "ma",
    "Haiti": "ht",
    "Scotland": "gb-sct",
    "USA": "us",
    "Paraguay": "py",
    "Australia": "au",
    "Turkey": "tr",
    "Germany": "de",
    "Curaçao": "cw",
    "Ivory Coast": "ci",
    "Ecuador": "ec",
    "Netherlands": "nl",
    "Japan": "jp",
    "Sweden": "se",
    "Tunisia": "tn",
    "Belgium": "be",
    "Egypt": "eg",
    "Iran": "ir",
    "New Zealand": "nz",
    "Spain": "es",
    "Cape Verde": "cv",
    "Saudi Arabia": "sa",
    "Uruguay": "uy",
    "France": "fr",
    "Senegal": "sn",
    "Iraq": "iq",
    "Norway": "no",
    "Argentina": "ar",
    "Algeria": "dz",
    "Austria": "at",
    "Jordan": "jo",
    "Portugal": "pt",
    "DR Congo": "cd",
    "Uzbekistan": "uz",
    "Colombia": "co",
    "England": "gb-eng",
    "Croatia": "hr",
    "Ghana": "gh",
    "Panama": "pa",
}


def _looks_like_team_name(name):
    if not name:
        return False
    if len(name) <= 3 and name[0].isdigit():
        return False
    if name.startswith("W") and name[1:].isdigit():
        return False
    if name.startswith("L") and name[1:].isdigit():
        return False
    if name.startswith("3"):
        return False
    return True


def _flag_url(team_name):
    if not _looks_like_team_name(team_name):
        return ""
    code = _TEAM_ISO.get(team_name)
    if code:
        return f"https://flagcdn.com/w80/{code}.png"
    return ""


def _parse_openfootball_score(score_obj):
    """Return (score_list, status) from openfootball score object."""
    if not score_obj:
        return None, "scheduled"
    ft = score_obj.get("ft")
    if not ft:
        return None, "scheduled"
    pens = score_obj.get("p")
    if pens and ft[0] == ft[1]:
        return [int(pens[0]), int(pens[1])], "finished"
    return [int(ft[0]), int(ft[1])], "finished"


def _pen_score_from_match(match):
    """Extract penalty shootout score from wcup-style match fields."""
    for key in ("pen", "pens", "penalties", "penalty", "score_pen"):
        val = match.get(key)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return [int(val[0]), int(val[1])]
        if isinstance(val, dict):
            for sub in ("p", "ft", "score"):
                inner = val.get(sub)
                if isinstance(inner, (list, tuple)) and len(inner) >= 2:
                    return [int(inner[0]), int(inner[1])]
    score_obj = match.get("scoreObj") or match.get("scores")
    if isinstance(score_obj, dict):
        pens = score_obj.get("p") or score_obj.get("pen")
        if isinstance(pens, (list, tuple)) and len(pens) >= 2:
            return [int(pens[0]), int(pens[1])]
    return None


def normalize_match_score(match):
    """Normalize score so penalty winners are reflected in score list."""
    score = match.get("score")
    if not score or not isinstance(score, (list, tuple)) or len(score) < 2:
        return score
    a, b = int(score[0]), int(score[1])
    if a != b:
        return [a, b]
    pens = _pen_score_from_match(match)
    if pens:
        return pens
    return [a, b]


def _normalize_wcup_matches(matches):
    out = []
    for m in matches:
        entry = dict(m)
        entry["score"] = normalize_match_score(entry)
        out.append(entry)
    return out


def _compute_standings(group_matches):
    """Build standings tables from finished group-stage matches."""
    stats = {}
    for m in group_matches:
        g = m.get("group", "")
        if not g.startswith("Group "):
            continue
        for team in (m["team1"], m["team2"]):
            if team not in stats:
                stats[team] = {
                    "team": team,
                    "p": 0,
                    "w": 0,
                    "d": 0,
                    "l": 0,
                    "gf": 0,
                    "ga": 0,
                    "gd": 0,
                    "pts": 0,
                    "_group": g,
                }
        if m.get("status") != "finished" or not m.get("score"):
            continue
        t1, t2 = m["team1"], m["team2"]
        s1, s2 = m["score"]
        stats[t1]["p"] += 1
        stats[t2]["p"] += 1
        stats[t1]["gf"] += s1
        stats[t1]["ga"] += s2
        stats[t2]["gf"] += s2
        stats[t2]["ga"] += s1
        if s1 > s2:
            stats[t1]["w"] += 1
            stats[t1]["pts"] += 3
            stats[t2]["l"] += 1
        elif s2 > s1:
            stats[t2]["w"] += 1
            stats[t2]["pts"] += 3
            stats[t1]["l"] += 1
        else:
            stats[t1]["d"] += 1
            stats[t2]["d"] += 1
            stats[t1]["pts"] += 1
            stats[t2]["pts"] += 1

    standings = {}
    for team, row in stats.items():
        row["gd"] = row["gf"] - row["ga"]
        g = row.pop("_group")
        standings.setdefault(g, []).append(row)

    for g in standings:
        standings[g].sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"]))
    return standings


def _normalize_openfootball(raw):
    """Convert openfootball JSON to app match list + computed standings."""
    raw_matches = raw.get("matches", [])
    normalized = []
    group_idx = 0

    for m in raw_matches:
        rnd = m.get("round", "")
        score, status = _parse_openfootball_score(m.get("score"))
        t1, t2 = m.get("team1", ""), m.get("team2", "")

        if rnd.startswith("Matchday") or m.get("group", "").startswith("Group"):
            mid = group_idx
            group_idx += 1
            entry = {
                "id": mid,
                "round": rnd,
                "group": m.get("group", ""),
                "team1": t1,
                "team2": t2,
                "flag1": _flag_url(t1),
                "flag2": _flag_url(t2),
                "status": status,
                "score": score,
                "date": m.get("date"),
                "ground": m.get("ground", ""),
            }
        else:
            num = m.get("num")
            if num is None:
                if rnd == "Final":
                    num = 104
                elif "third" in rnd.lower():
                    num = 103
                else:
                    continue
            mid = int(num) - 1
            entry = {
                "id": mid,
                "round": rnd,
                "group": "",
                "team1": t1,
                "team2": t2,
                "flag1": _flag_url(t1),
                "flag2": _flag_url(t2),
                "status": status,
                "score": score,
                "date": m.get("date"),
                "ground": m.get("ground", ""),
            }
        normalized.append(entry)

    normalized.sort(key=lambda x: x["id"])
    group_matches = [m for m in normalized if m.get("group", "").startswith("Group")]
    standings = _compute_standings(group_matches)
    return normalized, standings


def _fetch_openfootball():
    last_err = None
    for attempt in range(_RETRIES):
        try:
            r = requests.get(OPENFOOTBALL_URL, timeout=_TIMEOUT, headers=_HEADERS)
            r.raise_for_status()
            return r.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_err = exc
            if attempt < _RETRIES - 1:
                time.sleep(2**attempt)
    raise last_err


def _fetch_wcup():
    session = requests.Session()
    session.headers.update({**_HEADERS, "Referer": "https://wcup2026.org/"})

    def fetch_action(action):
        url = f"{WCUP_API}?action={action}"
        last_err = None
        for attempt in range(_RETRIES):
            try:
                r = session.get(url, timeout=_TIMEOUT)
                if r.status_code == 403:
                    raise requests.HTTPError(f"403 Forbidden for {action}", response=r)
                r.raise_for_status()
                data = r.json()
                if not data.get("ok"):
                    raise ValueError(data.get("error", f"API error for {action}"))
                return data
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_err = exc
                if attempt < _RETRIES - 1:
                    time.sleep(2**attempt)
        raise last_err

    standings_data = fetch_action("standings")
    time.sleep(0.5)
    all_data = fetch_action("all")
    return {
        "standings": standings_data["standings"],
        "matches": _normalize_wcup_matches(all_data["matches"]),
    }


def load_data():
    """Load tournament data. Returns dict with standings, matches, updatedAt, source."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        raw = _fetch_openfootball()
        matches, standings = _normalize_openfootball(raw)
        return {
            "standings": standings,
            "matches": matches,
            "updatedAt": now,
            "source": "OpenFootball",
        }
    except Exception:
        data = _fetch_wcup()
        return {
            "standings": data["standings"],
            "matches": data["matches"],
            "updatedAt": now,
            "source": "wcup2026.org",
        }
