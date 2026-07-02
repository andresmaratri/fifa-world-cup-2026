import base64
import pathlib
import re
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from data_loader import load_data
from third_place import format_third_placeholder, resolve_third_place_code

# ─── Asset helpers ───────────────────────────────────────────────────────────────

_ASSETS = pathlib.Path(__file__).parent / "assets"


def _b64_img(path: pathlib.Path) -> str:
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f"data:image/png;base64,{b64}"


LOGO_DATA_URL = _b64_img(_ASSETS / "logo.png")

# ─── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="FIFA World Cup 2026 — Wall Chart",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Team name resolution ────────────────────────────────────────────────────────

_GROUP_RANK = re.compile(r"^([12])([A-L])$")
_WINNER = re.compile(r"^W(\d+)$")
_LOSER = re.compile(r"^L(\d+)$")
_THIRD = re.compile(r"^3")


def _looks_like_real_team(name):
    if not name:
        return False
    return (
        not _GROUP_RANK.match(name)
        and not _WINNER.match(name)
        and not _LOSER.match(name)
        and not _THIRD.match(name)
    )


def _fmt_placeholder(code):
    m = _GROUP_RANK.match(code)
    if m:
        rank = "1st" if m.group(1) == "1" else "2nd"
        return f"{rank} Group {m.group(2)}"
    m = _WINNER.match(code)
    if m:
        return f"Winner M{m.group(1)}"
    m = _LOSER.match(code)
    if m:
        return f"Loser M{m.group(1)}"
    if _THIRD.match(code):
        return f"3rd ({code[1:]})"
    return code


def _standings_team(standings, letter, rank):
    rows = standings.get(f"Group {letter}", [])
    return rows[rank - 1]["team"] if len(rows) >= rank else None


def _find_match(matches, fixture_num):
    mid = int(fixture_num) - 1
    return next((m for m in matches if m["id"] == mid), None)


def _pen_score(match):
    for key in ("pen", "pens", "penalties", "penalty", "score_pen"):
        val = match.get(key)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return [int(val[0]), int(val[1])]
    return None


def _et_score(match):
    for key in ("et", "extra_time", "aet", "score_et"):
        val = match.get(key)
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return [int(val[0]), int(val[1])]
    return None


def _effective_score(match):
    if not match or match.get("status") != "finished":
        return None
    score = match.get("score")
    if not score or not isinstance(score, (list, tuple)) or len(score) < 2:
        return None
    a, b = int(score[0]), int(score[1])
    if a != b:
        return [a, b]
    pens = _pen_score(match)
    if pens:
        return pens
    et = _et_score(match)
    if et:
        return et
    return [a, b]


def _winner(match):
    score = _effective_score(match)
    if not score:
        return None
    a, b = score
    if a > b:
        return match.get("team1")
    if b > a:
        return match.get("team2")
    return None


def _loser(match):
    score = _effective_score(match)
    if not score:
        return None
    a, b = score
    if a > b:
        return match.get("team2")
    if b > a:
        return match.get("team1")
    return None


def resolve_name(code, standings, matches, match_id=None, source=None, depth=0):
    if depth > 20 or not code:
        return _fmt_placeholder(code or "")
    if _looks_like_real_team(code):
        return code
    m = _GROUP_RANK.match(code)
    if m:
        team = _standings_team(standings, m.group(2), int(m.group(1)))
        return team if team else _fmt_placeholder(code)
    m = _WINNER.match(code)
    if m:
        match = _find_match(matches, m.group(1))
        w = _winner(match)
        if w and _looks_like_real_team(w):
            return w
        if w:
            return resolve_name(w, standings, matches, match_id, source, depth + 1)
        return _fmt_placeholder(code)
    m = _LOSER.match(code)
    if m:
        match = _find_match(matches, m.group(1))
        lo = _loser(match)
        if lo and _looks_like_real_team(lo):
            return lo
        if lo:
            return resolve_name(lo, standings, matches, match_id, source, depth + 1)
        return _fmt_placeholder(code)
    if _THIRD.match(code):
        team = resolve_third_place_code(code, standings, match_id, source=source)
        if team:
            return team
        return format_third_placeholder(code)
    return _fmt_placeholder(code)


def enrich_matches(matches, standings, source=None):
    enriched = []
    for m in matches:
        enriched.append(
            {
                **m,
                "resolvedTeam1": resolve_name(
                    m.get("team1", ""), standings, matches, m.get("id"), source
                ),
                "resolvedTeam2": resolve_name(
                    m.get("team2", ""), standings, matches, m.get("id"), source
                ),
            }
        )

    for m in sorted(
        (x for x in enriched if x.get("id", 0) >= 72), key=lambda x: x["id"]
    ):
        m["resolvedTeam1"] = resolve_name(
            m.get("team1", ""), standings, matches, m.get("id"), source
        )
        m["resolvedTeam2"] = resolve_name(
            m.get("team2", ""), standings, matches, m.get("id"), source
        )

    return enriched


def build_flag_map(matches):
    name_flags = {}
    for m in matches:
        if not m.get("group", "").startswith("Group"):
            continue
        for tk, fk in [("team1", "flag1"), ("team2", "flag2")]:
            if m.get(tk) and m.get(fk):
                name_flags[m[tk]] = m[fk]

    fm = dict(name_flags)
    for m in matches:
        for tk, fk in [
            ("team1", "flag1"),
            ("team2", "flag2"),
            ("resolvedTeam1", "flag1"),
            ("resolvedTeam2", "flag2"),
        ]:
            if m.get(tk) and m.get(fk):
                fm[m[tk]] = m[fk]
        for rk in ("resolvedTeam1", "resolvedTeam2"):
            name = m.get(rk)
            if name and name in name_flags:
                fm[name] = name_flags[name]
    return fm


# ─── Bracket wiring ──────────────────────────────────────────────────────────────

LEFT_ROUNDS = [
    {"label": "Round of 32", "side": "r32", "pairs": [[73, 76], [72, 74], [82, 83], [80, 81]]},
    {"label": "Round of 16", "side": "r16", "pairs": [[88, 89], [92, 93]]},
    {"label": "Quarter-finals", "side": "qf", "pairs": [[96, 97]]},
    {"label": "Semi-finals", "side": "sf", "single": 100},
]
RIGHT_ROUNDS = [
    {"label": "Semi-finals", "side": "sf", "single": 101},
    {"label": "Quarter-finals", "side": "qf", "pairs": [[98, 99]]},
    {"label": "Round of 16", "side": "r16", "pairs": [[90, 91], [94, 95]]},
    {"label": "Round of 32", "side": "r32", "pairs": [[75, 77], [78, 79], [85, 87], [84, 86]]},
]
FINAL_ID = 103
THIRD_ID = 102
GROUP_ORDER = [f"Group {c}" for c in "ABCDEFGHIJKL"]

# ─── HTML helpers ────────────────────────────────────────────────────────────────


def _fmt_date(d):
    if not d:
        return ""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}"
    except Exception:
        return d


def _flag(flag_map, name):
    url = flag_map.get(name)
    if url:
        return f'<img class="flag" src="{url}" alt="" loading="lazy">'
    return '<span class="flag flag--empty"></span>'


def _group_card(group_name, rows, flag_map):
    rows_html = ""
    for i, row in enumerate(rows):
        cls = ' class="qualifier"' if i < 2 else (' class="third-place"' if i == 2 else "")
        flag = _flag(flag_map, row["team"])
        rows_html += (
            f'<tr{cls}>'
            f'<td class="team-cell">{flag}<span class="team-name">{row["team"]}</span></td>'
            f'<td>{row.get("p",0)}</td><td>{row.get("w",0)}</td>'
            f'<td>{row.get("d",0)}</td><td>{row.get("l",0)}</td>'
            f'<td>{row.get("gf",0)}</td><td>{row.get("ga",0)}</td>'
            f'<td>{row.get("gd",0)}</td><td>{row.get("pts",0)}</td>'
            f"</tr>"
        )
    return (
        f'<div class="group-card">'
        f'<h3 class="group-card__title">{group_name}</h3>'
        f'<table class="group-table">'
        f"<thead><tr>"
        f"<th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th>"
        f"<th>GF</th><th>GA</th><th>GD</th><th>Pts</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table></div>"
    )


def _get_match(matches, mid):
    return next(
        (m for m in matches if m["id"] == mid),
        {
            "id": mid,
            "resolvedTeam1": "TBD",
            "resolvedTeam2": "TBD",
            "status": "scheduled",
            "score": None,
            "date": None,
        },
    )


def _ko_match(match, flag_map, extra_cls=""):
    status = match.get("status", "scheduled")
    cls = f"ko-match{' ' + extra_cls if extra_cls else ''}"
    if status == "live":
        cls += " ko-match--live"
    elif status == "finished":
        cls += " ko-match--done"
    score = match.get("score")
    t1 = match.get("resolvedTeam1", "TBD")
    t2 = match.get("resolvedTeam2", "TBD")
    s1 = str(score[0]) if score else ""
    s2 = str(score[1]) if score else ""
    sc_cls1 = "ko-score" if score else "ko-score ko-score--empty"
    sc_cls2 = "ko-score" if score else "ko-score ko-score--empty"
    date_str = _fmt_date(match.get("date"))
    live_badge = ""
    if status == "live":
        lm = match.get("live_minute")
        live_badge = f'<span class="ko-live-badge">{lm}\'' if lm else '<span class="ko-live-badge">LIVE</span>'
        if lm:
            live_badge += "</span>"
    f1 = _flag(flag_map, t1)
    f2 = _flag(flag_map, t2)
    return (
        f'<article class="{cls}">'
        f'<div class="ko-team">{f1}<span class="ko-name">{t1}</span><span class="{sc_cls1}">{s1}</span></div>'
        f'<hr class="ko-divider">'
        f'<div class="ko-team">{f2}<span class="ko-name">{t2}</span><span class="{sc_cls2}">{s2}</span></div>'
        f'<div class="ko-meta">{date_str}{live_badge}</div>'
        f"</article>"
    )


def _ko_pair(ids, matches, flag_map):
    inner = "".join(_ko_match(_get_match(matches, mid), flag_map) for mid in ids)
    return f'<div class="ko-pair">{inner}</div>'


def _round_col(rnd, matches, flag_map):
    if "single" in rnd:
        body = _ko_match(_get_match(matches, rnd["single"]), flag_map)
    else:
        body = "".join(_ko_pair(ids, matches, flag_map) for ids in rnd["pairs"])
    return (
        f'<div class="ko-col ko-col--{rnd["side"]}">'
        f'<div class="ko-col-title">{rnd["label"]}</div>'
        f'<div class="ko-col-body">{body}</div>'
        f"</div>"
    )


def _bracket(matches, flag_map):
    left = "".join(_round_col(r, matches, flag_map) for r in LEFT_ROUNDS)
    right = "".join(_round_col(r, matches, flag_map) for r in RIGHT_ROUNDS)
    final = _ko_match(_get_match(matches, FINAL_ID), flag_map, "ko-match--final")
    third = _ko_match(_get_match(matches, THIRD_ID), flag_map)
    return (
        f'<div class="ko-bracket">'
        f'<div class="ko-half ko-half--left">{left}</div>'
        f'<div class="ko-center">'
        f'<div class="ko-final-section">'
        f'<div class="ko-col-title ko-col-title--final">Final</div>'
        f'<div class="ko-final-body">{final}</div>'
        f"</div>"
        f'<div class="ko-third-section">'
        f'<div class="ko-col-title ko-col-title--third">3rd Place</div>'
        f"{third}"
        f"</div>"
        f"</div>"
        f'<div class="ko-half ko-half--right">{right}</div>'
        f"</div>"
    )


# ─── CSS ────────────────────────────────────────────────────────────────────────

WALL_CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --fifa-blue:#003087;--fifa-gold:#c9a227;--fifa-green:#1a5c2e;
  --bg:#0a1628;--surface:#122038;--surface-alt:#1a2d4a;
  --text:#f0f4f8;--text-muted:#94a3b8;
  --qualifier:rgba(201,162,39,.15);--third:rgba(255,255,255,.04);
  --live:#ef4444;--border:rgba(255,255,255,.1);--radius:8px;
  --line:rgba(201,162,39,.5);--stub:20px;
}
html{font-size:14px}
body{
  margin:0;
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.4;
}
h2{
  margin:0 0 1rem;font-size:1.2rem;color:var(--fifa-gold);
  text-transform:uppercase;letter-spacing:.08em;
  border-bottom:1px solid var(--border);padding-bottom:.5rem;
}
.section{margin-bottom:2rem;padding:1.25rem 1.5rem}

/* ── Group tables ── */
.groups-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:.75rem}
.group-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.group-card__title{
  margin:0;padding:.45rem .65rem;font-size:.8rem;
  background:var(--surface-alt);color:var(--fifa-gold);
  text-transform:uppercase;letter-spacing:.06em;
}
.group-table{width:100%;border-collapse:collapse;font-size:.72rem}
.group-table th,.group-table td{padding:.25rem .35rem;text-align:center;border-bottom:1px solid var(--border)}
.group-table th:first-child,.group-table td:first-child{text-align:left}
.group-table th{color:var(--text-muted);font-weight:600;font-size:.65rem}
.group-table tbody tr:last-child td{border-bottom:none}
.group-table tr.qualifier{background:var(--qualifier)}
.group-table tr.third-place{background:var(--third)}
.team-cell{display:flex;align-items:center;gap:.35rem;min-width:0}
.team-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.flag{width:18px;height:13px;object-fit:cover;border-radius:2px;flex-shrink:0}
.flag--empty{display:inline-block;width:18px;height:13px;background:var(--surface-alt);border-radius:2px}

/* ── Bracket outer ── */
.bracket{overflow:hidden}
.ko-bracket{display:flex;flex-direction:row;align-items:flex-start;gap:40px;overflow-x:auto;padding-bottom:1rem}
.ko-half--left,.ko-half--right{display:flex;flex-direction:row;gap:40px;flex-shrink:0}

/* ── Round column ── */
.ko-col{display:flex;flex-direction:column;flex-shrink:0;width:136px;overflow:visible}
.ko-col-title{
  height:28px;display:flex;align-items:center;justify-content:center;
  font-size:.58rem;color:var(--fifa-gold);text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;
}
.ko-col-title--third{color:var(--text-muted);font-size:.55rem}
.ko-col-title--final{color:var(--fifa-gold);font-size:.7rem;font-weight:700}
.ko-col-body{height:640px;display:flex;flex-direction:column;overflow:visible}
.ko-col--sf .ko-col-body{justify-content:center}

/* ── Pairs ── */
.ko-pair{flex:1;display:flex;flex-direction:column;justify-content:space-around;position:relative;overflow:visible}

/* ── Match card ── */
.ko-match{
  width:136px;background:var(--surface);border:1px solid var(--border);
  border-radius:6px;padding:5px 7px 4px;position:relative;overflow:visible;flex-shrink:0;
}
.ko-match--live{border-color:var(--live);box-shadow:0 0 0 1px rgba(239,68,68,.25)}
.ko-match--done{opacity:.92}
.ko-match--final{width:154px;border-color:var(--fifa-gold);border-width:2px;background:var(--surface-alt)}
.ko-team{display:flex;align-items:center;gap:4px;font-size:.63rem}
.ko-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ko-score{font-weight:700;font-size:.72rem;color:var(--fifa-gold);min-width:10px;text-align:right}
.ko-score--empty::after{content:'·';color:var(--text-muted);font-weight:400}
.ko-divider{border:none;border-top:1px solid var(--border);margin:3px 0}
.ko-meta{font-size:.52rem;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;margin-top:2px}
.ko-live-badge{color:var(--live);font-weight:700;font-size:.52rem;animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

/* ── Center ── */
.ko-center{display:flex;flex-direction:column;align-items:center;flex-shrink:0}
.ko-final-section{display:flex;flex-direction:column;align-items:center}
.ko-final-body{height:640px;display:flex;align-items:center;justify-content:center}
.ko-third-section{display:flex;flex-direction:column;align-items:center;gap:6px;padding-top:20px}

/* ── Connector lines — LEFT bracket (→) ── */
.ko-half--left .ko-match::after{
  content:'';position:absolute;right:-20px;top:50%;width:20px;height:2px;
  background:var(--line);transform:translateY(-50%);
}
.ko-half--left .ko-pair::after{
  content:'';position:absolute;right:-20px;top:25%;width:2px;height:50%;background:var(--line);
}
.ko-half--left .ko-col--r16 .ko-match::before,
.ko-half--left .ko-col--qf  .ko-match::before,
.ko-half--left .ko-col--sf  .ko-match::before{
  content:'';position:absolute;left:-20px;top:50%;width:20px;height:2px;
  background:var(--line);transform:translateY(-50%);
}

/* ── Connector lines — RIGHT bracket (←) ── */
.ko-half--right .ko-match::after{
  content:'';position:absolute;left:-20px;top:50%;width:20px;height:2px;
  background:var(--line);transform:translateY(-50%);
}
.ko-half--right .ko-pair::after{
  content:'';position:absolute;left:-20px;top:25%;width:2px;height:50%;background:var(--line);
}
.ko-half--right .ko-col--sf  .ko-match::before,
.ko-half--right .ko-col--qf  .ko-match::before,
.ko-half--right .ko-col--r16 .ko-match::before{
  content:'';position:absolute;right:-20px;top:50%;width:20px;height:2px;
  background:var(--line);transform:translateY(-50%);
}

/* ── Final stubs ── */
.ko-match--final::before{
  content:'';position:absolute;left:-20px;top:50%;width:20px;height:2px;
  background:var(--line);transform:translateY(-50%);
}
.ko-match--final::after{
  content:'';position:absolute;right:-20px;top:50%;width:20px;height:2px;
  background:var(--line);transform:translateY(-50%);
}
"""


def build_wall_html(standings, enriched, flag_map):
    groups = "".join(
        _group_card(g, standings[g], flag_map) for g in GROUP_ORDER if g in standings
    )
    bracket = _bracket(enriched, flag_map)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>{WALL_CSS}</style>
</head>
<body>
<div class="section">
  <h2>Group Stage</h2>
  <div class="groups-grid">{groups}</div>
</div>
<div class="section">
  <h2>Knockout Stage</h2>
  <div class="bracket">{bracket}</div>
</div>
</body>
</html>"""


# ─── Streamlit UI ────────────────────────────────────────────────────────────────

# Dark background to match the wall chart theme
st.markdown(
    """
    <style>
      [data-testid="stAppViewContainer"] > .main { background: #0a1628; }
      [data-testid="stHeader"] { background: transparent; }
      section[data-testid="stSidebar"] { display: none; }
      .block-container { padding-top: 1rem !important; }
      div[data-testid="stMarkdownContainer"] h1 { color: #f0f4f8; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Logo
st.markdown(
    f"""
    <div style="text-align:center;padding:1rem 0 0.25rem">
      <img src="{LOGO_DATA_URL}"
           style="height:200px;width:auto;object-fit:contain;mix-blend-mode:lighten;" alt="IUGA Electronics">
    </div>
    """,
    unsafe_allow_html=True,
)

# Header row
col_title, col_ctrl = st.columns([5, 1])

with col_title:
    st.markdown(
        """
        <div style="padding:.5rem 0 .25rem">
          <h1 style="color:#f0f4f8;margin:0;font-size:2rem;font-family:system-ui,sans-serif">
            FIFA World Cup 2026
          </h1>
          <p style="color:#c9a227;font-weight:600;text-transform:uppercase;
                    letter-spacing:.12em;font-size:.85rem;margin:.15rem 0 0">
            Wall Chart
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_ctrl:
    st.markdown("<div style='padding-top:0.75rem'></div>", unsafe_allow_html=True)
    update_clicked = st.button("⟳ Update", use_container_width=True, type="primary")
    status_box = st.empty()

st.markdown(
    "<p style='color:rgba(255,255,255,.45);font-size:.7rem;margin:0 0 .75rem'>"
    "Unofficial fan project — data from wcup2026.org, not affiliated with FIFA."
    "</p>",
    unsafe_allow_html=True,
)

# ── State init ──────────────────────────────────────────────────────────────────

if "wc_data" not in st.session_state:
    st.session_state.wc_data = None
    st.session_state.wc_updated = None
    st.session_state.wc_error = None
    auto_load = True
else:
    auto_load = False

# ── Fetch ───────────────────────────────────────────────────────────────────────

if update_clicked or auto_load:
    with st.spinner("Fetching latest data…"):
        try:
            data = load_data()
            st.session_state.wc_data = data
            st.session_state.wc_updated = datetime.now()
            st.session_state.wc_error = None
        except Exception as exc:
            st.session_state.wc_error = str(exc)

if st.session_state.wc_error:
    msg = st.session_state.wc_error
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        msg = "The data server is slow or unreachable. Please try Update again."
    elif "403" in msg or "forbidden" in msg.lower():
        msg = "The data server blocked the request. Please try Update again in a moment."
    status_box.error(f"Update failed: {msg}")
    if st.session_state.wc_data:
        status_box.caption("Showing previously loaded data.")
elif st.session_state.wc_updated:
    ts = st.session_state.wc_updated.strftime("%b %d, %Y %H:%M")
    src = ""
    if st.session_state.wc_data and st.session_state.wc_data.get("source"):
        src = f" ({st.session_state.wc_data['source']})"
    status_box.caption(f"Last updated: {ts}{src}")
else:
    status_box.caption("Click Update to load data.")

# ── Render ──────────────────────────────────────────────────────────────────────

if st.session_state.wc_data:
    d = st.session_state.wc_data
    enriched = enrich_matches(d["matches"], d["standings"], d.get("source"))
    flag_map = build_flag_map(enriched)
    html = build_wall_html(d["standings"], enriched, flag_map)
    components.html(html, height=2200, scrolling=True)
