"""Spike S5 (throwaway): independent validator for a plan written by common.plan_output.

Deliberately does not reuse common.schedule: it re-reads the fixture JSON and checks the
written events against the rules. Returns a list of violations (empty means valid) and the
plan's metrics.
"""


def check(fx, plan):
    errors = []
    idx = {n["id"]: i for i, n in enumerate(fx["nodes"])}
    nodes = fx["nodes"]
    T = fx["travel_minutes"]
    meals = {m["name"]: m for m in fx["meals"]}
    seen = set()
    travel_total = 0
    busy = 0
    planned_minutes = 0
    if len(plan["days"]) != len(fx["days"]):
        errors.append("day count differs")
    for spec, day in zip(fx["days"], plan["days"]):
        tag = f"day {spec['day']}"
        ev = day["events"]
        if ev is None:
            errors.append(f"{tag}: no schedule")
            continue
        if ev[0]["type"] != "start":
            errors.append(f"{tag}: does not begin with start")
        loc = None if spec["start"] is None else idx[spec["start"]]
        t = ev[0]["time"]
        last_meal_end = t
        end_of_day = t
        if t < spec.get("earliest_start", fx["day_start"]):
            errors.append(f"{tag}: starts too early")
        meal_count = {name: 0 for name in meals}
        # t = when the traveller is free at `loc`; meals since then may be eaten anywhere on
        # the way to the next located item, so that item needs travel + those meals after t.
        pending_meal_min = 0
        for e in ev[1:]:
            if e["type"] == "meal":
                m = meals.get(e["name"])
                if m is None:
                    errors.append(f"{tag}: unknown meal")
                    continue
                meal_count[e["name"]] += 1
                if not (m["earliest"] <= e["start"] <= m["latest"]):
                    errors.append(f"{tag}: {e['name']} outside its window")
                if e["end"] - e["start"] != m["duration"]:
                    errors.append(f"{tag}: {e['name']} wrong duration")
                if e["start"] < max(t, last_meal_end):
                    errors.append(f"{tag}: {e['name']} overlaps another item")
                last_meal_end = e["end"]
                pending_meal_min += m["duration"]
                busy += m["duration"]
                end_of_day = max(end_of_day, e["end"])
                continue
            if e["type"] == "visit":
                v = idx[e["id"]]
                n = nodes[v]
                if n["kind"] != "visit":
                    errors.append(f"{tag}: {e['id']} is not a visit")
                if e["id"] in seen:
                    errors.append(f"{tag}: {e['id']} visited twice")
                seen.add(e["id"])
                if spec["city"] is not None and n["city"] != spec["city"]:
                    errors.append(f"{tag}: {e['id']} outside the day's city")
                if e["end"] - e["start"] != n["duration"]:
                    errors.append(f"{tag}: {e['id']} wrong duration")
                arrive = e["start"]
                busy += n["duration"]
            elif e["type"] == "end":
                v = idx[e["node"]]
                if v != (None if spec["end"] is None else idx[spec["end"]]):
                    errors.append(f"{tag}: wrong end node")
                arrive = e["time"]
            else:
                errors.append(f"{tag}: unknown event {e['type']}")
                continue
            need = 0 if loc is None else T[loc][v]
            if arrive < t + need + pending_meal_min or arrive < last_meal_end:
                errors.append(f"{tag}: {e.get('id', e.get('node'))} reached too early")
            travel_total += need
            busy += need
            pending_meal_min = 0
            t = e["end"] if e["type"] == "visit" else e["time"]
            loc = v
            end_of_day = max(end_of_day, t)
        if spec["end"] is not None and ev[-1]["type"] != "end" and not any(
                x["type"] == "end" for x in ev):
            errors.append(f"{tag}: never returns to the end node")
        for name, c in meal_count.items():
            if c != 1:
                errors.append(f"{tag}: {name} count {c}")
        if end_of_day > fx["day_end"]:
            errors.append(f"{tag}: ends after day window")
        planned_minutes += busy
        busy = 0
    pen = sum(2 * n["score"] for n in nodes if n["kind"] == "visit" and n["id"] not in seen)
    day_window = (fx["day_end"] - fx["day_start"]) * len(fx["days"])
    metrics = {
        "visits": len(seen),
        "score": sum(n["score"] for n in nodes if n["id"] in seen),
        "travel_min": travel_total,
        "objective": travel_total + pen,
        "travel_share": round(travel_total / planned_minutes, 3) if planned_minutes else None,
        "utilisation": round(planned_minutes / day_window, 3),
    }
    return errors, metrics
