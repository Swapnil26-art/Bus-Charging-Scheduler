"""
Bus Charging Scheduler — Streamlit App
======================================
Single-process app. Pick a scenario, see the schedule.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import json

from scheduler import (
    load_all_scenarios,
    run_scheduler,
    minutes_to_hhmm,
    hhmm_to_minutes,
    ScheduleResult,
    BusResult,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ChargeSched",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background-color: #0a0c10;
    color: #c8d0e0;
}

.stApp {
    background: #0a0c10;
}

/* ── Header ── */
.cs-header {
    border-bottom: 1px solid #1e2530;
    padding: 1.5rem 0 1.2rem 0;
    margin-bottom: 2rem;
    display: flex;
    align-items: baseline;
    gap: 1rem;
}

.cs-logo {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.5rem;
    font-weight: 700;
    color: #4fd1c5;
    letter-spacing: -0.02em;
}

.cs-logo span {
    color: #2d3748;
}

.cs-tagline {
    font-size: 0.78rem;
    color: #4a5568;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* ── Section headings ── */
.cs-section {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    color: #4fd1c5;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin: 2rem 0 0.75rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.cs-section::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #1e2530;
}

/* ── Cards ── */
.cs-card {
    background: #0f1318;
    border: 1px solid #1a2030;
    border-radius: 6px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.75rem;
}

/* ── Stat boxes ── */
.cs-stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1.5rem;
}
.cs-stat {
    background: #0f1318;
    border: 1px solid #1a2030;
    border-radius: 6px;
    padding: 1rem 1.25rem;
    text-align: left;
}
.cs-stat-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 700;
    color: #edf2f7;
    line-height: 1;
}
.cs-stat-label {
    font-size: 0.72rem;
    color: #4a5568;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: 0.3rem;
}
.cs-stat-accent { border-left: 3px solid #4fd1c5; }
.cs-stat-warn   { border-left: 3px solid #f6ad55; }
.cs-stat-info   { border-left: 3px solid #667eea; }
.cs-stat-ok     { border-left: 3px solid #68d391; }

/* ── Operator badges ── */
.op-kpn      { background:#1a3a5c; color:#63b3ed; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-family:'IBM Plex Mono',monospace; font-weight:600; }
.op-freshbus { background:#1a3a2c; color:#68d391; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-family:'IBM Plex Mono',monospace; font-weight:600; }
.op-flixbus  { background:#3a2c1a; color:#f6ad55; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-family:'IBM Plex Mono',monospace; font-weight:600; }

/* ── Direction badge ── */
.dir-bk { background:#1a2a3a; color:#90cdf4; border-radius:4px; padding:2px 8px; font-size:0.7rem; font-family:'IBM Plex Mono',monospace; }
.dir-kb { background:#2a1a3a; color:#d6bcfa; border-radius:4px; padding:2px 8px; font-size:0.7rem; font-family:'IBM Plex Mono',monospace; }

/* ── Timeline row ── */
.tl-row {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #a0aec0;
    border-bottom: 1px solid #141820;
    padding: 0.5rem 0;
}
.tl-row:last-child { border-bottom: none; }

/* ── Wait indicator ── */
.wait-none { color: #68d391; }
.wait-low  { color: #f6ad55; }
.wait-high { color: #fc8181; }

/* ── Streamlit overrides ── */
div[data-testid="stSelectbox"] > div > div {
    background: #0f1318 !important;
    border-color: #1e2530 !important;
    color: #c8d0e0 !important;
    font-family: 'IBM Plex Mono', monospace;
}

.stDataFrame {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
}

div[data-testid="stDataFrame"] {
    background: #0f1318;
    border: 1px solid #1a2030;
    border-radius: 6px;
    overflow: hidden;
}

/* Tabs */
button[data-baseweb="tab"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.75rem !important;
    color: #4a5568 !important;
    letter-spacing: 0.05em;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #4fd1c5 !important;
    border-bottom-color: #4fd1c5 !important;
}

/* Sliders */
div[data-testid="stSlider"] .stSlider > div {
    color: #c8d0e0;
}

/* Expander */
details summary {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #667eea;
}

/* Selectbox label */
.stSelectbox label, .stSlider label {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.72rem !important;
    color: #4a5568 !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* Metric */
[data-testid="metric-container"] {
    background: #0f1318;
    border: 1px solid #1a2030;
    border-radius: 6px;
    padding: 0.75rem 1rem;
}

/* Info/warning boxes */
div[data-testid="stInfo"] {
    background: #0d1f2d;
    border-color: #1e4976;
    color: #90cdf4;
}

/* scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0a0c10; }
::-webkit-scrollbar-thumb { background: #2d3748; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4a5568; }
</style>
""", unsafe_allow_html=True)


# ── Load scenarios (cached) ────────────────────────────────────────────────────
@st.cache_data
def load_scenarios():
    scenarios_dir = Path(__file__).parent / "scenarios"
    return load_all_scenarios(scenarios_dir)


@st.cache_data
def get_schedule(scenario_id: str, weights_key: str, _scenario):
    """Cache schedule per scenario+weights combo."""
    return run_scheduler(_scenario)


# ── Helpers ───────────────────────────────────────────────────────────────────

OPERATOR_COLORS = {
    "kpn":      "#63b3ed",
    "freshbus": "#68d391",
    "flixbus":  "#f6ad55",
}

def op_badge(op: str) -> str:
    return f'<span class="op-{op}">{op.upper()}</span>'

def dir_badge(d: str) -> str:
    label = "BLR → KCH" if d == "BK" else "KCH → BLR"
    return f'<span class="dir-{d.lower()}">{label}</span>'

def wait_class(minutes: float) -> str:
    if minutes < 1:   return "wait-none"
    if minutes < 30:  return "wait-low"
    return "wait-high"

def fmt_min(m: float) -> str:
    h = int(m) // 60
    mn = int(m) % 60
    if h:
        return f"{h}h {mn}m" if mn else f"{h}h"
    return f"{mn}m"


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cs-header">
  <div class="cs-logo">⚡ CHARGE<span>//</span>SCHED</div>
  <div class="cs-tagline">Electric Bus Charging Scheduler · BLR → KCH Corridor</div>
</div>
""", unsafe_allow_html=True)


# ── Load data ─────────────────────────────────────────────────────────────────
all_scenarios = load_scenarios()
scenario_options = {s.name: sid for sid, s in all_scenarios.items()}


# ── Scenario picker ───────────────────────────────────────────────────────────
col_pick, col_info = st.columns([1, 2])

with col_pick:
    st.markdown('<div class="cs-section">01 · Scenario</div>', unsafe_allow_html=True)
    selected_name = st.selectbox(
        "Select scenario",
        options=list(scenario_options.keys()),
        label_visibility="collapsed",
    )
    selected_id = scenario_options[selected_name]
    scenario = all_scenarios[selected_id]

with col_info:
    st.markdown('<div class="cs-section">Description</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="cs-card" style="margin-top:0.1rem">
        <div style="font-size:0.85rem; color:#a0aec0; line-height:1.6">{scenario.description}</div>
        <div style="margin-top:0.75rem; display:flex; gap:0.5rem; flex-wrap:wrap;">
            <span style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#4a5568;">
                {len(scenario.buses)} buses
            </span>
            <span style="color:#2d3748">·</span>
            <span style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#4a5568;">
                Speed {scenario.physics.speed_kmh} km/h
            </span>
            <span style="color:#2d3748">·</span>
            <span style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#4a5568;">
                Range {scenario.physics.battery_range_km} km
            </span>
            <span style="color:#2d3748">·</span>
            <span style="font-family:'IBM Plex Mono',monospace; font-size:0.7rem; color:#4a5568;">
                Charge {scenario.physics.charge_duration_min} min
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Weight tuner ──────────────────────────────────────────────────────────────
st.markdown('<div class="cs-section">02 · Weight Tuner</div>', unsafe_allow_html=True)

wt_col1, wt_col2, wt_col3 = st.columns(3)
with wt_col1:
    w_individual = st.slider(
        "Individual (bus wait)",
        min_value=0.0, max_value=5.0,
        value=float(scenario.weights.get("individual", 1.0)),
        step=0.1,
        help="How much to penalise a single bus waiting too long.",
    )
with wt_col2:
    w_operator = st.slider(
        "Operator (fleet fairness)",
        min_value=0.0, max_value=5.0,
        value=float(scenario.weights.get("operator", 1.0)),
        step=0.1,
        help="How much to penalise one operator's fleet being disadvantaged.",
    )
with wt_col3:
    w_overall = st.slider(
        "Overall (network throughput)",
        min_value=0.0, max_value=5.0,
        value=float(scenario.weights.get("overall", 1.0)),
        step=0.1,
        help="How much to penalise high total system wait time.",
    )

# Apply overridden weights
import copy
active_scenario = copy.deepcopy(scenario)
active_scenario.weights = {
    "individual": w_individual,
    "operator":   w_operator,
    "overall":    w_overall,
}


# ── Run scheduler ─────────────────────────────────────────────────────────────
weights_key = f"{w_individual:.1f}-{w_operator:.1f}-{w_overall:.1f}"

@st.cache_data
def cached_schedule(scenario_id, weights_key, ind, op, ov):
    sc = copy.deepcopy(all_scenarios[scenario_id])
    sc.weights = {"individual": ind, "operator": op, "overall": ov}
    return run_scheduler(sc)

result: ScheduleResult = cached_schedule(
    selected_id, weights_key, w_individual, w_operator, w_overall
)


# ── Summary stats ─────────────────────────────────────────────────────────────
st.markdown('<div class="cs-section">03 · Summary</div>', unsafe_allow_html=True)

bk_buses = [r for r in result.bus_results if r.direction == "BK"]
kb_buses = [r for r in result.bus_results if r.direction == "KB"]

total_wait  = result.total_wait_minutes
max_wait    = result.max_individual_wait
avg_journey = sum(r.total_journey_min for r in result.bus_results) / max(len(result.bus_results), 1)
ops = list(set(b.operator for b in scenario.buses))

stat_html = '<div class="cs-stat-grid">'
stat_html += f'''
<div class="cs-stat cs-stat-accent">
    <div class="cs-stat-val">{len(result.bus_results)}</div>
    <div class="cs-stat-label">Buses Scheduled</div>
</div>
<div class="cs-stat cs-stat-warn">
    <div class="cs-stat-val">{fmt_min(total_wait)}</div>
    <div class="cs-stat-label">Total Wait</div>
</div>
<div class="cs-stat cs-stat-info">
    <div class="cs-stat-val">{fmt_min(max_wait)}</div>
    <div class="cs-stat-label">Max Individual Wait</div>
</div>
<div class="cs-stat cs-stat-ok">
    <div class="cs-stat-val">{fmt_min(avg_journey)}</div>
    <div class="cs-stat-label">Avg Journey Time</div>
</div>
'''
for op in sorted(ops):
    op_wait = result.operator_wait(op)
    stat_html += f'''
<div class="cs-stat" style="border-left:3px solid {OPERATOR_COLORS.get(op,'#aaa')}">
    <div class="cs-stat-val">{fmt_min(op_wait)}</div>
    <div class="cs-stat-label">{op.upper()} avg wait</div>
</div>'''

stat_html += '</div>'
st.markdown(stat_html, unsafe_allow_html=True)


# ── Scenario input view ───────────────────────────────────────────────────────
with st.expander("📋  View Scenario Input Data", expanded=False):
    st.markdown('<div class="cs-section">Buses</div>', unsafe_allow_html=True)
    bus_rows = []
    for b in scenario.buses:
        bus_rows.append({
            "Bus ID": b.id,
            "Operator": b.operator.upper(),
            "Direction": "BLR → KCH" if b.direction == "BK" else "KCH → BLR",
            "Departure": b.departure,
        })
    df_buses = pd.DataFrame(bus_rows)
    st.dataframe(df_buses, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="cs-section">Route Segments</div>', unsafe_allow_html=True)
        seg_rows = [
            {"From": s.from_stop, "To": s.to_stop, "Distance (km)": s.distance_km}
            for s in scenario.route.segments
        ]
        st.dataframe(pd.DataFrame(seg_rows), use_container_width=True, hide_index=True)
    with c2:
        st.markdown('<div class="cs-section">Stations</div>', unsafe_allow_html=True)
        st_rows = [
            {"Station": s.id, "Name": s.name, "Chargers": s.chargers, "Position (km)": s.position_km}
            for s in scenario.route.stations
        ]
        st.dataframe(pd.DataFrame(st_rows), use_container_width=True, hide_index=True)

    st.markdown('<div class="cs-section">Active Weights</div>', unsafe_allow_html=True)
    wt_data = {
        "Weight": ["Individual (bus wait)", "Operator (fleet fairness)", "Overall (throughput)"],
        "Key": ["individual", "operator", "overall"],
        "Value": [w_individual, w_operator, w_overall],
    }
    st.dataframe(pd.DataFrame(wt_data), use_container_width=True, hide_index=True)


# ── Per-bus timetable ─────────────────────────────────────────────────────────
st.markdown('<div class="cs-section">04 · Per-Bus Timetable</div>', unsafe_allow_html=True)

tab_bk, tab_kb, tab_all = st.tabs(["🟦  BLR → KCH", "🟣  KCH → BLR", "All Buses"])

def render_bus_table(buses: list[BusResult], scenario):
    if not buses:
        st.info("No buses in this direction for this scenario.")
        return

    rows = []
    for r in sorted(buses, key=lambda x: x.bus_id):
        dep = minutes_to_hhmm(r.departure_min)
        arr = minutes_to_hhmm(r.arrival_time)
        stops = " → ".join(r.stops_summary()) if r.stops_summary() else "—"
        rows.append({
            "Bus ID": r.bus_id,
            "Operator": r.operator.upper(),
            "Departure": dep,
            "Charging Stops": stops,
            "Total Wait": fmt_min(r.total_wait_min),
            "Journey Time": fmt_min(r.total_journey_min),
            "Arrival": arr,
        })

    df = pd.DataFrame(rows)
    
    # Style the dataframe
    def style_wait(val):
        # Extract number for coloring
        try:
            raw = val.replace("h", "").replace("m", "").strip()
            parts = raw.split()
            total = 0
            for p in parts:
                total += int(p)
            if total == 0: return "color: #68d391"
            if total < 30: return "color: #f6ad55"
            return "color: #fc8181"
        except:
            return ""

    st.dataframe(
        df.style.applymap(style_wait, subset=["Total Wait"]),
        use_container_width=True,
        hide_index=True,
    )

    # Detailed stop timeline
    st.markdown('<div class="cs-section" style="margin-top:1.5rem">Stop-by-Stop Timeline</div>', unsafe_allow_html=True)
    
    for r in sorted(buses, key=lambda x: x.bus_id):
        dep_str  = minutes_to_hhmm(r.departure_min)
        arr_str  = minutes_to_hhmm(r.arrival_time)
        wait_cl  = wait_class(r.total_wait_min)
        op_col   = OPERATOR_COLORS.get(r.operator, "#aaa")

        with st.expander(
            f"{r.bus_id}  ·  {r.operator.upper()}  ·  depart {dep_str}  →  arrive {arr_str}  ·  wait {fmt_min(r.total_wait_min)}"
        ):
            if not r.charging_stops:
                st.markdown("*No charging stops — direct run (range sufficient).*")
            else:
                tl = []
                tl.append({
                    "Event": "🚌 Depart",
                    "Station": "Origin",
                    "Time": dep_str,
                    "Wait": "—",
                    "Charge": "—",
                    "Depart Station": dep_str,
                })
                for cs in r.charging_stops:
                    tl.append({
                        "Event": "⚡ Charge",
                        "Station": cs.station_id,
                        "Time": minutes_to_hhmm(cs.arrival_time),
                        "Wait": fmt_min(cs.wait_time) if cs.wait_time > 0 else "—",
                        "Charge": f"{minutes_to_hhmm(cs.charge_start)} – {minutes_to_hhmm(cs.charge_end)}",
                        "Depart Station": minutes_to_hhmm(cs.charge_end),
                    })
                tl.append({
                    "Event": "🏁 Arrive",
                    "Station": "Destination",
                    "Time": arr_str,
                    "Wait": "—",
                    "Charge": "—",
                    "Depart Station": "—",
                })

                df_tl = pd.DataFrame(tl)
                st.dataframe(df_tl, use_container_width=True, hide_index=True)


with tab_bk:
    render_bus_table(bk_buses, scenario)

with tab_kb:
    render_bus_table(kb_buses, scenario)

with tab_all:
    render_bus_table(result.bus_results, scenario)


# ── Per-station view ──────────────────────────────────────────────────────────
st.markdown('<div class="cs-section">05 · Per-Station Charger Log</div>', unsafe_allow_html=True)

station_ids = [s.id for s in sorted(scenario.route.stations, key=lambda s: s.position_km)]
station_tabs = st.tabs([f"Station {sid}" for sid in station_ids])

for tab, sid in zip(station_tabs, station_ids):
    with tab:
        slots = result.station_log.get(sid, [])
        if not slots:
            st.info(f"No buses charged at Station {sid} in this scenario.")
            continue

        # Station header info
        st_obj = next(s for s in scenario.route.stations if s.id == sid)
        st.markdown(f"""
        <div class="cs-card" style="margin-bottom:1rem">
            <div style="display:flex; gap:2rem; align-items:center;">
                <div>
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:1.1rem; color:#4fd1c5; font-weight:700">
                        {st_obj.name}
                    </div>
                    <div style="font-size:0.75rem; color:#4a5568; margin-top:0.2rem">
                        {st_obj.position_km} km from Bengaluru · {st_obj.chargers} charger(s)
                    </div>
                </div>
                <div>
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:1.5rem; color:#edf2f7; font-weight:700">
                        {len(slots)}
                    </div>
                    <div style="font-size:0.72rem; color:#4a5568; text-transform:uppercase; letter-spacing:0.06em">
                        Buses Served
                    </div>
                </div>
                <div>
                    <div style="font-family:'IBM Plex Mono',monospace; font-size:1.5rem; color:#edf2f7; font-weight:700">
                        {fmt_min(sum(s.wait_time for s in slots))}
                    </div>
                    <div style="font-size:0.72rem; color:#4a5568; text-transform:uppercase; letter-spacing:0.06em">
                        Total Wait
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        slot_rows = []
        for i, slot in enumerate(slots):
            slot_rows.append({
                "#": i + 1,
                "Bus ID": slot.bus_id,
                "Operator": slot.operator.upper(),
                "Charge Start": minutes_to_hhmm(slot.charge_start),
                "Charge End":   minutes_to_hhmm(slot.charge_end),
                "Wait Before":  fmt_min(slot.wait_time) if slot.wait_time > 0 else "—",
            })

        df_slots = pd.DataFrame(slot_rows)
        st.dataframe(df_slots, use_container_width=True, hide_index=True)

        # Visual timeline bar
        if slots:
            st.markdown('<div class="cs-section" style="margin-top:1.5rem">Charger Timeline</div>', unsafe_allow_html=True)
            
            min_t = min(s.charge_start for s in slots)
            max_t = max(s.charge_end for s in slots)
            span  = max_t - min_t or 1.0

            bars_html = '<div style="position:relative; height:{}px; background:#0a0c10; border:1px solid #1a2030; border-radius:4px; overflow:hidden; margin-bottom:0.5rem">'.format(
                max(60, len(slots) * 32)
            )

            op_colors = {"kpn": "#2b6cb0", "freshbus": "#276749", "flixbus": "#92400e"}
            op_text   = {"kpn": "#63b3ed", "freshbus": "#68d391",  "flixbus": "#f6ad55"}
            for i, slot in enumerate(slots):
                left  = (slot.charge_start - min_t) / span * 100
                width = (slot.charge_end - slot.charge_start) / span * 100
                top   = i * 32 + 4
                bg    = op_colors.get(slot.operator, "#2d3748")
                tc    = op_text.get(slot.operator, "#eee")
                bars_html += f'''
                <div style="position:absolute; left:{left:.2f}%; width:{width:.2f}%; top:{top}px; height:24px;
                            background:{bg}; border-radius:3px; display:flex; align-items:center; padding:0 6px;
                            overflow:hidden; white-space:nowrap;">
                    <span style="font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:{tc}; font-weight:600">
                        {slot.bus_id}
                    </span>
                </div>'''

                if slot.wait_time > 0.5:
                    wait_left  = (slot.charge_start - slot.wait_time - min_t) / span * 100
                    wait_width = slot.wait_time / span * 100
                    bars_html += f'''
                    <div style="position:absolute; left:{wait_left:.2f}%; width:{wait_width:.2f}%; top:{top}px; height:24px;
                                background:rgba(252,129,129,0.15); border:1px solid rgba(252,129,129,0.3); border-radius:3px;">
                    </div>'''

            bars_html += "</div>"

            # Time axis labels
            time_labels = '<div style="display:flex; justify-content:space-between; font-family:\'IBM Plex Mono\',monospace; font-size:0.65rem; color:#4a5568; margin-bottom:1rem">'
            for frac in [0, 0.25, 0.5, 0.75, 1.0]:
                t = min_t + frac * span
                time_labels += f'<span>{minutes_to_hhmm(t)}</span>'
            time_labels += '</div>'

            legend_html = '<div style="display:flex; gap:1rem; margin-bottom:0.5rem">'
            for op in sorted(set(s.operator for s in slots)):
                op_color = op_text.get(op, "#eee")
                op_bg = op_colors.get(op, "#555")
                legend_html += (
                    f'<span style="display:flex;align-items:center;gap:4px;font-family:IBM Plex Mono,monospace;font-size:0.65rem;color:{op_color}">'
                    f'<span style="width:10px;height:10px;background:{op_bg};border-radius:2px;display:inline-block"></span>'
                    f'{op.upper()}</span>'
                )
            legend_html += (
                '<span style="display:flex;align-items:center;gap:4px;font-family:IBM Plex Mono,monospace;font-size:0.65rem;color:#fc8181">'
                '<span style="width:10px;height:10px;background:rgba(252,129,129,0.15);border:1px solid rgba(252,129,129,0.3);border-radius:2px;display:inline-block"></span>'
                'WAIT</span>'
            )
            legend_html += '</div>'

            st.markdown(legend_html, unsafe_allow_html=True)
            st.markdown(bars_html, unsafe_allow_html=True)
            st.markdown(time_labels, unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="border-top:1px solid #1e2530; margin-top:3rem; padding-top:1.5rem; 
            font-family:'IBM Plex Mono',monospace; font-size:0.65rem; color:#2d3748;
            display:flex; justify-content:space-between; align-items:center;">
    <span>ChargeSched · BLR–KCH Corridor Scheduler</span>
    <span>Python · Streamlit · Priority-Queue Engine</span>
</div>
""", unsafe_allow_html=True)
