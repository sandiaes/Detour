"""Spike S5 (throwaway): the OR-Tools routing sequencer.

Model: one vehicle per day; optional visits as single-node disjunctions with penalty
DROP_WEIGHT x score; a time dimension (service time + travel) capped at the day end; lunch and
dinner as vehicle breaks with start windows; visits restricted to
the days of their city. A free day start or end is a dummy node with zero travel to everything.

OR-Tools decides which visits are planned and in which order. The plan is then written out with
the same earliest-start schedule rule as the heuristic (common.schedule), so both outputs can be
compared directly; a route that OR-Tools accepts but the schedule rule rejects is counted as a
model mismatch.

Search configurations (first solution PARALLEL_CHEAPEST_INSERTION; prefix "au-" for
ALL_UNPERFORMED, i.e. start with nothing planned):
  descent     first solution + greedy descent; stops at a local optimum (no limit needed)
  gls-sN      guided local search stopped after N solutions; wall-clock cap only as a safety net
  gls-tMS     guided local search stopped by a wall-clock limit of MS milliseconds
"""
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

SAFETY_CAP_S = 60


def build(p):
    # model nodes: 0 = free dummy (if used), then every fixture node used as a day start or end, then visits
    # (the dummy exists only if some day uses it: an unused dummy would be an ordinary,
    # mandatory node with zero travel, i.e. a teleport in the middle of a route)
    depots = sorted({d[x] for d in p.days for x in ("start", "end") if d[x] is not None})
    free = any(d[x] is None for d in p.days for x in ("start", "end"))
    model_nodes = ([None] if free else []) + depots + list(p.visits)
    pos = {fx: i for i, fx in enumerate(model_nodes) if fx is not None}
    starts = [0 if d["start"] is None else pos[d["start"]] for d in p.days]
    ends = [0 if d["end"] is None else pos[d["end"]] for d in p.days]
    n_veh = len(p.days)
    manager = pywrapcp.RoutingIndexManager(len(model_nodes), n_veh, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def trav(a, b):
        fa, fb = model_nodes[a], model_nodes[b]
        if fa is None or fb is None:
            return 0
        return p.T[fa][fb]

    def cost_cb(i, j):
        return trav(manager.IndexToNode(i), manager.IndexToNode(j))

    def time_cb(i, j):
        a = manager.IndexToNode(i)
        fa = model_nodes[a]
        return (0 if fa is None else p.dur[fa]) + trav(a, manager.IndexToNode(j))

    cost_idx = routing.RegisterTransitCallback(cost_cb)
    time_idx = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_idx)
    routing.AddDimension(time_idx, p.day_end - p.day_start, p.day_end, False, "Time")
    time = routing.GetDimensionOrDie("Time")

    for fx in p.visits:
        idx = manager.NodeToIndex(pos[fx])
        routing.AddDisjunction([idx], p.pen[fx])
        if len(p.allowed[fx]) < n_veh:
            # -1 = not performed (the visit stays optional)
            routing.VehicleVar(idx).SetValues([-1] + p.allowed[fx])

    solver = routing.solver()
    node_visit_transit = [0] * routing.Size()
    for index in range(routing.Size()):
        fx = model_nodes[manager.IndexToNode(index)]
        node_visit_transit[index] = 0 if fx is None else p.dur[fx]
    for v in range(n_veh):
        start_var = time.CumulVar(routing.Start(v))
        end_var = time.CumulVar(routing.End(v))
        start_var.SetRange(p.days[v]["earliest"], p.day_end)
        end_var.SetRange(p.day_start, p.day_end)
        breaks = []
        for e, latest, d, name in p.meals:
            # A meal before the first or after the last item is legal (the traveller eats where
            # they are), so no link to the route's start and end is needed; the window only must
            # not open before the day can start. (A first version linked the breaks to the
            # route's start and end with generic constraints; insertion heuristics then stalled
            # on days that start late, see the S5 findings.)
            b = solver.FixedDurationIntervalVar(max(e, p.days[v]["earliest"]), latest, d,
                                                False, f"{name}-{v}")
            breaks.append(b)
            routing.AddIntervalToAssignment(b)
        time.SetBreakIntervalsOfVehicle(breaks, v, node_visit_transit)
        routing.AddVariableMinimizedByFinalizer(start_var)
        routing.AddVariableMinimizedByFinalizer(end_var)
    return manager, routing, model_nodes


def debug_times(p, config):
    """Spike diagnostics: OR-Tools' own times for each day (visits and breaks)."""
    manager, routing, model_nodes = build(p)
    sol = routing.SolveWithParameters(params_for(config))
    time = routing.GetDimensionOrDie("Time")
    names = {f"{m[3]}-{v}" for m in p.meals for v in range(len(p.days))}
    ivs = {}
    for k in range(sol.IntervalVarContainer().Size()):
        e = sol.IntervalVarContainer().Element(k)
        if e.Var().Name() in names:
            ivs[e.Var().Name()] = (e.StartValue(), e.EndValue())
    out = []
    for v in range(len(p.days)):
        items = []
        index = routing.Start(v)
        while True:
            fx = model_nodes[manager.IndexToNode(index)]
            c = time.CumulVar(index)
            items.append(("free" if fx is None else p.nodes[fx]["id"], sol.Min(c), sol.Max(c)))
            if routing.IsEnd(index):
                break
            index = sol.Value(routing.NextVar(index))
        brk = [(f"{m[3]}-{v}",) + ivs.get(f"{m[3]}-{v}", (None, None)) for m in p.meals]
        out.append({"items": items, "breaks": brk})
    return out


def params_for(config):
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION)
    if config.startswith("au-"):
        # start from "nothing planned" and let local search insert visits
        params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.ALL_UNPERFORMED)
        config = config[3:]
    if config == "descent":
        params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT)
        params.time_limit.FromSeconds(SAFETY_CAP_S)
    elif config.startswith("gls-s"):
        params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        params.solution_limit = int(config[5:])
        params.time_limit.FromSeconds(SAFETY_CAP_S)
    elif config.startswith("gls-t"):
        params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        params.time_limit.FromMilliseconds(int(config[5:]))
    else:
        raise ValueError(config)
    return params


def default_limits():
    d = pywrapcp.DefaultRoutingSearchParameters()
    return {"lns_time_limit_ms": d.lns_time_limit.ToMilliseconds(),
            "time_limit_s": d.time_limit.seconds, "solution_limit": d.solution_limit}


def solve(p, config):
    manager, routing, model_nodes = build(p)
    sol = routing.SolveWithParameters(params_for(config))
    status = routing.status()
    if sol is None:
        return [[] for _ in p.days], {"status": int(status), "solved": False}
    routes = []
    for v in range(len(p.days)):
        r = []
        index = routing.Start(v)
        while not routing.IsEnd(index):
            fx = model_nodes[manager.IndexToNode(index)]
            if fx is not None and p.nodes[fx]["kind"] == "visit":
                r.append(fx)
            index = sol.Value(routing.NextVar(index))
        routes.append(r)
    return routes, {"status": int(status), "solved": True,
                    "solver_objective": sol.ObjectiveValue()}
