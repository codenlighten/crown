"""Test/demo QUBO generators with known structure.

These build instances whose "reducible shell vs irreducible core" split is known
in advance, so we can demonstrate (and test) hardness distillation honestly.
"""

from __future__ import annotations

import random
from typing import Dict, Tuple

from .ising import QUBO


def make_field_dominated(n: int, seed: int = 0) -> QUBO:
    """Every variable is individually forced: |field| > sum of incident couplings.

    Roof duality decides all variables and its lower bound is tight, so the
    CROWN pipeline returns a CERTIFIED-OPTIMAL result with 100% compression.
    """
    rng = random.Random(seed)
    linear: Dict[int, float] = {}
    quadratic: Dict[Tuple[int, int], float] = {}
    coupling_budget = {i: 0.0 for i in range(n)}

    # light random couplings first
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.05:
                b = rng.uniform(-1.0, 1.0)
                quadratic[(i, j)] = b
                coupling_budget[i] += abs(b)
                coupling_budget[j] += abs(b)

    # fields strong enough to dominate every variable's incident couplings
    for i in range(n):
        mag = coupling_budget[i] + rng.uniform(2.0, 5.0)
        linear[i] = mag if rng.random() < 0.5 else -mag

    return QUBO(n=n, linear=linear, quadratic=quadratic)


def _antiferro_triangle(base: int, strength: float = 1.0) -> QUBO:
    """A frustrated 3-clique (antiferromagnetic Ising) over vars base..base+2.

    Ising J*s_i*s_j with J>0 prefers s_i != s_j; on a triangle this is
    unsatisfiable -> frustration. In QUBO terms (s = 2x-1):
        J s_i s_j = 4J x_i x_j - 2J x_i - 2J x_j + J
    """
    linear: Dict[int, float] = {}
    quadratic: Dict[Tuple[int, int], float] = {}
    const = 0.0
    tri = [base, base + 1, base + 2]
    for a in range(3):
        for b in range(a + 1, 3):
            i, j = tri[a], tri[b]
            quadratic[(i, j)] = 4 * strength
            linear[i] = linear.get(i, 0.0) - 2 * strength
            linear[j] = linear.get(j, 0.0) - 2 * strength
            const += strength
    return QUBO(n=base + 3, linear=linear, quadratic=quadratic, const=const)


def make_shell_with_core(shell: int = 100, n_triangles: int = 4, seed: int = 0) -> QUBO:
    """A large field-dominated shell plus several frustrated triangles (the core).

    Roof duality fixes the shell (~`shell` variables) and leaves the
    3*n_triangles frustrated variables undecided -> a small irreducible core
    that is solved exactly by brute force, with an honest residual gap.
    """
    base = make_field_dominated(shell, seed=seed)
    n = shell + 3 * n_triangles
    linear = dict(base.linear)
    quadratic = dict(base.quadratic)
    const = base.const
    for t in range(n_triangles):
        tri = _antiferro_triangle(shell + 3 * t, strength=1.0)
        for i, a in tri.linear.items():
            linear[i] = linear.get(i, 0.0) + a
        for e, b in tri.quadratic.items():
            quadratic[e] = quadratic.get(e, 0.0) + b
        const += tri.const
    return QUBO(n=n, linear=linear, quadratic=quadratic, const=const)


def make_random(n: int, density: float = 0.5, seed: int = 0, scale: float = 1.0) -> QUBO:
    """Dense random QUBO -- a stress test with no planted structure."""
    rng = random.Random(seed)
    linear = {i: rng.uniform(-scale, scale) for i in range(n)}
    quadratic: Dict[Tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < density:
                quadratic[(i, j)] = rng.uniform(-scale, scale)
    return QUBO(n=n, linear=linear, quadratic=quadratic)
