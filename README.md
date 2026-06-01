# ⚡ ChargeSched — Bus Charging Scheduler

A Streamlit app that schedules charging stops for electric buses on the **Bengaluru → Kochi** corridor.  
Built as a take-home assessment deliverable.

---

## Quick Start

```bash
git clone <your-repo>
cd bus-charging-scheduler

pip install -r requirements.txt
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Changing a Weight

Weights live in **one place** in each scenario JSON file:

```json
// scenarios/scenario_1.json
"weights": {
  "individual": 1.0,   ← penalise a single bus waiting too long
  "operator":   1.0,   ← penalise one operator's fleet being disadvantaged
  "overall":    1.0    ← penalise high total system wait time
}
```

You can also change weights **live** in the UI using the sliders in the Weight Tuner section.  
No code change required. Weight changes take effect immediately.

---

## Adding a New Rule

Define one function in `scheduler/engine.py` and register it:

```python
# scheduler/engine.py

def rule_priority_bus(bus, state, station_id, extra_wait, ctx):
    """Priority buses pay no extra cost — they always jump the queue."""
    priority_ids = ctx.scenario.weights.get("priority_buses", [])
    if bus.id in priority_ids:
        return -9999.0  # make it the most attractive option
    return 0.0

# Register it — one line:
SOFT_RULES["priority_bus"] = (rule_priority_bus, "priority")
```

Then add `"priority": 1.0` to any scenario's `weights` block and a `"priority_buses": ["bus-BK-01"]` field.  
The engine will pick it up automatically. **No other code changes needed.**

---

## Adding a New Scenario

Copy any existing JSON file, change the `id`, `name`, `description`, `buses`, and optionally `weights`.  
Drop it in `scenarios/`. The app auto-discovers all `scenario_*.json` files on startup.

---

## Project Structure

```
bus-charging-scheduler/
├── app.py                    # Streamlit UI
├── requirements.txt
├── README.md
├── ARCHITECTURE.md
├── scheduler/
│   ├── __init__.py
│   └── engine.py             # Scheduling logic (all of it)
└── scenarios/
    ├── scenario_1.json       # Even spacing
    ├── scenario_2.json       # Bunched start
    ├── scenario_3.json       # Asymmetric load
    ├── scenario_4.json       # Operator-heavy
    └── scenario_5.json       # Worst-case convergence
```

---

## Hosting on Streamlit Community Cloud

1. Push this repo to GitHub (public).
2. Go to [share.streamlit.io](https://share.streamlit.io).
3. Click **New app**, select your repo, set `app.py` as the main file.
4. Click **Deploy**. Done.

Streamlit reads `requirements.txt` and installs everything automatically.

---

## Assumptions

See `ARCHITECTURE.md` for the full list.
