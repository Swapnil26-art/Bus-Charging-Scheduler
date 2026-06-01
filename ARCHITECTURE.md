# ARCHITECTURE.md

## Framework Choice: Priority-Queue Event Simulation + Weighted Cost Rules

### What I built

The scheduler is a **discrete-event simulation** driven by a min-heap.  
Every meaningful moment in a bus's journey (arriving at a station, finishing a charge) is an **event** with a timestamp. The engine processes events in chronological order. When multiple buses contend for the same charger within a short time window, a **weighted cost function** decides who goes first.

Soft rules are plain Python functions registered in a dict (`SOFT_RULES`). Each rule takes the current bus, its live state, the station, the projected extra wait, and a shared context object — and returns a float cost. The engine sums all rules' weighted costs and picks the bus with the lowest score.

### Why this approach

| Option | Why I didn't use it |
|---|---|
| ILP / Mixed-integer solver | Correct but brittle. Adding a rule means reformulating the objective. Hard to explain at a code level; heavy dependencies. |
| Greedy FCFS | Simple but weight-unaware. Changing a weight does nothing. |
| Genetic / search heuristic | No convergence guarantee; slow for interactive UI; hard to add hard constraints. |
| **Event sim + cost rules** ✓ | Fast (milliseconds), transparent, extensible by design, weights are first-class citizens. |

The event simulation handles time correctly: a bus can't schedule its second stop until its first charge is done, because the second event fires only after the charger confirms it. This means cascading delays propagate naturally through the simulation with zero special-casing.

---

## Data Structure Design

Each scenario is a self-contained JSON file with six top-level sections:

```
{
  "id", "name", "description",
  "route":   { endpoints, stations[], segments[] },
  "physics": { battery_range_km, charge_duration_min, speed_kmh },
  "weights": { individual, operator, overall, ... },
  "buses":   [ { id, operator, direction, departure } ]
}
```

**Route geometry is data, not code.** Stations carry `position_km` from the Bengaluru end. Direction (BK vs KB) is handled by mirroring positions at runtime — no separate tables for each direction.

**Chargers are a count, not a list.** `"chargers": 2` at a station means two queues, selected greedily. Going from 1 to 2 chargers at any station is a one-character JSON edit.

---

## Anticipated Future Changes — and How the Design Handles Each

| Change | Code change required? | How |
|---|---|---|
| **Change a weight** | No | One value in `scenarios/*.json` or the live UI slider |
| **Add a new soft rule** | Add one function + one dict entry | `SOFT_RULES["my_rule"] = (fn, "weight_key")` |
| **Add a new station** | No | Add to `stations[]` and `segments[]` in JSON |
| **Add chargers to a station** | No | Change `"chargers": 1` to `"chargers": N` |
| **Add a new operator** | No | Just use the new name in bus records |
| **Add priority buses** | Add one rule function | New rule checks `bus.id in ctx.scenario.weights["priority_buses"]` |
| **Multiple routes sharing stations** | Minor | Route gets an `id`; stations carry a `routes[]` list; engine filters by route |
| **Time-of-day electricity pricing** | Add one rule | Rule reads `ctx.scenario` for a cost schedule keyed by hour |
| **Driver shift constraints** | Add one rule + bus field | Rule checks `bus.shift_end_min` vs projected arrival |
| **Varying bus ranges** | No | Move `battery_range_km` from `physics` to each bus record; engine checks `bus.range` |
| **Faster/slower buses** | No | Move `speed_kmh` to each bus record |
| **More buses** | No | Add rows to `buses[]` |
| **More scenarios** | No | Drop a new `scenario_N.json` in `scenarios/`; app autodiscovers |
| **Different segment distances** | No | Edit `segments[]` in JSON |
| **Hard rule: no operator may monopolise a station for >N minutes** | Add guard in `schedule_bus_at_station` | Check charger log before scheduling; reject if constraint violated |
| **Multiple routes** | Minor refactor | Route ID becomes a FK; stations can belong to multiple routes |

### One thing that would require a larger refactor

**Multi-hop shared stations** (a station serves two crossing routes simultaneously). This would need a station registry keyed by `(station_id, route_id)` and conflict detection across routes. The data model supports it (stations already have IDs independent of routes), but the event loop would need a merge step. I'd estimate ~100 lines of new code, zero deletions.

---

## How to Change a Weight

```python
# In scenarios/scenario_4.json — before:
"weights": { "individual": 1.0, "operator": 1.0, "overall": 1.0 }

# After (double the operator weight):
"weights": { "individual": 1.0, "operator": 2.0, "overall": 1.0 }
```

Or use the live sliders in the UI — no file edit needed.

---

## How to Add a New Rule

```python
# scheduler/engine.py

def rule_electricity_cost(bus, state, station_id, extra_wait, ctx):
    """
    Penalise scheduling a charge during expensive peak hours (18:00–22:00).
    Assumes scenario JSON has: "weights": { ..., "electricity": 1.0 }
    """
    charge_hour = (state.current_time_min // 60) % 24
    if 18 <= charge_hour <= 22:
        return 50.0  # penalty in cost units
    return 0.0

# Register — one line:
SOFT_RULES["electricity_cost"] = (rule_electricity_cost, "electricity")
```

Add `"electricity": 1.0` to any scenario's `weights` block. Done.  
The engine automatically includes this rule in cost calculations. Nothing else changes.

---

## Assumptions

1. **Speed is uniform.** All buses travel at `physics.speed_kmh`. No traffic, no variation. Distance-to-time is deterministic.

2. **Charge is always to full.** The spec says this explicitly. A bus leaving a charger always has 240 km range.

3. **Charging time is fixed at 25 min.** No partial charges, no faster chargers.

4. **Origin endpoints are not scheduling concerns.** Bengaluru and Kochi have slow chargers that always fill buses before departure; we assume buses always depart with full charge.

5. **Minimum 2 charging stops per bus.** The route is 540 km, range is 240 km. At least 2 stops are always required. The greedy planner chooses the 2 (or more) stations that satisfy range constraints with minimum stops.

6. **Greedy station selection: go as far as possible.** For each bus, the planner picks the latest-reachable station from the current charge point. This minimises total stops and total charging time.

7. **Contention window of 2 minutes.** Buses arriving within 2 minutes of each other are treated as simultaneous for the purpose of cost-based ordering. This is tunable.

8. **Multi-charger stations use shortest-queue routing.** A bus always goes to the charger that becomes free soonest.

9. **No preemption.** Once a bus starts charging, it charges to full. No priority override mid-charge.

10. **The `"individual"`, `"operator"`, and `"overall"` weight keys are the built-in defaults.** Any new rule adds its own key. Unknown keys in the weights block are silently ignored.

11. **Scenario 3 has 14 buses.** The spec says 20 buses per scenario but Scenario 3 only lists 14 (10 BK + 4 KB). I encoded it exactly as given.
