"""Adapters to independent exact solvers, for cross-validating CROWN.

Each adapter returns ``SolveResult(energy, assignment, seconds, proven)`` where
``proven`` is True iff the solver proved global optimality within its time limit.
Both adapters are optional: if the package is missing, the adapter is absent from
`available()`.

toulbar2 implements the SAME algorithm family as CROWN (AND/OR branch-and-bound +
mini-bucket heuristics) in tuned C++ -- the most informative head-to-head.
SCIP is a general exact MILP/MIQP solver -- a second, independent cross-check.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from crown.ising import QUBO


@dataclass
class SolveResult:
    energy: float
    assignment: List[int]
    seconds: float
    proven: bool


def solve_toulbar2(qubo: QUBO, time_limit: int = 30) -> SolveResult:
    import pytoulbar2  # noqa

    cfn = pytoulbar2.CFN(resolution=0, verbose=-1)
    for i in range(qubo.n):
        cfn.AddVariable(f"x{i}", range(2))
    shift = 0.0
    for i, a in qubo.linear.items():
        costs = [0.0, a]
        m = min(costs)
        shift += m
        cfn.AddFunction([i], [c - m for c in costs])
    for (i, j), b in qubo.quadratic.items():
        costs = [0.0, 0.0, 0.0, b]          # row-major over (x_i, x_j)
        m = min(costs)
        shift += m
        cfn.AddFunction([i, j], [c - m for c in costs])

    t0 = time.perf_counter()
    res = cfn.Solve(timeLimit=time_limit)
    secs = time.perf_counter() - t0
    if not res:                              # no solution found within the limit
        return SolveResult(float("inf"), [0] * qubo.n, secs, False)
    sol, opt = res[0], res[1]
    energy = opt + shift + qubo.const
    x = [int(v) for v in sol]
    # toulbar2 only returns a solution at the end of a complete search unless it
    # times out; treat a returned solution within the limit as proven-optimal.
    proven = secs < time_limit
    return SolveResult(energy, x, secs, proven)


def solve_scip(qubo: QUBO, time_limit: int = 30) -> SolveResult:
    from pyscipopt import Model, quicksum  # noqa

    m = Model()
    m.hideOutput()
    m.setParam("limits/time", time_limit)
    x = {i: m.addVar(vtype="B", name=f"x{i}") for i in range(qubo.n)}
    obj = qubo.const
    obj += quicksum(a * x[i] for i, a in qubo.linear.items())
    obj += quicksum(b * x[i] * x[j] for (i, j), b in qubo.quadratic.items())
    m.setObjective(obj, "minimize")
    t0 = time.perf_counter()
    m.optimize()
    secs = time.perf_counter() - t0
    status = m.getStatus()
    if m.getNSols() == 0:
        return SolveResult(float("inf"), [0] * qubo.n, secs, False)
    energy = m.getObjVal()
    assign = [int(round(m.getVal(x[i]))) for i in range(qubo.n)]
    return SolveResult(energy, assign, secs, status == "optimal")


def available() -> Dict[str, Callable[[QUBO, int], SolveResult]]:
    out: Dict[str, Callable[[QUBO, int], SolveResult]] = {}
    try:
        import pytoulbar2  # noqa
        out["toulbar2"] = solve_toulbar2
    except ImportError:
        pass
    try:
        import pyscipopt  # noqa
        out["scip"] = solve_scip
    except ImportError:
        pass
    return out
