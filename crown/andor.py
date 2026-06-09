"""AND/OR branch-and-bound with a static mini-bucket heuristic (JGLP-strength).

This unifies the two strengths from earlier layers:

  * the recursive AND/OR decomposition + context caching (cuts the search on
    problems that split into independent subproblems), and
  * a strong, mini-bucket-derived heuristic (the flat JGLP-guided search showed
    a strong bound dominates a cheap per-factor one on dense cores).

The heuristic must DECOMPOSE per pseudo-tree subtree -- the global JGLP bound
does not, because cost-shifting moves cost across subtree boundaries. The
standard tool that does decompose is the **static mini-bucket heuristic**
(Kask & Dechter): eliminate variables along the pseudo-tree order (deepest
first), and for the cost-to-go of a subtree, sum the mini-bucket messages that
cross OUT of that subtree (their scope lies entirely in the subtree's context,
so they evaluate to a scalar once the context is assigned). Each message is a
min-relaxation, so the sum is a sound lower bound on the subtree's optimal cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .elimination import Factor, _combine, _initial_factors, _min_marginal, _shift
from .ising import QUBO
from .search import _PTree, build_pseudo_tree


def _parent_depth(pt: _PTree) -> Tuple[Dict[int, Optional[int]], Dict[int, int]]:
    parent: Dict[int, Optional[int]] = {}
    depth: Dict[int, int] = {}
    for r in pt.roots:
        parent[r] = None
        depth[r] = 0
        stack = [r]
        while stack:
            u = stack.pop()
            for c in pt.children[u]:
                parent[c] = u
                depth[c] = depth[u] + 1
                stack.append(c)
    return parent, depth


@dataclass
class StaticMBHeuristic:
    crossings: Dict[int, List[Factor]]    # node -> messages crossing out of its subtree
    parent: Dict[int, Optional[int]]
    depth: Dict[int, int]

    def h(self, node: int, assign: Dict[int, int]) -> float:
        tot = 0.0
        for msg in self.crossings[node]:
            if msg.vars:
                tot += float(msg.table[tuple(assign[v] for v in msg.vars)])
            else:
                tot += float(msg.table)
        return tot


def build_static_mb_heuristic(core: QUBO, pt: _PTree, ibound: int = 12,
                              moment_match: bool = True) -> StaticMBHeuristic:
    parent, depth = _parent_depth(pt)
    n = core.n
    order = sorted(range(n), key=lambda v: -depth[v])     # deepest first

    buckets: Dict[int, List[Factor]] = {v: [] for v in range(n)}
    for f in _initial_factors(core):
        dv = max(f.vars, key=lambda v: depth[v])          # place at deepest variable
        buckets[dv].append(f)

    messages: List[Tuple[int, Optional[int], Factor]] = []   # (source, dest, msg)
    for v in order:
        fs = buckets[v]
        if not fs:
            continue
        fs.sort(key=lambda f: len(f.vars), reverse=True)
        groups: List[List[Factor]] = []
        for f in fs:
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
        # bucket-tree cost-shifting: equalise v's min-marginal across the
        # mini-buckets of this bucket. The shift is a zero-sum function of v and
        # every mini-bucket here is anchored at v -> same pseudo-tree subtree, so
        # this tightens the heuristic WITHOUT crossing a subtree boundary
        # (decomposition preserved). It removes the mini-bucket splitting slack.
        if moment_match and len(combined) > 1:
            margs = [_min_marginal(c, v) for c in combined]
            avg = sum(margs) / len(margs)
            for c, m in zip(combined, margs):
                _shift(c, v, avg - m)
        for comb in combined:
            ax = comb.vars.index(v)
            red = comb.table.min(axis=ax)
            new_vars = tuple(u for u in comb.vars if u != v)
            if new_vars:
                msg = Factor(new_vars, red)
                dest = max(new_vars, key=lambda u: depth[u])
                buckets[dest].append(msg)
                messages.append((v, dest, msg))
            else:
                messages.append((v, None, Factor((), np.asarray(float(red)))))

    crossings: Dict[int, List[Factor]] = {v: [] for v in range(n)}
    for (src, dest, msg) in messages:
        node = src
        while node is not None and node != dest:           # path src .. (exclusive) dest
            crossings[node].append(msg)
            node = parent[node]
    return StaticMBHeuristic(crossings, parent, depth)


def aobb_andor_mb_solve(core: QUBO, incumbent_energy: float = float("inf"),
                        incumbent_x: Optional[List[int]] = None, ibound: int = 16,
                        node_budget: int = 2_000_000, moment_match: bool = True):
    """AND/OR branch-and-bound + caching guided by the static mini-bucket heuristic.

    With moment_match (bucket-tree cost-shifting) the heuristic is markedly
    tighter -- on demo E it cut the search from ~114k to ~19k nodes, faster in
    wall-clock than flat JGLP-AOBB.
    """
    from .search import aobb_andor_solve
    if core.n == 0:
        return aobb_andor_solve(core, incumbent_energy, incumbent_x, node_budget=node_budget)
    pt = build_pseudo_tree(core)
    H = build_static_mb_heuristic(core, pt, ibound=ibound, moment_match=moment_match)
    return aobb_andor_solve(core, incumbent_energy, incumbent_x,
                            node_budget=node_budget, heuristic=H)
