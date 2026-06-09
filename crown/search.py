"""Branch-and-bound search guided by the JGLP bound (bound-carrying search).

When a core is too wide for exact bucket elimination yet JGLP/weighted-MB does
not fully close the gap, this turns the bound into an EXACT solver: a depth-first
branch-and-bound whose node lower bound is read off the JGLP-reparameterised
clusters. Because JGLP reparameterisation preserves the total energy
(`const + Σ_c table_c(x) == E(x)`), the conditioned cluster sum is a provably
admissible heuristic:

    f(partial) = const + Σ_c  min_{free vars of c}  table_c(partial)
               ≤ const + min_{free} Σ_c table_c        (min of sum ≥ sum of mins)
               = min over completions of E

So `f` never overestimates the best reachable energy; pruning on `f ≥ incumbent`
is sound, and at a leaf `f` equals the exact energy. If the search completes
without hitting the node budget, the returned assignment is the GLOBAL optimum of
the core -- proven by exhaustion, hence certifiable. Conditioning is maintained
incrementally (only clusters touching the just-assigned variable are sliced), and
restored on backtrack.

`complete=False` means the budget was hit: the result is then only an upper bound
(best found), never claimed optimal.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .elimination import join_graph_clusters, min_fill_order
from .ising import QUBO


@dataclass
class SearchResult:
    energy: float
    assignment: List[int]
    complete: bool          # True => exhaustive => global optimum proven
    nodes: int
    bound: float            # JGLP root lower bound


def aobb_solve(core: QUBO, incumbent_energy: float = float("inf"),
               incumbent_x: Optional[List[int]] = None,
               ibound: int = 10, jglp_iters: int = 60,
               node_budget: int = 300_000, tol: float = 1e-9) -> SearchResult:
    n = core.n
    if n == 0:
        return SearchResult(core.const, [], True, 0, core.const)

    order_elim, _ = min_fill_order(core)
    clusters, const, trace = join_graph_clusters(core, ibound, jglp_iters, order_elim)
    root_bound = const + sum(float(c.table.min()) for c in clusters)

    # clusters touching each variable; branch most-constrained-first
    var_in: dict[int, List[int]] = {i: [] for i in range(n)}
    for ci, c in enumerate(clusters):
        for v in c.vars:
            var_in[v].append(ci)
    branch_order = sorted(range(n), key=lambda v: -len(var_in[v]))

    # mutable per-cluster state: current table over still-free vars, and its min
    cur_table = [c.table for c in clusters]
    cur_vars = [list(c.vars) for c in clusters]
    cur_min = [float(t.min()) for t in cur_table]

    best_e = incumbent_energy
    best_x = list(incumbent_x) if incumbent_x is not None else None
    assign = [0] * n
    state = {"nodes": 0, "complete": True}

    def assign_var(v: int, val: int):
        """Slice v=val into its clusters; return undo list and Δf."""
        undo = []
        df = 0.0
        for ci in var_in[v]:
            vars_ci = cur_vars[ci]
            ax = vars_ci.index(v)
            old_t, old_m, old_vars = cur_table[ci], cur_min[ci], vars_ci
            new_t = old_t.take(val, axis=ax)
            new_m = float(new_t.min())
            cur_table[ci] = new_t
            cur_min[ci] = new_m
            cur_vars[ci] = old_vars[:ax] + old_vars[ax + 1:]
            df += new_m - old_m
            undo.append((ci, old_t, old_m, old_vars))
        return undo, df

    def restore(undo):
        for ci, old_t, old_m, old_vars in undo:
            cur_table[ci] = old_t
            cur_min[ci] = old_m
            cur_vars[ci] = old_vars

    def dfs(depth: int, f: float):
        nonlocal best_e, best_x
        if state["nodes"] >= node_budget:
            state["complete"] = False
            return
        state["nodes"] += 1
        if f >= best_e - tol:                     # cannot beat the incumbent
            return
        if depth == n:
            if f < best_e - tol:
                best_e = f
                best_x = list(assign)
            return
        v = branch_order[depth]
        # try both values, diving into the locally cheaper one first
        trials = []
        for val in (0, 1):
            undo, df = assign_var(v, val)
            trials.append((f + df, val, undo))
            restore(undo)
        trials.sort(key=lambda t: t[0])
        for child_f, val, _ in trials:
            if child_f >= best_e - tol:
                continue
            undo, _ = assign_var(v, val)
            assign[v] = val
            dfs(depth + 1, child_f)
            restore(undo)
            if not state["complete"]:
                return

    dfs(0, root_bound)
    if best_x is None:                            # budget hit before any leaf
        best_x = [0] * n
    return SearchResult(best_e, best_x, state["complete"], state["nodes"], root_bound)


# --------------------------------------------------------------------------- #
# AND/OR branch-and-bound with context caching
# --------------------------------------------------------------------------- #
# A pseudo-tree of the interaction graph orders the variables so that every
# interaction edge connects a node to one of its pseudo-tree ancestors (a DFS
# tree has exactly this property). Then, once a variable and its ancestors are
# fixed, its child subtrees become CONDITIONALLY INDEPENDENT -- they are the
# "AND" branches, solved separately and summed. Two partial assignments that
# agree on a variable's *context* (the ancestors adjacent to its subtree) induce
# identical subproblems, so subtree optima are cached by context.
#
# Because QUBO costs can be negative, pruning needs a sound lower bound on each
# subtree (you cannot prune on accumulated cost alone). We use a conditioned
# per-factor bound that decomposes exactly along the pseudo-tree.


@dataclass
class _PTree:
    roots: List[int]
    children: Dict[int, List[int]]
    context: Dict[int, List[int]]        # ancestors whose values key the cache
    anc_edges: Dict[int, List[Tuple[int, float]]]   # edges to ancestors (realized here)
    unary: Dict[int, float]
    subtree: Dict[int, List[int]]        # variables in the subtree rooted at v
    components: List[List[int]]          # connected components (root -> its component)


def build_pseudo_tree(core: QUBO) -> _PTree:
    adj: Dict[int, set] = {i: set() for i in range(core.n)}
    for (i, j) in core.quadratic:
        adj[i].add(j)
        adj[j].add(i)

    visited: set = set()
    children: Dict[int, List[int]] = {i: [] for i in range(core.n)}
    parent: Dict[int, Optional[int]] = {}
    roots: List[int] = []
    comp_of: Dict[int, int] = {}

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, core.n * 4 + 100))
    try:
        for s in sorted(range(core.n), key=lambda v: -len(adj[v])):
            if s in visited:
                continue
            roots.append(s)
            stack = [(s, None, iter(sorted(adj[s])))]
            parent[s] = None
            comp_of[s] = s
            visited.add(s)
            while stack:                          # iterative DFS tree
                u, par, it = stack[-1]
                advanced = False
                for w in it:
                    if w not in visited:
                        visited.add(w)
                        parent[w] = u
                        comp_of[w] = s
                        children[u].append(w)
                        stack.append((w, u, iter(sorted(adj[w]))))
                        advanced = True
                        break
                if not advanced:
                    stack.pop()
    finally:
        sys.setrecursionlimit(old_limit)

    # ancestor chains
    ancestors: Dict[int, List[int]] = {}
    for v in range(core.n):
        chain, p = [], parent[v]
        while p is not None:
            chain.append(p)
            p = parent[p]
        ancestors[v] = chain
    anc_set = {v: set(ancestors[v]) for v in range(core.n)}

    # subtree variable lists (post-order via children)
    subtree: Dict[int, List[int]] = {}

    def build_subtree(v: int) -> List[int]:
        acc = [v]
        for c in children[v]:
            acc.extend(build_subtree(c))
        subtree[v] = acc
        return acc

    sys.setrecursionlimit(max(old_limit, core.n * 4 + 100))
    try:
        for r in roots:
            build_subtree(r)
    finally:
        sys.setrecursionlimit(old_limit)

    # edges to ancestors (each edge is realized at its deeper endpoint)
    unary = {i: core.linear.get(i, 0.0) for i in range(core.n)}
    anc_edges: Dict[int, List[Tuple[int, float]]] = {i: [] for i in range(core.n)}
    for (i, j), b in core.quadratic.items():
        if j in anc_set[i]:
            anc_edges[i].append((j, b))
        else:                                     # i is ancestor of j
            anc_edges[j].append((i, b))

    # context: ancestors adjacent to the subtree (these key the cache)
    context: Dict[int, List[int]] = {}
    for v in range(core.n):
        ctx = set()
        for y in subtree[v]:
            for (a, _b) in anc_edges[y]:
                if a in anc_set[v]:
                    ctx.add(a)
        context[v] = sorted(ctx)

    components: List[List[int]] = [subtree[r] for r in roots]
    return _PTree(roots, children, context, anc_edges, unary, subtree, components)


def aobb_andor_solve(core: QUBO, incumbent_energy: float = float("inf"),
                     incumbent_x: Optional[List[int]] = None,
                     node_budget: int = 2_000_000, tol: float = 1e-9,
                     heuristic=None) -> SearchResult:
    n = core.n
    if n == 0:
        return SearchResult(core.const, [], True, 0, core.const)

    pt = build_pseudo_tree(core)
    assign: Dict[int, int] = {}
    cache: Dict[Tuple, float] = {}
    choice: Dict[Tuple, int] = {}              # (node, context) -> optimal value
    state = {"nodes": 0, "complete": True}

    def conditioned_local(y: int, yval: int) -> float:
        """min realized cost contribution of y for value yval, relaxing the
        still-unassigned ancestors of y to their best (a sound lower bound)."""
        if yval == 0:
            return 0.0
        c = pt.unary[y]
        for (a, b) in pt.anc_edges[y]:
            if a in assign:
                c += b * assign[a]
            elif b < 0:
                c += b
        return c

    if heuristic is not None:                         # strong static mini-bucket
        def h(x: int) -> float:
            return heuristic.h(x, assign)
    else:                                             # cheap per-factor default
        def h(x: int) -> float:
            tot = 0.0
            for y in pt.subtree[x]:
                tot += min(0.0, conditioned_local(y, 1))
            return tot

    def solve(x: int, ub: float) -> float:
        key = (x, tuple(assign[a] for a in pt.context[x]))
        cached = cache.get(key)
        if cached is not None:
            return cached
        if state["nodes"] >= node_budget:
            state["complete"] = False
            return ub
        state["nodes"] += 1

        best = ub
        best_val = None
        kids = pt.children[x]
        for val in (0, 1):
            local = pt.unary[x] * val + sum(b * assign[a] * val for (a, b) in pt.anc_edges[x])
            assign[x] = val
            hs = [h(c) for c in kids]
            rem = sum(hs)
            if local + rem >= best - tol:                 # whole value pruned
                del assign[x]
                continue
            total = local
            ok = True
            for c, hc in zip(kids, hs):
                rem -= hc
                budget = best - total - rem
                if hc >= budget - tol:
                    ok = False
                    break
                sub = solve(c, budget)
                if sub >= budget - tol:                   # child can't beat budget
                    ok = False
                    break
                total += sub
            del assign[x]
            if ok and total < best - tol:
                best = total
                best_val = val
            if not state["complete"]:
                return best
        if best < ub - tol:                               # exact => cacheable
            cache[key] = best
            choice[key] = best_val
        return best

    # per-component upper bounds from the incumbent (components are independent)
    total = core.const
    if incumbent_x is not None:
        inc_cost = {}
        for r, comp in zip(pt.roots, pt.components):
            cval = sum(pt.unary[y] * incumbent_x[y] for y in comp)
            cval += sum(b * incumbent_x[i] * incumbent_x[j]
                        for (i, j), b in core.quadratic.items()
                        if i in pt.subtree[r] and j in pt.subtree[r])
            inc_cost[r] = cval
    else:
        inc_cost = {r: float("inf") for r in pt.roots}

    for r in pt.roots:
        total += solve(r, inc_cost[r] + abs(inc_cost[r]) * tol + tol)

    if not state["complete"]:
        # budget hit: fall back to the incumbent as a plain upper bound
        x = list(incumbent_x) if incumbent_x is not None else [0] * n
        return SearchResult(incumbent_energy, x, False, state["nodes"], core.const)

    # extract an optimal assignment top-down from the recorded choices -- pure
    # lookups, NO re-solving, so this can neither hit the budget nor flip the
    # `complete` flag. A missing choice means the subtree's optimum equalled the
    # incumbent bound it was solved under (never strictly improved), so the
    # incumbent assignment for that subtree is optimal.
    assign.clear()

    def extract(x: int) -> None:
        key = (x, tuple(assign[a] for a in pt.context[x]))
        val = choice.get(key)
        if val is None:
            for y in pt.subtree[x]:
                assign[y] = incumbent_x[y] if incumbent_x is not None else 0
            return
        assign[x] = val
        for c in pt.children[x]:
            extract(c)

    sys.setrecursionlimit(max(sys.getrecursionlimit(), n * 4 + 100))
    for r in pt.roots:
        extract(r)
    xsol = [assign[i] for i in range(n)]
    return SearchResult(core.energy(xsol), xsol, state["complete"], state["nodes"], core.const)


# --------------------------------------------------------------------------- #
# Connected-component decomposition (top-level AND) + unified exact core solve
# --------------------------------------------------------------------------- #
def _anneal(core: QUBO, seed: int = 0, iters: int = 20000) -> Tuple[List[int], float]:
    import math
    import random
    if core.n == 0:
        return [], core.const
    rng = random.Random(seed)
    x = [rng.randint(0, 1) for _ in range(core.n)]
    e = core.energy(x)
    best_x, best_e = list(x), e
    t0, t1 = 2.0, 0.01
    for t in range(iters):
        temp = t0 * (t1 / t0) ** (t / max(1, iters - 1))
        i = rng.randrange(core.n)
        x[i] ^= 1
        ne = core.energy(x)
        if ne <= e or rng.random() < math.exp(-(ne - e) / temp):
            e = ne
            if e < best_e:
                best_e, best_x = e, list(x)
        else:
            x[i] ^= 1
    return best_x, best_e


def connected_components(core: QUBO) -> List[Tuple[QUBO, List[int]]]:
    """Split a core into independent sub-QUBOs (one per connected component).

    Independent components are the top-level AND decomposition: their optima are
    solved separately and summed. The QUBO constant is kept with the caller and
    is NOT duplicated into the sub-QUBOs.
    """
    adj: Dict[int, set] = {i: set() for i in range(core.n)}
    for (i, j) in core.quadratic:
        adj[i].add(j)
        adj[j].add(i)
    seen: set = set()
    comps: List[List[int]] = []
    for s in range(core.n):
        if s in seen:
            continue
        stack = [s]
        seen.add(s)
        comp = [s]
        while stack:
            u = stack.pop()
            for w in adj[u]:
                if w not in seen:
                    seen.add(w)
                    comp.append(w)
                    stack.append(w)
        comps.append(sorted(comp))

    out: List[Tuple[QUBO, List[int]]] = []
    for comp in comps:
        idx = {v: k for k, v in enumerate(comp)}
        lin = {idx[v]: core.linear[v] for v in comp if v in core.linear}
        quad = {(idx[i], idx[j]): b for (i, j), b in core.quadratic.items() if i in idx}
        out.append((QUBO(n=len(comp), linear=lin, quadratic=quad), comp))
    return out


_EXACT_WIDTH_LIMIT = 20


def solve_core_exact(core: QUBO, incumbent_energy: float = float("inf"),
                     incumbent_x: Optional[List[int]] = None, seed: int = 0,
                     flat_budget: int = 300_000):
    """Exactly solve a core by decomposing into independent components.

    Each component is solved with the best available exact method: bucket
    elimination if its induced width is small, else JGLP-bound-guided
    branch-and-bound (seeded with an annealing or supplied incumbent). Returns
    (energy, assignment, complete, method). `complete` is True only if every
    component was solved to proven optimality.
    """
    from .elimination import bucket_elimination

    total = core.const
    assignment = [0] * core.n
    complete = True
    methods: set = set()

    for sub, comp in connected_components(core):
        if incumbent_x is not None:
            ix = [incumbent_x[v] for v in comp]
            ie = sub.energy(ix)
        else:
            ix, ie = _anneal(sub, seed=seed)
        order, width = min_fill_order(sub)
        if width <= _EXACT_WIDTH_LIMIT:
            e, x = bucket_elimination(sub, order)
            c = True
            methods.add("BE")
        else:
            r = aobb_solve(sub, incumbent_energy=ie, incumbent_x=ix, node_budget=flat_budget)
            e, x, c = r.energy, r.assignment, r.complete
            methods.add("AOBB" if c else "AOBB-partial")
        total += e
        for k, v in enumerate(comp):
            assignment[v] = x[k]
        complete = complete and c

    return total, assignment, complete, "+".join(sorted(methods)) if methods else "trivial"
