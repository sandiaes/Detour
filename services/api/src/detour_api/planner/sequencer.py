"""Day construction: the ``Sequencer`` interface and its one implementation, the heuristic.

Spike S5 (``docs/spikes/s5-sequencing-findings.md``, decision D7) found OR-Tools not justified, so
the heuristic is the only sequencer. The interface stays so the question can be reopened.

The problem: choose and order visits over ``days`` open paths (a day starts at its first visit and
ends at its last: no accommodation, product brief section 9) to **maximise**

    sum of the values of the planned visits  -  travel_weight x total travel minutes

with every day's visits plus transfers fitting in ``day_minutes``. Values, durations and travel
minutes are integers.

The heuristic (architecture section 5.5): greedy best-gain insertion, then local search in a fixed
order (2-opt within a day, relocation within and between days, swapping a planned visit for an
unplanned one, re-insertion) until nothing improves. Every move strictly improves the objective,
so it terminates. Loops run in index order (indexes follow place ids), ties keep the first found,
and there is no randomness and no clock: the same problem gives the same plan on any machine.
"""

import itertools
from dataclasses import dataclass
from typing import Protocol

MAX_ROUNDS = 100


@dataclass(frozen=True)
class SequencingProblem:
    ids: tuple[str, ...]  # node index -> place id, ascending
    value: tuple[int, ...]
    duration: tuple[int, ...]  # minutes
    travel: tuple[tuple[int, ...], ...]  # minutes from node i to node j
    days: int
    day_minutes: int
    travel_weight: int


class Sequencer(Protocol):
    name: str

    def solve(self, problem: SequencingProblem) -> list[list[int]]:
        """One route (node indexes in visiting order) per day."""
        ...


class _State:
    def __init__(self, p: SequencingProblem) -> None:
        self.p = p
        self.T = p.travel
        self.routes: list[list[int]] = [[] for _ in range(p.days)]
        self.length = [0] * p.days  # visit minutes + travel minutes of each day
        # Nodes that can fit in a day at all, best value first, then index.
        self.order = sorted(
            (v for v in range(len(p.ids)) if p.duration[v] <= p.day_minutes and p.value[v] > 0),
            key=lambda v: (-p.value[v], v),
        )
        self.unplanned = set(self.order)

    # -- route arithmetic ----------------------------------------------------------------------

    def route_travel(self, r: list[int]) -> int:
        T = self.T
        return sum(T[a][b] for a, b in itertools.pairwise(r))

    def ins_delta(self, r: list[int], pos: int, v: int) -> int:
        T = self.T
        if not r:
            return 0
        if pos == 0:
            return T[v][r[0]]
        if pos == len(r):
            return T[r[-1]][v]
        a, b = r[pos - 1], r[pos]
        return T[a][v] + T[v][b] - T[a][b]

    def rem_delta(self, r: list[int], i: int) -> int:
        """Travel minutes saved by removing r[i]."""
        T = self.T
        n = len(r)
        if n == 1:
            return 0
        if i == 0:
            return T[r[0]][r[1]]
        if i == n - 1:
            return T[r[-2]][r[-1]]
        return T[r[i - 1]][r[i]] + T[r[i]][r[i + 1]] - T[r[i - 1]][r[i + 1]]

    def fits(self, length: int) -> bool:
        return length <= self.p.day_minutes

    # -- insertion -----------------------------------------------------------------------------

    def best_in(self, k: int, v: int) -> tuple[int, int] | None:
        """(gain, position) of the best feasible insertion of v into day k with a positive gain."""
        p = self.p
        r = self.routes[k]
        best: tuple[int, int] | None = None
        for pos in range(len(r) + 1):
            delta = self.ins_delta(r, pos, v)
            if not self.fits(self.length[k] + p.duration[v] + delta):
                continue
            gain = p.value[v] - p.travel_weight * delta
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, pos)
        return best

    def insert_all(self) -> bool:
        changed = False
        days = range(self.p.days)
        cache = {v: [self.best_in(k, v) for k in days] for v in self.order if v in self.unplanned}
        while cache:
            choice: tuple[int, int, int, int] | None = None  # gain, v, k, pos
            for v in self.order:
                options = cache.get(v)
                if options is None:
                    continue
                for k in days:
                    o = options[k]
                    if o is not None and (choice is None or o[0] > choice[0]):
                        choice = (o[0], v, k, o[1])
            if choice is None:
                break
            _, v, k, pos = choice
            self.length[k] += self.p.duration[v] + self.ins_delta(self.routes[k], pos, v)
            self.routes[k].insert(pos, v)
            self.unplanned.discard(v)
            del cache[v]
            for u, options in cache.items():
                options[k] = self.best_in(k, u)
            changed = True
        return changed

    # -- local search --------------------------------------------------------------------------

    def two_opt(self) -> bool:
        changed = False
        for k, r in enumerate(self.routes):
            again = True
            while again:
                again = False
                base = self.route_travel(r)
                for i in range(len(r) - 1):
                    for j in range(i + 1, len(r)):
                        cand = r[:i] + r[i : j + 1][::-1] + r[j + 1 :]
                        t = self.route_travel(cand)
                        if t < base and self.fits(self.length[k] - base + t):
                            self.length[k] += t - base
                            r[:] = cand
                            changed = again = True
                            break
                    if again:
                        break
        return changed

    def _relocate_once(self) -> bool:
        p = self.p
        for k, r in enumerate(self.routes):
            for i, v in enumerate(r):
                saved = self.rem_delta(r, i)
                rest = r[:i] + r[i + 1 :]
                for k2 in range(p.days):
                    target = rest if k2 == k else self.routes[k2]
                    for pos in range(len(target) + 1):
                        if k2 == k and pos == i:
                            continue
                        cost = self.ins_delta(target, pos, v)
                        if cost >= saved:
                            continue
                        if k2 == k:
                            new_len = self.length[k] - saved + cost
                            if not self.fits(new_len):
                                continue
                            self.routes[k] = [*rest[:pos], v, *rest[pos:]]
                            self.length[k] = new_len
                        else:
                            new_len2 = self.length[k2] + p.duration[v] + cost
                            if not self.fits(new_len2):
                                continue
                            self.routes[k] = rest
                            self.length[k] -= p.duration[v] + saved
                            self.routes[k2] = [*target[:pos], v, *target[pos:]]
                            self.length[k2] = new_len2
                        return True
        return False

    def relocate(self) -> bool:
        changed = False
        while self._relocate_once():
            changed = True
        return changed

    def _swap_once(self) -> bool:
        p = self.p
        for v in self.order:
            if v not in self.unplanned:
                continue
            for k, r in enumerate(self.routes):
                for i, a in enumerate(r):
                    if p.value[v] <= p.value[a]:
                        continue
                    cand = [*r[:i], v, *r[i + 1 :]]
                    d_travel = self.route_travel(cand) - self.route_travel(r)
                    gain = p.value[v] - p.value[a] - p.travel_weight * d_travel
                    new_len = self.length[k] - p.duration[a] + p.duration[v] + d_travel
                    if gain > 0 and self.fits(new_len):
                        self.routes[k] = cand
                        self.length[k] = new_len
                        self.unplanned.discard(v)
                        self.unplanned.add(a)
                        return True
        return False

    def swap_in(self) -> bool:
        changed = False
        while self._swap_once():
            changed = True
        return changed


class HeuristicSequencer:
    """Greedy best-gain insertion plus deterministic local search (spike S5, D7)."""

    name = "heuristic-1"

    def solve(self, problem: SequencingProblem) -> list[list[int]]:
        s = _State(problem)
        s.insert_all()
        for _ in range(MAX_ROUNDS):
            changed = s.two_opt()
            changed |= s.relocate()
            changed |= s.swap_in()
            changed |= s.insert_all()
            if not changed:
                break
        return [list(r) for r in s.routes]
