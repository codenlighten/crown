"""Bound-carrying variable elimination (vision layer 4, made rigorous).

Two engines over a QUBO, both min-sum (we minimise energy):

  * `bucket_elimination` -- EXACT. Solves the problem in time/space
    O(2^(w+1)) where w is the induced width of the elimination order, NOT 2^n.
    A 200-variable core with treewidth 8 is trivial here but 2^200 by brute
    force. Returns the exact minimum energy AND an optimal assignment.

  * `mini_bucket` -- a sound LOWER BOUND when the induced width is too large to
    eliminate exactly. It partitions each bucket into mini-buckets of bounded
    scope and minimises each independently; letting the eliminated variable take
    different values in different mini-buckets is a relaxation, hence a lower
    bound on the true minimum (Dechter & Rish). With i-bound >= width it
    coincides with exact elimination.

This is the "tensor collapse as a proof engine" idea: each elimination message
carries either the exact min-marginal (exact engine) or a lower-bounding
min-marginal (mini-bucket), so pruning is structural, not just scalar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from .ising import QUBO


@dataclass
class Factor:
    vars: Tuple[int, ...]      # sorted scope
    table: np.ndarray          # shape (2,) * len(vars); table[assignment] = energy


def _initial_factors(qubo: QUBO) -> List[Factor]:
    factors: List[Factor] = []
    for i, a in qubo.linear.items():
        factors.append(Factor((i,), np.array([0.0, a])))
    for (i, j), b in qubo.quadratic.items():
        t = np.zeros((2, 2))
        t[1, 1] = b
        lo, hi = (i, j) if i < j else (j, i)
        if (lo, hi) != (i, j):
            t = t.T
        factors.append(Factor((lo, hi), t))
    return factors


def _align(factor: Factor, scope: Tuple[int, ...]) -> np.ndarray:
    """Broadcast a factor's table to `scope` (a sorted superset of its vars)."""
    present = set(factor.vars)
    shape = [2 if v in present else 1 for v in scope]
    return factor.table.reshape(shape)


def _combine(factors: List[Factor]) -> Factor:
    scope = tuple(sorted(set().union(*[set(f.vars) for f in factors])))
    acc = np.zeros((2,) * len(scope))
    for f in factors:
        acc = acc + _align(f, scope)
    return Factor(scope, acc)


def _min_marginal(factor: Factor, v: int) -> np.ndarray:
    """min over every variable except v -> a length-2 vector over v's two values."""
    axis = factor.vars.index(v)
    other = tuple(a for a in range(len(factor.vars)) if a != axis)
    return factor.table.min(axis=other) if other else factor.table.copy()


def _shift(factor: Factor, v: int, delta: np.ndarray) -> None:
    """In place: add a length-2 cost shift delta(v), broadcast over v's axis."""
    axis = factor.vars.index(v)
    shape = [1] * len(factor.vars)
    shape[axis] = 2
    factor.table = factor.table + delta.reshape(shape)


# --------------------------------------------------------------------------- #
# Elimination ordering + induced width (min-fill heuristic)
# --------------------------------------------------------------------------- #
def min_fill_order(qubo: QUBO) -> Tuple[List[int], int]:
    adj: Dict[int, set] = {i: set() for i in range(qubo.n)}
    for (i, j) in qubo.quadratic:
        adj[i].add(j)
        adj[j].add(i)

    remaining = set(range(qubo.n))
    order: List[int] = []
    width = 0
    while remaining:
        best, best_fill, best_deg = None, None, None
        for v in remaining:
            nb = adj[v] & remaining
            fill = 0
            nb_list = list(nb)
            for a in range(len(nb_list)):
                for b in range(a + 1, len(nb_list)):
                    if nb_list[b] not in adj[nb_list[a]]:
                        fill += 1
            if best_fill is None or fill < best_fill or (fill == best_fill and len(nb) < best_deg):
                best, best_fill, best_deg = v, fill, len(nb)
        v = best
        nb = adj[v] & remaining
        width = max(width, len(nb))
        nb_list = list(nb)
        for a in nb_list:                      # connect the clique (fill-in)
            adj[a].update(x for x in nb_list if x != a)
        remaining.remove(v)
        order.append(v)
    return order, width


# --------------------------------------------------------------------------- #
# Exact bucket elimination
# --------------------------------------------------------------------------- #
def bucket_elimination(qubo: QUBO, order: List[int] | None = None) -> Tuple[float, List[int]]:
    if qubo.n == 0:
        return qubo.const, []
    if order is None:
        order, _ = min_fill_order(qubo)

    factors = _initial_factors(qubo)
    const = qubo.const
    combined_for: Dict[int, Factor] = {}

    for v in order:
        bucket = [f for f in factors if v in f.vars]
        if not bucket:
            continue
        factors = [f for f in factors if v not in f.vars]
        combined = _combine(bucket)
        combined_for[v] = combined
        axis = combined.vars.index(v)
        reduced = combined.table.min(axis=axis)
        new_vars = tuple(u for u in combined.vars if u != v)
        if new_vars:
            factors.append(Factor(new_vars, reduced))
        else:
            const += float(reduced)
    for f in factors:                          # leftover scalars
        const += float(f.table)
    min_energy = const

    # backward pass: recover an optimal assignment
    assign: Dict[int, int] = {}
    for v in reversed(order):
        comb = combined_for.get(v)
        if comb is None:
            continue
        idx = []
        for u in comb.vars:
            idx.append(slice(None) if u == v else assign[u])
        col = comb.table[tuple(idx)]
        assign[v] = int(np.argmin(col))
    x = [assign.get(i, 0) for i in range(qubo.n)]
    return min_energy, x


# --------------------------------------------------------------------------- #
# Mini-bucket elimination -> lower bound
# --------------------------------------------------------------------------- #
def mini_bucket(qubo: QUBO, ibound: int = 16, order: List[int] | None = None) -> float:
    if qubo.n == 0:
        return qubo.const
    if order is None:
        order, _ = min_fill_order(qubo)

    factors = _initial_factors(qubo)
    const = qubo.const

    for v in order:
        bucket = [f for f in factors if v in f.vars]
        if not bucket:
            continue
        factors = [f for f in factors if v not in f.vars]

        # greedily pack factors into mini-buckets of scope <= ibound
        bucket.sort(key=lambda f: len(f.vars), reverse=True)
        groups: List[List[Factor]] = []
        for f in bucket:
            placed = False
            for g in groups:
                scope = set(f.vars)
                for gf in g:
                    scope |= set(gf.vars)
                if len(scope) <= ibound:
                    g.append(f)
                    placed = True
                    break
            if not placed:
                groups.append([f])

        for g in groups:
            combined = _combine(g)
            axis = combined.vars.index(v)
            reduced = combined.table.min(axis=axis)   # independent min => relaxation
            new_vars = tuple(u for u in combined.vars if u != v)
            if new_vars:
                factors.append(Factor(new_vars, reduced))
            else:
                const += float(reduced)
    for f in factors:
        const += float(f.table)
    return const


def weighted_mini_bucket(qubo: QUBO, ibound: int = 16,
                         order: List[int] | None = None) -> float:
    """Mini-bucket with moment matching (cost-shifting) -> a TIGHTER lower bound.

    Same partitioning as `mini_bucket`, but before eliminating a variable `v`
    that lands in several mini-buckets, we reparameterise: add a zero-sum cost
    shift to each mini-bucket so that v's min-marginals agree across them
    (moment matching). Two facts make this a sound *and* tighter bound:

      * ANY zero-sum shift keeps it a lower bound, since for shifted factors
        phi'_k we still have  sum_k min_v phi'_k <= min_v sum_k phi'_k.
      * Matching the min-marginals to their average equalises v's marginal
        across the mini-buckets and usually tightens the bound substantially
        (~3/4 of instances in practice). With ib >= width there is no splitting
        and it equals the exact minimum.

    NOTE: a single moment-matching pass is not *guaranteed* monotone over a
    sequential elimination schedule (downstream messages couple the copies), so
    it can occasionally come out below plain mini-bucket. Always combine via
    `mini_bucket_bound`, which returns max(plain, matched) -- provably >= plain
    and still a valid lower bound.

    This is the MAP/min-sum form of weighted mini-bucket (Ihler et al.): the
    tightening for minimisation comes from cost-shifting, not from Holder
    weights (those tighten the sum/partition-function bound).
    """
    if qubo.n == 0:
        return qubo.const
    if order is None:
        order, _ = min_fill_order(qubo)

    factors = _initial_factors(qubo)
    const = qubo.const

    for v in order:
        bucket = [f for f in factors if v in f.vars]
        if not bucket:
            continue
        factors = [f for f in factors if v not in f.vars]

        bucket.sort(key=lambda f: len(f.vars), reverse=True)
        groups: List[List[Factor]] = []
        for f in bucket:
            placed = False
            for g in groups:
                scope = set(f.vars)
                for gf in g:
                    scope |= set(gf.vars)
                if len(scope) <= ibound:
                    g.append(f)
                    placed = True
                    break
            if not placed:
                groups.append([f])

        combined = [_combine(g) for g in groups]

        # moment matching: equalise v's min-marginal across the mini-buckets
        if len(combined) > 1:
            margs = [_min_marginal(c, v) for c in combined]
            avg = sum(margs) / len(margs)
            for c, m in zip(combined, margs):
                _shift(c, v, avg - m)

        for c in combined:
            axis = c.vars.index(v)
            reduced = c.table.min(axis=axis)
            new_vars = tuple(u for u in c.vars if u != v)
            if new_vars:
                factors.append(Factor(new_vars, reduced))
            else:
                const += float(reduced)
    for f in factors:
        const += float(f.table)
    return const


def mini_bucket_bound(qubo: QUBO, ibound: int = 16,
                      order: List[int] | None = None) -> float:
    """Best available mini-bucket lower bound: max(plain, moment-matched).

    Both terms are valid lower bounds on the minimum energy, so their max is a
    valid lower bound, and it is >= the plain mini-bucket bound by construction.
    """
    if order is None:
        order, _ = min_fill_order(qubo)
    return max(mini_bucket(qubo, ibound=ibound, order=order),
               weighted_mini_bucket(qubo, ibound=ibound, order=order))


# --------------------------------------------------------------------------- #
# Join-graph cost-shifting (JGLP) -- iterated, monotone, converges past roof dual
# --------------------------------------------------------------------------- #
def _build_clusters(qubo: QUBO, ibound: int, order: List[int]) -> List[Factor]:
    """Static cover of the original factors by clusters of scope <= ibound.

    Each unary/pairwise factor is claimed by the first of its variables in the
    elimination order; factors sharing that variable are greedily packed into
    mini-buckets. The result is a fixed join graph (clusters share variables),
    which is what makes the subsequent cost-shifting monotone -- unlike a single
    elimination pass, the clusters never change.
    """
    pool = _initial_factors(qubo)
    clusters: List[Factor] = []
    for v in order:
        bucket = [f for f in pool if v in f.vars]
        if not bucket:
            continue
        pool = [f for f in pool if v not in f.vars]
        bucket.sort(key=lambda f: len(f.vars), reverse=True)
        groups: List[List[Factor]] = []
        for f in bucket:
            placed = False
            for g in groups:
                scope = set(f.vars)
                for gf in g:
                    scope |= set(gf.vars)
                if len(scope) <= ibound:
                    g.append(f)
                    placed = True
                    break
            if not placed:
                groups.append([f])
        for g in groups:
            clusters.append(_combine(g))
    for f in pool:                                  # isolated leftovers (rare)
        clusters.append(f)
    return clusters


def _marginal_over(factor: Factor, svars: Tuple[int, ...]) -> np.ndarray:
    """min over every variable NOT in svars -> a table over svars (sorted)."""
    keep = set(svars)
    other = tuple(a for a, v in enumerate(factor.vars) if v not in keep)
    return factor.table.min(axis=other) if other else factor.table.copy()


def _shift_over(factor: Factor, svars: Tuple[int, ...], delta: np.ndarray) -> None:
    """In place: add a shift indexed by svars, broadcast over the factor scope."""
    keep = set(svars)
    shape = [2 if v in keep else 1 for v in factor.vars]
    factor.table = factor.table + delta.reshape(shape)


def join_graph_bound(qubo: QUBO, ibound: int = 12, iters: int = 100,
                     order: List[int] | None = None, tol: float = 1e-9,
                     return_trace: bool = False):
    """Iterated cost-shifting on a fixed cluster join graph (JGLP / GDD).

    Clusters partition the original factors (scope <= ibound). We then repeatedly
    match min-marginals across the clusters that share a SEPARATOR -- both single
    variables AND variable pairs (the edges of the interaction graph). Each match
    sets every sharing cluster's separator min-marginal to their average, which
    is the exact block-maximiser of the dual lower bound, so the bound is
    **monotone non-decreasing** and converges toward the join-graph LP.

      * Single-variable separators alone converge to the pairwise LP == the
        roof-dual bound (no improvement -- that bound is already exact).
      * PAIR separators enforce joint two-variable consistency, capturing
        frustrated cycles. This is what pushes the bound strictly past roof
        duality (e.g. a frustrated triangle, where roof duality is loose).

    Soundness: every update is a zero-sum reparameterisation, so
    sum_c table_c == E(x) throughout, hence sum_c min table_c <= min E(x).
    """
    if qubo.n == 0:
        return (qubo.const, [qubo.const]) if return_trace else qubo.const
    clusters, const, trace = join_graph_clusters(qubo, ibound, iters, order, tol)
    b = const + sum(float(c.table.min()) for c in clusters)
    return (b, trace) if return_trace else b


def join_graph_clusters(qubo: QUBO, ibound: int = 12, iters: int = 100,
                        order: List[int] | None = None, tol: float = 1e-9):
    """Run JGLP cost-shifting and return the reparameterised clusters.

    Returns (clusters, const, trace). The clusters partition the energy
    (`const + sum_c table_c(x) == E(x)`), so `const + sum_c min table_c` is the
    JGLP lower bound -- and, conditioned on a partial assignment, the same sum is
    a valid admissible heuristic for branch-and-bound search (see crown/search.py).
    """
    if order is None:
        order, _ = min_fill_order(qubo)
    clusters = _build_clusters(qubo, ibound, order)
    const = qubo.const

    # separators: each variable and each interaction-graph edge, with the
    # clusters whose scope fully contains it (only those with >= 2 clusters bite).
    separators: List[Tuple[Tuple[int, ...], List[int]]] = []
    for i in range(qubo.n):
        cids = [ci for ci, c in enumerate(clusters) if i in c.vars]
        if len(cids) >= 2:
            separators.append(((i,), cids))
    for (i, j) in qubo.edges():
        cids = [ci for ci, c in enumerate(clusters) if i in c.vars and j in c.vars]
        if len(cids) >= 2:
            separators.append(((i, j), cids))

    def bound() -> float:
        return const + sum(float(c.table.min()) for c in clusters)

    trace = [bound()]
    for _ in range(iters):
        for svars, cids in separators:
            margs = [_marginal_over(clusters[ci], svars) for ci in cids]
            avg = sum(margs) / len(margs)
            for ci, m in zip(cids, margs):
                _shift_over(clusters[ci], svars, avg - m)
        trace.append(bound())
        if trace[-1] - trace[-2] < tol:             # converged
            break
    return clusters, const, trace


def wide_core_bound(qubo: QUBO, order: List[int] | None = None) -> float:
    """Best lower bound CROWN reports for a core too wide to eliminate exactly.

    The max of weighted mini-bucket and join-graph (JGLP) bounds -- both sound,
    so their max is sound and at least as tight as either. JGLP's pair-separator
    matching is what lets this exceed the roof-dual bound on frustrated cores.
    Deterministic given the core, so a verifier recomputes the identical value.
    """
    if order is None:
        order, _ = min_fill_order(qubo)
    return max(mini_bucket_bound(qubo, ibound=16, order=order),
               join_graph_bound(qubo, ibound=10, iters=60, order=order))
