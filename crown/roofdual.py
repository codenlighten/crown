"""Roof duality: the rigorous core of CROWN's "irreducible core extraction".

Roof duality (Hammer-Hansen-Simeone 1984; Boros-Hammer) is the classical,
provably-sound version of what the CROWN vision calls "hardness distillation".
It is *equivalent* to the standard linearisation LP of the QUBO, and it gives
two things at once:

  1. A valid LOWER BOUND on the global minimum energy, together with a
     dual-feasible certificate that an independent party can re-check by pure
     arithmetic (weak LP duality: any dual-feasible point lower-bounds the
     primal optimum, no solver trust required).

  2. PERSISTENCY: variables that come out integral (0 or 1) in the relaxation
     can be fixed to that value -- these are the "reducible shell". What is left
     fractional is the irreducible core.

Standard linearisation LP (w_e relaxes the product x_i x_j on edge e=(i,j)):

    min  const + sum_i a_i y_i + sum_e b_e w_e
    s.t. y_i + y_j - w_e <= 1     (C1)
         -y_i      + w_e <= 0     (C2)
              -y_j + w_e <= 0     (C3)
         0 <= y_i <= 1,  w_e >= 0

The dual we expose as the certificate (p,q,r >= 0 per edge, s >= 0 per node):

    LB = const - sum_e p_e - sum_i s_i
    s.t. (per node i)  -sum_{e ~ i} p_e + sum_{e=(i,*)} q_e
                       + sum_{e=(*,i)} r_e - s_i  <=  a_i
         (per edge e)   p_e - q_e - r_e           <=  b_e
         p, q, r, s >= 0

`verify_dual_bound` re-checks exactly these inequalities; that is the trustless
part of Proof-of-Collapse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
from scipy.optimize import linprog

from .ising import QUBO

_TOL = 1e-7


@dataclass
class RoofDualResult:
    lower_bound: float
    persistencies: Dict[int, int]      # variable -> fixed value (0/1)
    fractional: list[int]              # variables left undecided (the core)
    certificate: dict                  # dual vector + edge order, for verify
    primal_value: float                # for self-consistency checks


def roof_dual(qubo: QUBO) -> RoofDualResult:
    n = qubo.n
    edges = qubo.edges()
    m = len(edges)
    edge_index = {e: k for k, e in enumerate(edges)}

    # ---------------- Primal LP: lower bound + persistency ---------------- #
    # Variables z = [y_0..y_{n-1}, w_0..w_{m-1}]
    c = np.zeros(n + m)
    for i, a in qubo.linear.items():
        c[i] = a
    for e, b in qubo.quadratic.items():
        c[n + edge_index[e]] = b

    rows, rhs = [], []
    for (i, j) in edges:
        k = n + edge_index[(i, j)]
        r1 = np.zeros(n + m); r1[i] = 1; r1[j] = 1; r1[k] = -1; rows.append(r1); rhs.append(1.0)
        r2 = np.zeros(n + m); r2[i] = -1; r2[k] = 1; rows.append(r2); rhs.append(0.0)
        r3 = np.zeros(n + m); r3[j] = -1; r3[k] = 1; rows.append(r3); rhs.append(0.0)

    A_ub = np.array(rows) if rows else None
    b_ub = np.array(rhs) if rhs else None
    bounds = [(0.0, 1.0)] * n + [(0.0, None)] * m

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"roof-dual primal LP failed: {res.message}")
    primal_value = float(res.fun) + qubo.const
    y = res.x[:n]

    persistencies: Dict[int, int] = {}
    fractional: list[int] = []
    for i in range(n):
        if y[i] <= _TOL:
            persistencies[i] = 0
        elif y[i] >= 1.0 - _TOL:
            persistencies[i] = 1
        else:
            fractional.append(i)

    # ---------------- Dual LP: the checkable certificate ------------------ #
    # Dual vars d = [p_0..p_{m-1}, q_0..q_{m-1}, r_0..r_{m-1}, s_0..s_{n-1}]
    P, Q, R, S = 0, m, 2 * m, 3 * m
    nd = 3 * m + n
    cd = np.zeros(nd)                 # minimise sum p + sum s  (= maximise LB)
    for k in range(m):
        cd[P + k] = 1.0
    for i in range(n):
        cd[S + i] = 1.0

    drows, drhs = [], []
    # per-node constraints
    for i in range(n):
        row = np.zeros(nd)
        for (a_, b_) in edges:
            if i in (a_, b_):
                row[P + edge_index[(a_, b_)]] += -1.0
        for k, (a_, b_) in enumerate(edges):
            if a_ == i:
                row[Q + k] += 1.0
            if b_ == i:
                row[R + k] += 1.0
        row[S + i] += -1.0
        drows.append(row)
        drhs.append(qubo.linear.get(i, 0.0))
    # per-edge constraints
    for k, e in enumerate(edges):
        row = np.zeros(nd)
        row[P + k] = 1.0
        row[Q + k] = -1.0
        row[R + k] = -1.0
        drows.append(row)
        drhs.append(qubo.quadratic[e])

    dres = linprog(
        cd,
        A_ub=np.array(drows) if drows else None,
        b_ub=np.array(drhs) if drhs else None,
        bounds=[(0.0, None)] * nd,
        method="highs",
    )
    if not dres.success:
        raise RuntimeError(f"roof-dual dual LP failed: {dres.message}")
    dual_lb = qubo.const - float(dres.fun)

    d = dres.x
    certificate = {
        "edges": [list(e) for e in edges],
        "n": n,
        "const": qubo.const,
        "p": d[P:P + m].tolist(),
        "q": d[Q:Q + m].tolist(),
        "r": d[R:R + m].tolist(),
        "s": d[S:S + n].tolist(),
        "claimed_lower_bound": dual_lb,
    }

    # The dual we report is the certified one; it can only be <= primal value.
    return RoofDualResult(
        lower_bound=dual_lb,
        persistencies=persistencies,
        fractional=fractional,
        certificate=certificate,
        primal_value=primal_value,
    )


def verify_dual_bound(qubo: QUBO, certificate: dict, tol: float = 1e-5) -> Tuple[bool, float, str]:
    """Independently re-check a roof-dual certificate by pure arithmetic.

    Returns (ok, lower_bound, message). No LP solver is invoked: we only confirm
    the supplied dual vector is feasible and recompute its objective. By weak LP
    duality a feasible dual is a valid lower bound on every assignment's energy.
    """
    edges = [tuple(e) for e in certificate["edges"]]
    if edges != qubo.edges():
        return False, float("nan"), "certificate edge set does not match the QUBO"
    if certificate["n"] != qubo.n:
        return False, float("nan"), "certificate variable count mismatch"

    p = certificate["p"]; q = certificate["q"]; r = certificate["r"]; s = certificate["s"]
    if min(min(p, default=0), min(q, default=0), min(r, default=0), min(s, default=0)) < -tol:
        return False, float("nan"), "dual vector has negative entries"

    edge_index = {e: k for k, e in enumerate(edges)}

    # per-node feasibility: ... <= a_i
    for i in range(qubo.n):
        lhs = -s[i]
        for k, (a_, b_) in enumerate(edges):
            if i in (a_, b_):
                lhs -= p[k]
            if a_ == i:
                lhs += q[k]
            if b_ == i:
                lhs += r[k]
        if lhs > qubo.linear.get(i, 0.0) + tol:
            return False, float("nan"), f"node {i} dual constraint violated"

    # per-edge feasibility: p - q - r <= b_e
    for k, e in enumerate(edges):
        if p[k] - q[k] - r[k] > qubo.quadratic[e] + tol:
            return False, float("nan"), f"edge {e} dual constraint violated"

    lb = qubo.const - sum(p) - sum(s)
    return True, lb, "dual certificate verified"
