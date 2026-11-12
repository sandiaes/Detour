"""Spike S5 (throwaway): the simple heuristic sequencer.

Greedy best-gain insertion followed by deterministic local search (2-opt and relocation
within a day, relocation between days, swapping a planned visit for an unplanned one). Every
loop runs in a fixed order, ties are broken by node identifier, and there is no randomness and
no clock, so the same input gives the same plan on any machine.
"""
from common import objective, schedule, travel

MAX_ROUNDS = 200


def _delta(p, k, route, pos, v):
    day = p.days[k]
    prev = route[pos - 1] if pos > 0 else day["start"]
    nxt = route[pos] if pos < len(route) else day["end"]
    return travel(p, prev, v) + travel(p, v, nxt) - travel(p, prev, nxt)


def _route_travel(p, k, route):
    day = p.days[k]
    seq = [day["start"]] + list(route) + [day["end"]]
    return sum(travel(p, a, b) for a, b in zip(seq, seq[1:]))


def _feasible(p, k, route):
    return schedule(p, k, route) is not None


def _order(p, nodes):
    # higher penalty first, then identifier: a stable, data-only order
    return sorted(nodes, key=lambda v: (-p.pen[v], p.nodes[v]["id"]))


def insert_all(p, routes, unplanned):
    """Repeatedly apply the feasible insertion with the largest objective gain."""
    changed = False
    while True:
        best = None    # (gain, v, k, pos)
        for v in _order(p, unplanned):
            if best is not None and p.pen[v] <= best[0]:
                break  # insertion cost is never negative, so no later v can beat best
            for k in p.allowed[v]:
                r = routes[k]
                for pos in range(len(r) + 1):
                    gain = p.pen[v] - _delta(p, k, r, pos, v)
                    if gain <= 0 or (best is not None and gain <= best[0]):
                        continue
                    if _feasible(p, k, r[:pos] + [v] + r[pos:]):
                        best = (gain, v, k, pos)
        if best is None:
            return changed
        _, v, k, pos = best
        routes[k].insert(pos, v)
        unplanned.discard(v)
        changed = True


def two_opt(p, routes):
    improved = False
    for k, r in enumerate(routes):
        again = True
        while again:
            again = False
            base = _route_travel(p, k, r)
            for i in range(len(r) - 1):
                for j in range(i + 1, len(r)):
                    cand = r[:i] + r[i:j + 1][::-1] + r[j + 1:]
                    if _route_travel(p, k, cand) < base and _feasible(p, k, cand):
                        r[:] = cand
                        improved = again = True
                        break
                if again:
                    break
    return improved


def relocate(p, routes):
    """Move one visit to another position (same or other day) if travel drops."""
    for k, r in enumerate(routes):
        for i, v in enumerate(list(r)):
            rest = r[:i] + r[i + 1:]
            saved = _route_travel(p, k, r) - _route_travel(p, k, rest)
            for k2 in p.allowed[v]:
                r2 = rest if k2 == k else routes[k2]
                for pos in range(len(r2) + 1):
                    if k2 == k and pos == i:
                        continue
                    cost = _delta(p, k2, r2, pos, v)
                    if cost >= saved:
                        continue
                    cand = r2[:pos] + [v] + r2[pos:]
                    if not _feasible(p, k2, cand):
                        continue
                    if k2 != k and not _feasible(p, k, rest):
                        continue
                    if k2 == k:
                        routes[k] = cand
                    else:
                        routes[k] = rest
                        routes[k2] = cand
                    return True
    return False


def swap_in(p, routes, unplanned):
    """Replace a planned visit with an unplanned one if the objective improves."""
    for v in _order(p, unplanned):
        for k in p.allowed[v]:
            r = routes[k]
            for i, a in enumerate(r):
                if p.pen[v] <= p.pen[a]:
                    continue
                cand = r[:i] + [v] + r[i + 1:]
                gain = (p.pen[v] - p.pen[a]) - (_route_travel(p, k, cand) - _route_travel(p, k, r))
                if gain > 0 and _feasible(p, k, cand):
                    routes[k] = cand
                    unplanned.discard(v)
                    unplanned.add(a)
                    return True
    return False


def solve(p):
    routes = [[] for _ in p.days]
    unplanned = set(p.visits)
    insert_all(p, routes, unplanned)
    rounds = 0
    while rounds < MAX_ROUNDS:
        rounds += 1
        changed = two_opt(p, routes)
        changed |= relocate(p, routes)
        changed |= swap_in(p, routes, unplanned)
        changed |= insert_all(p, routes, unplanned)
        if not changed:
            break
    return routes, {"rounds": rounds, "objective": objective(p, routes)}
