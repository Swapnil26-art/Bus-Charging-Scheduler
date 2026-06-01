"""
Bus Charging Scheduler Engine
==============================
Core scheduling logic. Extensible, weight-tunable, rule-based.

Design principles:
  - Weights live in one dict — change one value, behavior changes everywhere.
  - Rules are plain functions (bus, state) → float. Add a new rule by writing
    one function and registering it; the engine finds the rest automatically.
  - Growing the world (more stations, chargers, routes, operators) requires
    no code changes — just richer scenario JSON.
"""

from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Station:
    id: str
    name: str
    chargers: int
    position_km: float          # distance from route origin


@dataclass
class Segment:
    from_stop: str
    to_stop: str
    distance_km: float


@dataclass
class Route:
    id: str
    name: str
    origin: str
    destination: str
    stations: list[Station]
    segments: list[Segment]
    total_distance_km: float


@dataclass
class Physics:
    battery_range_km: float
    charge_duration_min: float
    speed_kmh: float

    def travel_minutes(self, km: float) -> float:
        return (km / self.speed_kmh) * 60.0


@dataclass
class Bus:
    id: str
    operator: str
    direction: str              # "BK" = Bengaluru→Kochi, "KB" = Kochi→Bengaluru
    departure: str              # "HH:MM" string


@dataclass
class Scenario:
    id: str
    name: str
    description: str
    route: Route
    physics: Physics
    weights: dict[str, float]
    buses: list[Bus]


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class ChargingStop:
    station_id: str
    arrival_time: float         # absolute minutes from midnight
    wait_time: float            # minutes waited in queue
    charge_start: float
    charge_end: float


@dataclass
class BusResult:
    bus_id: str
    operator: str
    direction: str
    departure_min: float
    charging_stops: list[ChargingStop]
    arrival_time: float         # at destination
    total_wait_min: float
    total_journey_min: float

    def stops_summary(self) -> list[str]:
        return [s.station_id for s in self.charging_stops]


@dataclass
class StationSlot:
    """One bus's usage of a charger."""
    bus_id: str
    operator: str
    charge_start: float
    charge_end: float
    wait_time: float


@dataclass
class ScheduleResult:
    scenario_id: str
    bus_results: list[BusResult]
    station_log: dict[str, list[StationSlot]]   # station_id → ordered slots

    # Derived metrics
    @property
    def total_wait_minutes(self) -> float:
        return sum(r.total_wait_min for r in self.bus_results)

    @property
    def max_individual_wait(self) -> float:
        return max((r.total_wait_min for r in self.bus_results), default=0)

    def operator_wait(self, op: str) -> float:
        buses = [r for r in self.bus_results if r.operator == op]
        return sum(r.total_wait_min for r in buses) / max(len(buses), 1)


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------

def load_scenario(path: str | Path) -> Scenario:
    with open(path) as f:
        d = json.load(f)

    r = d["route"]
    stations = [
        Station(
            id=s["id"],
            name=s["name"],
            chargers=s["chargers"],
            position_km=s["position_km"],
        )
        for s in r["stations"]
    ]
    segments = [
        Segment(seg["from"], seg["to"], seg["distance_km"])
        for seg in r["segments"]
    ]
    route = Route(
        id=r["id"],
        name=r["name"],
        origin=r["endpoints"]["origin"],
        destination=r["endpoints"]["destination"],
        stations=stations,
        segments=segments,
        total_distance_km=r["total_distance_km"],
    )

    ph = d["physics"]
    physics = Physics(
        battery_range_km=ph["battery_range_km"],
        charge_duration_min=ph["charge_duration_min"],
        speed_kmh=ph["speed_kmh"],
    )

    buses = [
        Bus(
            id=b["id"],
            operator=b["operator"],
            direction=b["direction"],
            departure=b["departure"],
        )
        for b in d["buses"]
    ]

    return Scenario(
        id=d["id"],
        name=d["name"],
        description=d["description"],
        route=route,
        physics=physics,
        weights=d["weights"],
        buses=buses,
    )


def load_all_scenarios(scenarios_dir: str | Path) -> dict[str, Scenario]:
    p = Path(scenarios_dir)
    scenarios: dict[str, Scenario] = {}
    for f in sorted(p.glob("scenario_*.json")):
        s = load_scenario(f)
        scenarios[s.id] = s
    return scenarios


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def hhmm_to_minutes(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def minutes_to_hhmm(minutes: float) -> str:
    total = int(round(minutes))
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"


# ---------------------------------------------------------------------------
# Route geometry helpers
# ---------------------------------------------------------------------------

def get_ordered_stations(scenario: Scenario, direction: str) -> list[Station]:
    """
    Return stations in the order a bus travelling in `direction` visits them.
    BK = Bengaluru→Kochi (ascending position)
    KB = Kochi→Bengaluru (descending position)
    """
    stations = sorted(scenario.route.stations, key=lambda s: s.position_km)
    if direction == "KB":
        stations = list(reversed(stations))
    return stations


def cumulative_distances_from_origin(scenario: Scenario, direction: str) -> dict[str, float]:
    """
    Return a dict: stop_name → km from origin for a bus going `direction`.
    Origin is always distance=0, destination is total_distance.
    Intermediate stations are at their position_km (BK) or mirrored (KB).
    """
    total = scenario.route.total_distance_km
    result: dict[str, float] = {}

    if direction == "BK":
        result[scenario.route.origin] = 0.0
        for st in scenario.route.stations:
            result[st.id] = st.position_km
        result[scenario.route.destination] = total
    else:
        # Mirror: position from Kochi end = total - position_km
        result[scenario.route.destination] = 0.0     # Bengaluru is destination when going KB
        for st in scenario.route.stations:
            result[st.id] = total - st.position_km
        result[scenario.route.origin] = total         # Kochi is origin when going KB

    return result


def choose_charging_stations(scenario: Scenario, direction: str) -> list[str]:
    """
    Choose which stations a bus must stop at given range constraints.
    
    Strategy: greedy — at each point, go as far as possible without
    exceeding range, then charge. This minimises stops while guaranteeing
    feasibility.

    Returns list of station IDs in travel order.
    """
    ph = scenario.physics
    stations = get_ordered_stations(scenario, direction)
    dist = cumulative_distances_from_origin(scenario, direction)
    total = scenario.route.total_distance_km

    selected: list[str] = []
    last_charge_km = 0.0           # km from bus's origin where it last charged (starts full)

    for st in stations:
        st_km = dist[st.id]
        # distance from last charge to this station
        to_station = st_km - last_charge_km

        # distance from this station to end of route (destination)
        # needed to know if we can skip this station
        remaining_after = total - st_km

        if to_station > ph.battery_range_km:
            # We can't even reach this station — invalid plan (shouldn't happen
            # with correct data, but guard anyway)
            selected.append(st.id)
            last_charge_km = st_km
            continue

        # Can we reach the next viable charge point (or destination) without stopping here?
        # Find the nearest subsequent station (or destination)
        next_stations = [s for s in stations if dist[s.id] > st_km]
        
        if not next_stations:
            # This is the last station before destination
            to_dest = total - st_km
            if last_charge_km + ph.battery_range_km < total:
                # We must charge here to reach destination
                selected.append(st.id)
                last_charge_km = st_km
            # else we can reach destination without charging here — skip
        else:
            next_km = dist[next_stations[0].id]
            to_next = next_km - last_charge_km   # distance from last charge to next station

            if to_next > ph.battery_range_km or (remaining_after > ph.battery_range_km and len(next_stations) == 1):
                # Must charge here — skipping means we either can't reach next or can't finish
                must_stop = True
                # More precisely: check if skipping this station makes the gap to next charge impossible
                if to_next > ph.battery_range_km:
                    must_stop = True
                else:
                    # Check further: from next station, can we reach the destination?
                    # This is complex multi-hop — use conservative rule: if remaining > range, we need more stops
                    # Check if we can cover the rest with the remaining stations
                    remaining_stations = next_stations[1:]
                    must_stop = not _can_complete(last_charge_km, total, [dist[s.id] for s in next_stations], ph.battery_range_km)
                
                if must_stop:
                    selected.append(st.id)
                    last_charge_km = st_km

    # Validate: make sure the plan is actually feasible
    stops = _validate_and_fix(selected, direction, scenario)
    return stops


def _can_complete(current_km: float, total_km: float, station_kms: list[float], range_km: float) -> bool:
    """Check if we can complete the route from current_km given available station kms."""
    pos = current_km
    for skm in station_kms:
        if skm - pos > range_km:
            return False
        pos = skm  # charge here
    return total_km - pos <= range_km


def _validate_and_fix(
    selected: list[str],
    direction: str,
    scenario: Scenario,
) -> list[str]:
    """
    Full validation pass: ensure no gap exceeds battery range.
    If a gap is too large, insert the missing station.
    """
    ph = scenario.physics
    dist = cumulative_distances_from_origin(scenario, direction)
    total = scenario.route.total_distance_km
    all_stations = get_ordered_stations(scenario, direction)
    all_kms = {s.id: dist[s.id] for s in all_stations}

    # Build checkpoints: origin (0) + selected + destination (total)
    result = list(selected)

    def get_km(sid: str) -> float:
        return all_kms.get(sid, 0.0)

    changed = True
    while changed:
        changed = False
        checkpoints = [0.0] + [get_km(s) for s in result] + [total]
        for i in range(len(checkpoints) - 1):
            gap = checkpoints[i + 1] - checkpoints[i]
            if gap > ph.battery_range_km + 0.001:
                # Need to insert a station in this gap
                gap_start = checkpoints[i]
                gap_end = checkpoints[i + 1]
                candidates = [
                    s for s in all_stations
                    if gap_start < get_km(s.id) < gap_end and s.id not in result
                ]
                if candidates:
                    # Pick the farthest candidate within range from gap_start
                    valid = [c for c in candidates if get_km(c.id) - gap_start <= ph.battery_range_km]
                    if valid:
                        best = max(valid, key=lambda c: get_km(c.id))
                        # Insert in correct order
                        result.append(best.id)
                        result.sort(key=lambda sid: get_km(sid))
                        changed = True
                        break

    return result


# ---------------------------------------------------------------------------
# Soft rule framework
# ---------------------------------------------------------------------------

"""
A soft rule is a function:
    rule(bus, bus_state, station, queue_wait_minutes, context) -> float

where the float is an additional COST (higher = worse). The scheduler
minimises cost. Rules are registered in SOFT_RULES dict and weighted.
"""

@dataclass
class BusState:
    """Live state of a bus during scheduling."""
    bus_id: str
    operator: str
    direction: str
    current_time_min: float      # current absolute time (minutes from midnight)
    total_wait_min: float        # accumulated wait so far


@dataclass
class SchedulerContext:
    """Shared context visible to all rules."""
    weights: dict[str, float]
    all_bus_states: dict[str, BusState]
    operator_buses: dict[str, list[str]]    # operator → list of bus IDs
    scenario: Scenario


# --- Built-in soft rules ---

def rule_individual_wait(
    bus: Bus,
    state: BusState,
    station_id: str,
    extra_wait: float,
    ctx: SchedulerContext,
) -> float:
    """Penalise this individual bus waiting more."""
    return extra_wait


def rule_operator_fairness(
    bus: Bus,
    state: BusState,
    station_id: str,
    extra_wait: float,
    ctx: SchedulerContext,
) -> float:
    """
    Penalise if this operator's fleet already has high average wait.
    Adding more wait to a disadvantaged operator is extra costly.
    """
    op_buses = ctx.operator_buses.get(bus.operator, [])
    if not op_buses:
        return 0.0
    op_states = [ctx.all_bus_states[bid] for bid in op_buses if bid in ctx.all_bus_states]
    if not op_states:
        return 0.0
    avg_op_wait = sum(s.total_wait_min for s in op_states) / len(op_states)
    # Cost is proportional to how much this bus adds to an already-waiting fleet
    return avg_op_wait * 0.5 + extra_wait


def rule_overall_throughput(
    bus: Bus,
    state: BusState,
    station_id: str,
    extra_wait: float,
    ctx: SchedulerContext,
) -> float:
    """Penalise total system time — any wait is bad for overall throughput."""
    return extra_wait * 0.8


# Registry: name → (rule_function, weight_key)
# weight_key maps to scenario.weights dict
SOFT_RULES: dict[str, tuple[Any, str]] = {
    "individual_wait":   (rule_individual_wait,    "individual"),
    "operator_fairness": (rule_operator_fairness,  "operator"),
    "overall_throughput":(rule_overall_throughput, "overall"),
}


def compute_cost(
    bus: Bus,
    state: BusState,
    station_id: str,
    extra_wait: float,
    ctx: SchedulerContext,
) -> float:
    """Compute the weighted cost of assigning `extra_wait` to `bus` at `station_id`."""
    total_cost = 0.0
    for rule_name, (rule_fn, weight_key) in SOFT_RULES.items():
        w = ctx.weights.get(weight_key, 1.0)
        c = rule_fn(bus, state, station_id, extra_wait, ctx)
        total_cost += w * c
    return total_cost


# ---------------------------------------------------------------------------
# Charger queue simulation
# ---------------------------------------------------------------------------

@dataclass
class ChargerQueue:
    """
    Simulates a single physical charger at a station.
    Tracks when it next becomes free.
    """
    station_id: str
    slots: list[StationSlot] = field(default_factory=list)
    next_free_at: float = 0.0       # absolute minutes

    def schedule(self, bus_id: str, operator: str, arrival_time: float, charge_duration: float) -> StationSlot:
        start = max(arrival_time, self.next_free_at)
        wait = start - arrival_time
        end = start + charge_duration
        slot = StationSlot(
            bus_id=bus_id,
            operator=operator,
            charge_start=start,
            charge_end=end,
            wait_time=wait,
        )
        self.slots.append(slot)
        self.next_free_at = end
        return slot


# ---------------------------------------------------------------------------
# Main scheduler
# ---------------------------------------------------------------------------

def run_scheduler(scenario: Scenario) -> ScheduleResult:
    """
    Full scheduling run for a scenario.

    Algorithm:
    1. Pre-compute each bus's charging plan (which stations to stop at).
    2. For each station, maintain a charger queue (one per charger).
    3. Process buses in event order — earliest arrival at a station goes first
       when there's no contention. When multiple buses arrive at roughly the
       same time (within threshold), use weighted cost to decide order.
    4. Record full timeline per bus; accumulate station logs.
    """
    ph = scenario.physics

    # Build operator map
    operator_buses: dict[str, list[str]] = {}
    for bus in scenario.buses:
        operator_buses.setdefault(bus.operator, []).append(bus.id)

    # Pre-compute charging plans
    bus_plans: dict[str, list[str]] = {}
    for bus in scenario.buses:
        bus_plans[bus.id] = choose_charging_stations(scenario, bus.direction)

    # Station charger queues (one ChargerQueue per physical charger)
    # For multi-charger stations we'd have a list; for now 1 charger = 1 queue
    station_queues: dict[str, list[ChargerQueue]] = {}
    for st in scenario.route.stations:
        station_queues[st.id] = [ChargerQueue(station_id=st.id) for _ in range(st.chargers)]

    # Live bus states
    bus_states: dict[str, BusState] = {}
    for bus in scenario.buses:
        dep_min = hhmm_to_minutes(bus.departure)
        bus_states[bus.id] = BusState(
            bus_id=bus.id,
            operator=bus.operator,
            direction=bus.direction,
            current_time_min=dep_min,
            total_wait_min=0.0,
        )

    ctx = SchedulerContext(
        weights=scenario.weights,
        all_bus_states=bus_states,
        operator_buses=operator_buses,
        scenario=scenario,
    )

    # Compute arrival times at each station for each bus (ignoring waits for planning)
    # We'll use a simulation approach: process events chronologically.

    # Build per-bus geometry
    dist_maps: dict[str, dict[str, float]] = {}
    for bus in scenario.buses:
        dist_maps[bus.id] = cumulative_distances_from_origin(scenario, bus.direction)

    # Event-driven simulation
    # Each event: (time, bus_id, station_id)
    # We process events in time order; when a bus finishes charging, we fire the next event.

    bus_by_id = {bus.id: bus for bus in scenario.buses}
    bus_results: dict[str, BusResult] = {}

    # We'll simulate bus by bus but handle contention correctly using
    # a greedy contention-resolution step at each station.

    # Instead: simulate all buses simultaneously using a priority queue of events.
    # Event types: ARRIVE_STATION, FINISH_CHARGE → DEPART_STATION

    # Each bus's journey:
    #   departure → travel to station_1 → (wait?) → charge → travel to station_2 → ... → arrive destination

    # We use a min-heap: (event_time, sequence_counter, bus_id, event_type, station_id)
    ARRIVE = "ARRIVE"
    DONE   = "DONE"

    event_counter = 0
    heap: list[tuple] = []

    def push_event(time: float, bus_id: str, event_type: str, station_id: str):
        nonlocal event_counter
        heapq.heappush(heap, (time, event_counter, bus_id, event_type, station_id))
        event_counter += 1

    # Initialise: for each bus, schedule arrival at first charging station
    bus_stop_index: dict[str, int] = {bus.id: 0 for bus in scenario.buses}
    bus_charging_stops: dict[str, list[ChargingStop]] = {bus.id: [] for bus in scenario.buses}

    for bus in scenario.buses:
        plan = bus_plans[bus.id]
        if not plan:
            # Bus needs no charging stops — compute direct arrival
            dep_min = hhmm_to_minutes(bus.departure)
            total_travel = ph.travel_minutes(scenario.route.total_distance_km)
            arrival = dep_min + total_travel
            bus_results[bus.id] = BusResult(
                bus_id=bus.id,
                operator=bus.operator,
                direction=bus.direction,
                departure_min=dep_min,
                charging_stops=[],
                arrival_time=arrival,
                total_wait_min=0.0,
                total_journey_min=total_travel,
            )
            continue

        dep_min = hhmm_to_minutes(bus.departure)
        first_station_id = plan[0]
        first_station_km = dist_maps[bus.id][first_station_id]
        travel_to_first = ph.travel_minutes(first_station_km)
        arrive_first = dep_min + travel_to_first
        push_event(arrive_first, bus.id, ARRIVE, first_station_id)

    # Contention window: buses arriving within this many minutes are considered "simultaneous"
    # and the best is chosen by cost function.
    CONTENTION_WINDOW = 2.0

    # Station pending arrivals buffer: station_id → list of (arrive_time, bus_id)
    # We flush when the next event is outside the window.
    station_pending: dict[str, list[tuple[float, str]]] = {st.id: [] for st in scenario.route.stations}

    processed_buses_at_station: dict[str, set] = {st.id: set() for st in scenario.route.stations}

    def get_free_charger(station_id: str) -> ChargerQueue:
        """Return the charger that becomes free soonest."""
        return min(station_queues[station_id], key=lambda q: q.next_free_at)

    def projected_wait(station_id: str, arrival_time: float) -> float:
        q = get_free_charger(station_id)
        return max(0.0, q.next_free_at - arrival_time)

    def schedule_bus_at_station(bus_id: str, station_id: str, arrival_time: float):
        """
        Schedule bus on the best available charger and advance its journey.
        """
        bus = bus_by_id[bus_id]
        state = bus_states[bus_id]
        plan = bus_plans[bus_id]
        stop_idx = bus_stop_index[bus_id]

        charger = get_free_charger(station_id)
        slot = charger.schedule(bus_id, bus.operator, arrival_time, ph.charge_duration_min)

        cs = ChargingStop(
            station_id=station_id,
            arrival_time=arrival_time,
            wait_time=slot.wait_time,
            charge_start=slot.charge_start,
            charge_end=slot.charge_end,
        )
        bus_charging_stops[bus_id].append(cs)

        # Update bus state
        state.current_time_min = slot.charge_end
        state.total_wait_min += slot.wait_time

        # Schedule next event
        next_stop_idx = stop_idx + 1
        bus_stop_index[bus_id] = next_stop_idx

        if next_stop_idx < len(plan):
            next_station_id = plan[next_stop_idx]
            curr_km = dist_maps[bus_id][station_id]
            next_km = dist_maps[bus_id][next_station_id]
            travel = ph.travel_minutes(next_km - curr_km)
            arrive_next = slot.charge_end + travel
            push_event(arrive_next, bus_id, ARRIVE, next_station_id)
        else:
            # No more charging stops — travel to destination
            last_km = dist_maps[bus_id][station_id]
            total_km = scenario.route.total_distance_km
            travel = ph.travel_minutes(total_km - last_km)
            arrive_dest = slot.charge_end + travel
            push_event(arrive_dest, bus_id, DONE, "destination")

    # Process events
    while heap:
        event_time, _, bus_id, event_type, station_id = heapq.heappop(heap)

        if bus_id not in bus_by_id:
            continue  # ghost event; skip

        if event_type == DONE:
            bus = bus_by_id[bus_id]
            dep = hhmm_to_minutes(bus.departure)
            stops = bus_charging_stops[bus_id]
            total_wait = sum(s.wait_time for s in stops)
            bus_results[bus_id] = BusResult(
                bus_id=bus_id,
                operator=bus.operator,
                direction=bus.direction,
                departure_min=dep,
                charging_stops=stops,
                arrival_time=event_time,
                total_wait_min=total_wait,
                total_journey_min=event_time - dep,
            )
            continue

        if event_type == ARRIVE:
            if bus_id in processed_buses_at_station[station_id]:
                continue  # already handled (duplicate event guard)

            # Add to station pending buffer
            station_pending[station_id].append((event_time, bus_id))

            # Peek: are there more arrivals to this station within the contention window?
            # We flush when either:
            #   a) The next heap event for this station is beyond the window, OR
            #   b) We have buses waiting for longer than the window

            # Determine flush threshold
            flush_threshold = event_time + CONTENTION_WINDOW

            # Check heap for upcoming arrivals at same station within window
            upcoming_same_station = any(
                ev[2] != bus_id and ev[3] == ARRIVE and ev[4] == station_id and ev[0] <= flush_threshold
                for ev in heap
            )

            if not upcoming_same_station:
                # Flush the pending buffer for this station — resolve contention
                pending = station_pending[station_id]
                if not pending:
                    continue

                # Sort pending by arrival time (earliest first as default)
                pending_sorted = sorted(pending, key=lambda x: x[0])

                # For each bus in pending, compute cost of scheduling it next
                # We process one at a time (greedy): pick lowest cost, schedule, repeat
                while pending_sorted:
                    if len(pending_sorted) == 1:
                        arrive_t, bid = pending_sorted.pop(0)
                        schedule_bus_at_station(bid, station_id, arrive_t)
                        processed_buses_at_station[station_id].add(bid)
                    else:
                        # Multiple buses contending — pick by lowest cost
                        best_cost = float("inf")
                        best_idx = 0
                        for i, (arrive_t, bid) in enumerate(pending_sorted):
                            bus = bus_by_id[bid]
                            state = bus_states[bid]
                            extra_wait = projected_wait(station_id, arrive_t)
                            cost = compute_cost(bus, state, station_id, extra_wait, ctx)
                            if cost < best_cost:
                                best_cost = cost
                                best_idx = i

                        arrive_t, bid = pending_sorted.pop(best_idx)
                        schedule_bus_at_station(bid, station_id, arrive_t)
                        processed_buses_at_station[station_id].add(bid)

                station_pending[station_id] = []

    # Handle any remaining pending buses (edge case: last events in heap)
    for station_id, pending in station_pending.items():
        if pending:
            pending_sorted = sorted(pending, key=lambda x: x[0])
            while pending_sorted:
                arrive_t, bid = pending_sorted.pop(0)
                if bid not in processed_buses_at_station[station_id]:
                    schedule_bus_at_station(bid, station_id, arrive_t)
                    processed_buses_at_station[station_id].add(bid)

    # Handle buses with no charging plan that weren't added yet
    for bus in scenario.buses:
        if bus.id not in bus_results:
            dep_min = hhmm_to_minutes(bus.departure)
            stops = bus_charging_stops.get(bus.id, [])
            total_wait = sum(s.wait_time for s in stops)
            # Compute arrival: departure + travel + wait
            last_km = 0.0
            current_time = dep_min
            dm = dist_maps[bus.id]
            for stop in stops:
                st_km = dm[stop.station_id]
                travel = ph.travel_minutes(st_km - last_km)
                current_time = stop.charge_end
                last_km = st_km
            # Final leg
            remaining_km = scenario.route.total_distance_km - last_km
            arrival = current_time + ph.travel_minutes(remaining_km)
            bus_results[bus.id] = BusResult(
                bus_id=bus.id,
                operator=bus.operator,
                direction=bus.direction,
                departure_min=dep_min,
                charging_stops=stops,
                arrival_time=arrival,
                total_wait_min=total_wait,
                total_journey_min=arrival - dep_min,
            )

    # Build station log (sorted by charge_start)
    station_log: dict[str, list[StationSlot]] = {}
    for st in scenario.route.stations:
        all_slots = []
        for q in station_queues[st.id]:
            all_slots.extend(q.slots)
        station_log[st.id] = sorted(all_slots, key=lambda s: s.charge_start)

    return ScheduleResult(
        scenario_id=scenario.id,
        bus_results=sorted(bus_results.values(), key=lambda r: r.bus_id),
        station_log=station_log,
    )
