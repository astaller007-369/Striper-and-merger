import math
import re

import pandas as pd
import streamlit as st

COLS = "league_country,season,date,home_team,away_team,home_goals,away_goals,home_shots_on_target,away_shots_on_target,home_big_chances,away_big_chances,home_box_touches,away_box_touches,home_corner_kicks,away_corner_kicks,home_fouled_in_final_third,away_fouled_in_final_third,home_accurate_crosses,away_accurate_crosses,home_successful_crosses_percentage,away_successful_crosses_percentage,home_accurate_long_balls,away_accurate_long_balls,home_successful_long_passes_percentage,away_successful_long_passes_percentage,home_final_third_entries,away_final_third_entries,home_dribbles_percentage,away_dribbles_percentage,home_tackles_won_percentage,away_tackles_won_percentage,home_ground_duels_percentage,away_ground_duels_percentage,home_aerial_duels_percentage,away_aerial_duels_percentage,home_goalkeeper_saves,away_goalkeeper_saves,home_xg,away_xg,home_xgot,away_xgot,home_xg_set_play,away_xg_set_play,home_xg_open_play,away_xg_open_play".split(",")


# ---------- helpers ----------
def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def canon(s):
    """Normalised column name; 'long passes' and 'long balls' are the same thing."""
    c = norm(s).replace("long_passes", "long_balls")
    return re.sub(r"long_pass(_|$)", r"long_balls\1", c)


def is_xg(c):
    return "xg" in canon(c)


def empty(v):
    return v is None or str(v).strip() == ""


def rnd(col, v):
    """Strip decimals (round) everywhere except the xG family."""
    if is_xg(col) or not isinstance(v, str):
        return v
    m = re.match(r"^(-?\d+\.\d+)(%?)$", v.strip())
    return str(math.floor(float(m.group(1)) + 0.5)) + m.group(2) if m else v


def nt(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def nd(s):
    s = str(s).strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)  # day first
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    d = pd.to_datetime(s, errors="coerce")
    return s.lower() if pd.isna(d) else d.strftime("%Y-%m-%d")


def key(row, k):
    return f"{nd(row[k[0]])}|{nt(row[k[1]])}|{nt(row[k[2]])}"


def num(m, c):
    try:
        return float(str(m.get(c, "")).replace("%", ""))
    except ValueError:
        return None


def pct(n, d):
    return None if n is None or d is None or d <= 0 else math.floor(n / d * 100 + 0.5)


@st.cache_data(show_spinner=False)
def load(file_bytes):
    import io
    df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    for c in df.columns:
        df[c] = df[c].map(lambda v, c=c: rnd(c, v))
    return df


def detect(df, name):
    for c in df.columns:
        if canon(c) == name:
            return c
    return df.columns[0]


# ---------- UI ----------
st.set_page_config(page_title="CSV Match Merger", page_icon="⚽", layout="wide")
st.title("⚽ CSV Match Merger")
st.caption("Upload two CSVs, cross-fill empty cells by date + home team + away team, "
           "calculate percentages and export one clean CSV.")

c1, c2 = st.columns(2)
files, dfs, keys = [None, None], [None, None], [None, None]
for i, col in enumerate((c1, c2)):
    with col:
        st.subheader(f"CSV {i + 1}")
        files[i] = st.file_uploader("Upload CSV", type="csv", key=f"f{i}")
        if files[i]:
            dfs[i] = load(files[i].getvalue())
            st.caption(f"{len(dfs[i])} rows · {len(dfs[i].columns)} columns "
                       "(decimals stripped except xG family)")
            k1, k2, k3 = st.columns(3)
            cols = list(dfs[i].columns)
            keys[i] = [
                k1.selectbox("Date", cols, cols.index(detect(dfs[i], "date")), key=f"d{i}"),
                k2.selectbox("Home team", cols, cols.index(detect(dfs[i], "home_team")), key=f"h{i}"),
                k3.selectbox("Away team", cols, cols.index(detect(dfs[i], "away_team")), key=f"a{i}"),
            ]

if not all(d is not None for d in dfs):
    st.info("Upload both CSV files to continue.")
    st.stop()

# ---------- column mapping ----------
st.subheader("Matching columns (copied both ways)")
kc = {canon(c) for k in keys for c in k}
auto = []
for a in dfs[0].columns:
    if canon(a) in kc:
        continue
    b = next((x for x in dfs[1].columns if canon(x) == canon(a)), None)
    if b:
        auto.append({"CSV 1 column": a, "CSV 2 column": b})

sig = (tuple(dfs[0].columns), tuple(dfs[1].columns))
if st.session_state.get("sig") != sig:
    st.session_state["sig"] = sig
    st.session_state["map"] = pd.DataFrame(auto, columns=["CSV 1 column", "CSV 2 column"])
    st.session_state.pop("editor", None)

st.caption("Auto-matched by name. Edit, delete, or add rows (＋ at the bottom of the table). "
           "'Long balls' and 'long passes' are treated as the same column.")
if st.button("Reset to auto-match"):
    st.session_state["map"] = pd.DataFrame(auto, columns=["CSV 1 column", "CSV 2 column"])
    st.session_state.pop("editor", None)

mapping = st.data_editor(
    st.session_state["map"], num_rows="dynamic", use_container_width=True, key="editor",
    column_config={
        "CSV 1 column": st.column_config.SelectboxColumn(options=list(dfs[0].columns)),
        "CSV 2 column": st.column_config.SelectboxColumn(options=list(dfs[1].columns)),
    },
)
overwrite = st.checkbox("Overwrite existing percentage values with recalculated ones")

# ---------- run ----------
if st.button("Merge, calculate & build final CSV", type="primary"):
    A = dfs[0].to_dict("records")
    B = dfs[1].to_dict("records")
    b_index = {}
    for r in B:
        b_index.setdefault(key(r, keys[1]), r)

    pairs = [(a, b) for a, b in zip(mapping["CSV 1 column"], mapping["CSV 2 column"])
             if a in dfs[0].columns and b in dfs[1].columns]
    matched = filled = 0
    seen = set()
    for ra in A:
        k = key(ra, keys[0])
        rb = b_index.get(k)
        if rb is None:
            continue
        if k not in seen:
            seen.add(k)
            matched += 1
        for a, b in pairs:
            if empty(ra[a]) and not empty(rb[b]):
                ra[a] = rb[b]; filled += 1
            elif empty(rb[b]) and not empty(ra[a]):
                rb[b] = ra[a]; filled += 1

    # merge both files into one canonical-named row per match
    merged, order = {}, []

    def add(r, k, kk, fields):
        m = merged.get(k)
        if m is None:
            m = merged[k] = {}
            order.append(k)
        for c in fields:
            cc = canon(c)
            if empty(m.get(cc)) and not empty(r[c]):
                m[cc] = r[c]
        for name, col in zip(("date", "home_team", "away_team"), kk):
            if empty(m.get(name)):
                m[name] = r[col]

    for r in A:
        add(r, key(r, keys[0]), keys[0], dfs[0].columns)
    for r in B:
        add(r, key(r, keys[1]), keys[1], dfs[1].columns)

    def put(m, c, v):
        if v is not None and (overwrite or empty(m.get(c))):
            m[c] = v

    for k in order:
        m = merged[k]
        for s in ("home", "away"):
            put(m, f"{s}_tackles_won_percentage", pct(num(m, f"{s}_tackles_won"), num(m, f"{s}_total_tackles")))
            put(m, f"{s}_successful_crosses_percentage", pct(num(m, f"{s}_accurate_crosses"), num(m, f"{s}_total_crosses")))
        for t in ("ground", "aerial"):
            h, a = num(m, f"home_{t}_duels_won"), num(m, f"away_{t}_duels_won")
            if h is not None and a is not None and h + a > 0:
                put(m, f"home_{t}_duels_percentage", math.floor(h / (h + a) * 100 + 0.5))
                put(m, f"away_{t}_duels_percentage", math.floor(a / (h + a) * 100 + 0.5))

    out = pd.DataFrame([[rnd(c, str(merged[k].get(canon(c), ""))) for c in COLS] for k in order],
                       columns=COLS)
    st.session_state["result"] = (out, matched, filled)

if "result" in st.session_state:
    out, matched, filled = st.session_state["result"]
    st.success(f"{len(out)} rows in final CSV · {matched} matches found · "
               f"{filled} empty cells filled across the two files.")
    blanks = {c: int((out[c] == "").sum()) for c in COLS if (out[c] == "").any()}
    if blanks:
        st.caption("Columns still containing empty cells (no source data found): "
                   + ", ".join(f"{c} ({n})" for c, n in blanks.items()))
    st.download_button("⬇️ Download final CSV", out.to_csv(index=False).encode("utf-8"),
                       "final_matches.csv", "text/csv", type="primary")
    st.dataframe(out, use_container_width=True)
