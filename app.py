import io
import math
import re

import pandas as pd
import streamlit as st

COLS = "league_country,season,date,home_team,away_team,home_goals,away_goals,home_shots_on_target,away_shots_on_target,home_big_chances,away_big_chances,home_box_touches,away_box_touches,home_corner_kicks,away_corner_kicks,home_fouled_in_final_third,away_fouled_in_final_third,home_accurate_crosses,away_accurate_crosses,home_successful_crosses_percentage,away_successful_crosses_percentage,home_accurate_long_balls,away_accurate_long_balls,home_successful_long_passes_percentage,away_successful_long_passes_percentage,home_final_third_entries,away_final_third_entries,home_dribbles_percentage,away_dribbles_percentage,home_tackles_won_percentage,away_tackles_won_percentage,home_ground_duels_percentage,away_ground_duels_percentage,home_aerial_duels_percentage,away_aerial_duels_percentage,home_goalkeeper_saves,away_goalkeeper_saves,home_xg,away_xg,home_xgot,away_xgot,home_xg_set_play,away_xg_set_play,home_xg_open_play,away_xg_open_play".split(",")

# Columns that identify a match or describe it (not stat metrics). Never copied.
NON_STAT_DEFAULT = ["league_country", "season", "date", "home_team", "away_team"]


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
    """Returns (dataframe, number of malformed lines that had to be skipped)."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    bad = []
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except pd.errors.ParserError:
        # tolerant fallback: sniff delimiter, skip (and count) malformed lines
        bad.clear()
        df = pd.read_csv(
            io.StringIO(text), sep=None, engine="python", dtype=str,
            keep_default_na=False, skipinitialspace=True,
            on_bad_lines=lambda row: bad.append(row),  # returns None -> line skipped
        )
    for c in df.columns:
        df[c] = df[c].map(lambda v, c=c: rnd(c, v))
    return df, len(bad)


def detect(df, name):
    for c in df.columns:
        if canon(c) == name:
            return c
    return df.columns[0]


# ---------- UI ----------
st.set_page_config(page_title="CSV Match Merger", page_icon="⚽", layout="wide")
st.title("⚽ CSV Match Merger")
st.caption("Upload two CSVs, copy missing stat metrics one way (matched by date + home team + "
           "away team), calculate percentages and export the result.")

c1, c2 = st.columns(2)
files, dfs, keys = [None, None], [None, None], [None, None]
for i, col in enumerate((c1, c2)):
    with col:
        st.subheader(f"CSV {i + 1}")
        files[i] = st.file_uploader("Upload CSV", type="csv", key=f"f{i}")
        if files[i]:
            dfs[i], nbad = load(files[i].getvalue())
            st.caption(f"{len(dfs[i])} rows · {len(dfs[i].columns)} columns "
                       "(decimals stripped except xG family)")
            if nbad:
                st.warning(f"{nbad} malformed line(s) in this file were skipped. Matches on those "
                           "lines will be missing - fix the source file if that matters.")
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

# ---------- direction ----------
st.subheader("Copy direction")
direction = st.radio(
    "Copy stat metrics from → to",
    ["CSV 1 → CSV 2", "CSV 2 → CSV 1"],
    horizontal=True,
    help="Only empty cells in the destination file are filled. The source file is never changed.",
)
src, dst = (0, 1) if direction == "CSV 1 → CSV 2" else (1, 0)
st.caption(f"Empty stat cells in **CSV {dst + 1}** will be filled from **CSV {src + 1}**. "
           f"The output is CSV {dst + 1} with its own columns and rows, plus any essential columns it "
           "was missing. Nothing else is changed.")

# ---------- column mapping ----------
st.subheader("Stat columns to copy")
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

all_canon = sorted({canon(c) for d in dfs for c in d.columns})
non_stat = st.multiselect(
    "Non-stat columns (never copied, left exactly as they are)",
    all_canon,
    default=[c for c in NON_STAT_DEFAULT if c in all_canon],
    help="Add any other descriptive column here (e.g. venue, referee, round).",
)
essential = st.multiselect(
    "Essential columns (added to the destination if it doesn't have them)",
    COLS,
    default=[c for c in COLS if canon(c) not in set(non_stat)],
    help="Any of these missing from the destination file is added as a new column and filled "
         "from the source file. Other source-only columns are NOT added.",
)
overwrite = st.checkbox("Overwrite existing percentage values with recalculated ones")

# ---------- run ----------
if st.button("Copy stats, calculate & build final CSV", type="primary"):
    excluded = set(non_stat) | kc
    S = dfs[src].to_dict("records")
    D = dfs[dst].to_dict("records")
    src_name, dst_name = ("CSV 1 column", "CSV 2 column") if src == 0 else ("CSV 2 column", "CSV 1 column")

    # (source column, destination column) pairs - stat metrics only
    pairs = [
        (s, d) for s, d in zip(mapping[src_name], mapping[dst_name])
        if s in dfs[src].columns and d in dfs[dst].columns
        and canon(d) not in excluded and canon(s) not in excluded
    ]

    s_index = {}
    for r in S:
        s_index.setdefault(key(r, keys[src]), r)

    dst_col = {canon(c): c for c in dfs[dst].columns}
    src_col = {canon(c): c for c in dfs[src].columns}

    # essential columns the destination lacks -> appended (in COLS order), nothing else is added
    add_cols = [c for c in essential if canon(c) not in dst_col and canon(c) not in excluded]
    for c in add_cols:
        dst_col[canon(c)] = c
    matched = unmatched = filled = calc = 0

    for rd in D:
        for c in add_cols:
            rd[c] = ""
        rs = s_index.get(key(rd, keys[dst]))
        if rs is not None:
            matched += 1
            for s, d in pairs:
                if empty(rd[d]) and not empty(rs[s]):
                    rd[d] = rs[s]
                    filled += 1
            for c in add_cols:
                sc = src_col.get(canon(c))
                if sc is not None and not empty(rs[sc]):
                    rd[c] = rs[sc]
                    filled += 1
        else:
            unmatched += 1

        # canonical view used only to calculate percentages (inputs may come from either file)
        m = {canon(c): v for c, v in rd.items() if not empty(v)}
        if rs is not None:
            for c, v in rs.items():
                if canon(c) not in excluded and canon(c) not in m and not empty(v):
                    m[canon(c)] = v

        def put(c, v):
            """Write a calculated percentage into the destination row (if it has that column)."""
            global calc
            col = dst_col.get(c)
            if v is None or col is None:
                return
            if overwrite or empty(rd[col]):
                new = str(v)
                if rd[col] != new:
                    rd[col] = new
                    calc += 1

        for s_ in ("home", "away"):
            put(f"{s_}_tackles_won_percentage", pct(num(m, f"{s_}_tackles_won"), num(m, f"{s_}_total_tackles")))
            put(f"{s_}_successful_crosses_percentage", pct(num(m, f"{s_}_accurate_crosses"), num(m, f"{s_}_total_crosses")))
        for t in ("ground", "aerial"):
            h, a = num(m, f"home_{t}_duels_won"), num(m, f"away_{t}_duels_won")
            if h is not None and a is not None and h + a > 0:
                put(f"home_{t}_duels_percentage", math.floor(h / (h + a) * 100 + 0.5))
                put(f"away_{t}_duels_percentage", math.floor(a / (h + a) * 100 + 0.5))

    out = pd.DataFrame(D, columns=list(dfs[dst].columns) + add_cols).fillna("")
    st.session_state["result"] = (out, matched, unmatched, filled, calc, src + 1, dst + 1, add_cols)

if "result" in st.session_state:
    out, matched, unmatched, filled, calc, s_no, d_no, added = st.session_state["result"]
    st.success(f"{len(out)} rows (CSV {d_no}) · {matched} matched in CSV {s_no} · "
               f"{unmatched} with no match · {filled} stat cells copied · "
               f"{calc} percentages calculated · {len(added)} essential columns added.")
    if added:
        st.caption("Added columns: " + ", ".join(added))
    blanks = {c: int((out[c] == "").sum()) for c in out.columns if (out[c] == "").any()}
    if blanks:
        st.caption("Columns still containing empty cells: "
                   + ", ".join(f"{c} ({n})" for c, n in blanks.items()))
    st.download_button("⬇️ Download final CSV", out.to_csv(index=False).encode("utf-8"),
                       "final_matches.csv", "text/csv", type="primary")
    st.dataframe(out, use_container_width=True)
