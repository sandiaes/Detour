"""Spike S5 (throwaway): problem definition, schedule rule, objective and plan output.

Both sequencers optimise the same objective:
    total travel minutes + sum over dropped visits of DROP_WEIGHT x score
subject to: day window 09:00-21:00 (later start on a move day), one lunch and one dinner per day inside their start
windows, at most one visit per place, visits only on days allowed for their city.

Meals are reserved time blocks without a location (the restaurant is chosen afterwards, as in
architecture.md section 5.2 step 5). A meal may be taken while moving between two items, which
is the same rule OR-Tools uses for vehicle breaks.

The schedule of a fixed visit order is computed by `schedule()`: every item starts as early as
possible. Both sequencers report their result through it, so their output format and times are
identical in kind. The validator (validate.py) re-checks the result independently.
"""
import hashlib
import json

DROP_WEIGHT = 2   # minutes of travel the plan would accept to include one point of score


class Problem:
    def __init__(self, fx):
        self.name = fx["name"]
        self.nodes = fx["nodes"]
        self.index = {n["id"]: i for i, n in enumerate(self.nodes)}
        self.T = fx["travel_minutes"]
        self.day_start = fx["day_start"]
        self.day_end = fx["day_end"]
        self.meals = sorted(((m["earliest"], m["latest"], m["duration"], m["name"])
                             for m in fx["meals"]))
        self.days = []
        for d in fx["days"]:
            self.days.append({
                "day": d["day"], "city": d["city"],
                "start": None if d["start"] is None else self.index[d["start"]],
                "end": None if d["end"] is None else self.index[d["end"]],
                "earliest": d.get("earliest_start", self.day_start),
            })
        self.visits = [i for i, n in enumerate(self.nodes) if n["kind"] == "visit"]
        self.dur = [n.get("duration", 0) for n in self.nodes]
        self.pen = [DROP_WEIGHT * n["score"] if n["kind"] == "visit" else 0
                    for n in self.nodes]
        self.allowed = {}
        for v in self.visits:
            city = self.nodes[v]["city"]
            self.allowed[v] = [k for k, d in enumerate(self.days)
                               if d["city"] is None or d["city"] == city]


def load(path):
    with open(path, encoding="utf-8") as f:
        return Problem(json.load(f))


def travel(p, a, b):
    """Travel minutes between node indexes; None stands for a free day start or end."""
    if a is None or b is None:
        return 0
    return p.T[a][b]


def schedule(p, k, route, detail=False):
    """Earliest-start schedule of day k visiting `route` (node indexes) in order.

    Returns None if infeasible, else (finish, travel_minutes, events). `finish` is the time
    the day ends (last arrival, visit or meal). Meals are inserted greedily: at the first
    moment their window is open; a meal that would force a wait is deferred past the next
    visit when that keeps it inside its window.
    """
    day = p.days[k]
    meals = p.meals
    mi = 0
    cur = day["earliest"]
    loc = day["start"]
    total = 0
    events = [] if detail else None
    if detail:
        events.append({"type": "start", "node": None if loc is None else p.nodes[loc]["id"],
                       "time": cur})
    seq = list(route)
    has_end = day["end"] is not None
    if has_end:
        seq.append(day["end"])
    n = len(route)
    for pos in range(len(seq) + (0 if has_end else 1)):
        is_last = pos >= n
        node = seq[pos] if pos < len(seq) else None
        rem = travel(p, loc, node)
        total += rem
        while mi < len(meals):
            e, latest, d, name = meals[mi]
            if cur > latest:
                return None
            if e <= cur + rem:                      # starts during this move, no waiting
                start = max(cur, e)
                rem -= start - cur
                cur = start + d
            elif not is_last and cur + rem + p.dur[node] <= latest:
                break                                # defer past the next visit
            else:                                    # wait for the window to open
                start = e
                rem = 0
                cur = start + d
            if detail:
                events.append({"type": "meal", "name": name, "start": cur - d, "end": cur})
            mi += 1
        cur += rem
        if node is None:
            break
        if pos < n:
            start = cur
            cur += p.dur[node]
            if detail:
                events.append({"type": "visit", "id": p.nodes[node]["id"],
                               "start": start, "end": cur})
            loc = node
        else:
            if detail:
                events.append({"type": "end", "node": p.nodes[node]["id"], "time": cur})
            loc = node
    if mi < len(meals) or cur > p.day_end:
        return None
    if detail:
        events.sort(key=lambda ev: (ev.get("start", ev.get("time")),
                                    0 if ev["type"] == "start" else 2 if ev["type"] == "end"
                                    else 1))
    return cur, total, events


def objective(p, routes):
    used = {v for r in routes for v in r}
    trav = 0
    for k, r in enumerate(routes):
        res = schedule(p, k, r)
        if res is None:
            return None
        trav += res[1]
    return trav + sum(p.pen[v] for v in p.visits if v not in used)


def plan_output(p, routes):
    """Canonical plan: what a golden test would compare byte for byte."""
    days = []
    for k, r in enumerate(routes):
        res = schedule(p, k, r, detail=True)
        days.append({"day": p.days[k]["day"],
                     "events": None if res is None else res[2]})
    return {"fixture": p.name, "days": days}


def plan_hash(plan):
    text = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]
