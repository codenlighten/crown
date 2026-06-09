"""Rigorous, persistency-independent global lower bound via a JGLP certificate.

JGLP cost-shifting reparameterises the energy into clusters with
`const + sum_c table_c(x) == E(x)` for all x. Hence

    LB = const + sum_c min_x table_c(x)  <=  min_x E(x)

is a valid lower bound, and -- because the JGLP clusters are pairwise -- it can
be certified COMPACTLY and TRUSTLESSLY: ship the clusters as pairwise
sub-QUBOs; a verifier checks (a) they sum back to the original QUBO (the
reparameterisation identity, pure arithmetic) and (b) recomputes each cluster's
minimum (a bounded 2^|scope| enumeration). Soundness needs nothing more: ANY set
of pairwise clusters that sums to E gives a valid lower bound, no matter how it
was produced. Run on the UNREDUCED problem this bound is rigorous and does not
rely on roof-dual strong persistency -- so when it meets the achieved energy the
certificate is `bound-tight`, the strongest kind.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple

from .elimination import Factor, join_graph_clusters, min_fill_order
from .ising import QUBO


def _extract_pairwise(factor: Factor, tol: float = 1e-7):
    """Extract (const, linear, quadratic) from a factor table, or None if the
    table is not exactly a pairwise function over its scope."""
    S = factor.vars
    T = factor.table
    z = (0,) * len(S)
    const = float(T[z])
    lin: Dict[int, float] = {}
    for a, i in enumerate(S):
        e = [0] * len(S)
        e[a] = 1
        lin[i] = float(T[tuple(e)]) - const
    quad: Dict[Tuple[int, int], float] = {}
    for a in range(len(S)):
        for b in range(a + 1, len(S)):
            ea = [0] * len(S); ea[a] = 1
            eb = [0] * len(S); eb[b] = 1
            eab = [0] * len(S); eab[a] = 1; eab[b] = 1
            quad[(S[a], S[b])] = (float(T[tuple(eab)]) - float(T[tuple(ea)])
                                  - float(T[tuple(eb)]) + const)
    # verify the table really is this pairwise function (no higher-order term)
    for bits in itertools.product((0, 1), repeat=len(S)):
        val = const
        for a, i in enumerate(S):
            if bits[a]:
                val += lin[i]
        for a in range(len(S)):
            for b in range(a + 1, len(S)):
                if bits[a] and bits[b]:
                    val += quad[(S[a], S[b])]
        if abs(val - float(T[bits])) > tol:
            return None
    return const, lin, quad


def jglp_certificate(qubo: QUBO, ibound: int = 10, iters: int = 80,
                     order: Optional[List[int]] = None):
    """Produce a trustless JGLP lower-bound certificate for `qubo`.

    Returns (certificate dict, lower_bound) or None if any cluster is not
    pairwise (should not happen for pairwise inputs).
    """
    if order is None:
        order, _ = min_fill_order(qubo)
    clusters, const, _ = join_graph_clusters(qubo, ibound, iters, order)
    cert_clusters = []
    lb = const
    for c in clusters:
        ex = _extract_pairwise(c)
        if ex is None:
            return None
        cc, lin, quad = ex
        mn = _cluster_min(c.vars, cc, lin, quad)
        lb += mn
        cert_clusters.append({
            "vars": list(c.vars),
            "const": cc,
            "linear": [[i, lin[i]] for i in c.vars if abs(lin.get(i, 0.0)) > 0],
            "quadratic": [[i, j, b] for (i, j), b in quad.items() if abs(b) > 0],
        })
    return {"const": const, "clusters": cert_clusters}, lb


def _cluster_min(vars_: Tuple[int, ...], const: float, lin: Dict[int, float],
                 quad: Dict[Tuple[int, int], float]) -> float:
    best = float("inf")
    idx = {v: k for k, v in enumerate(vars_)}
    for bits in itertools.product((0, 1), repeat=len(vars_)):
        val = const
        for v in vars_:
            if bits[idx[v]]:
                val += lin.get(v, 0.0)
        for (i, j), b in quad.items():
            if bits[idx[i]] and bits[idx[j]]:
                val += b
        best = min(best, val)
    return best


def verify_jglp_certificate(qubo: QUBO, cert: dict, tol: float = 1e-5):
    """Independently check a JGLP certificate and recompute its lower bound.

    Returns (ok, lower_bound, message). Sound for ANY pairwise clusters that sum
    to the QUBO -- it does not trust that JGLP produced them.
    """
    total_const = cert["const"]
    total_lin: Dict[int, float] = {}
    total_quad: Dict[Tuple[int, int], float] = {}
    lb = cert["const"]
    for cl in cert["clusters"]:
        S = tuple(cl["vars"])
        cc = float(cl["const"])
        lin = {int(i): float(a) for i, a in cl["linear"]}
        quad = {(int(i), int(j)): float(b) for i, j, b in cl["quadratic"]}
        if any(k not in S for k in lin) or any(i not in S or j not in S for (i, j) in quad):
            return False, float("nan"), "cluster term outside its declared scope"
        lb += _cluster_min(S, cc, lin, quad)
        total_const += cc
        for i, a in lin.items():
            total_lin[i] = total_lin.get(i, 0.0) + a
        for (i, j), b in quad.items():
            key = (i, j) if i < j else (j, i)
            total_quad[key] = total_quad.get(key, 0.0) + b

    # reparameterisation identity: clusters (plus cert const) must sum to E
    if abs(total_const - qubo.const) > tol:
        return False, float("nan"), "constant does not match"
    for i in set(total_lin) | set(qubo.linear):
        if abs(total_lin.get(i, 0.0) - qubo.linear.get(i, 0.0)) > tol:
            return False, float("nan"), f"linear term {i} does not match"
    for e in set(total_quad) | set(qubo.quadratic):
        if abs(total_quad.get(e, 0.0) - qubo.quadratic.get(e, 0.0)) > tol:
            return False, float("nan"), f"quadratic term {e} does not match"
    return True, lb, "jglp certificate verified"
