"""Standard, INTEGER-valued QUBO/Ising benchmark instances.

Integer coefficients matter for the head-to-head: toulbar2 then solves the
*identical* problem (no float rounding), so any disagreement on the optimum is a
real bug, not a precision artifact.

* `sk_spin_glass`  -- Sherrington-Kirkpatrick: complete graph, couplings in
  {-1,+1}. The canonical frustrated, high-treewidth hard instance.
* `random_maxcut`  -- max-cut on a random graph (unit weights), encoded as a QUBO
  minimisation whose optimum is -(max cut).
"""

from __future__ import annotations

import random

from crown.ising import QUBO


def sk_spin_glass(n: int, seed: int = 0) -> QUBO:
    """Ising H(s) = sum_{i<j} J_ij s_i s_j with J_ij in {-1,+1}, s in {-1,+1},
    written as a QUBO over x in {0,1} via s = 2x - 1."""
    rng = random.Random(seed)
    linear: dict = {}
    quadratic: dict = {}
    const = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            J = rng.choice((-1, 1))
            # J s_i s_j = J(2x_i-1)(2x_j-1) = 4J x_i x_j - 2J x_i - 2J x_j + J
            quadratic[(i, j)] = quadratic.get((i, j), 0.0) + 4 * J
            linear[i] = linear.get(i, 0.0) - 2 * J
            linear[j] = linear.get(j, 0.0) - 2 * J
            const += J
    return QUBO(n=n, linear=linear, quadratic=quadratic, const=const)


def random_maxcut(n: int, density: float = 0.5, seed: int = 0) -> QUBO:
    """Max-cut on a random graph (unit edge weights). Cut(i,j)=1 iff x_i != x_j;
    minimise E = sum_edges (2 x_i x_j - x_i - x_j)  ->  min E = -(max cut)."""
    rng = random.Random(seed)
    linear: dict = {}
    quadratic: dict = {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < density:
                quadratic[(i, j)] = quadratic.get((i, j), 0.0) + 2
                linear[i] = linear.get(i, 0.0) - 1
                linear[j] = linear.get(j, 0.0) - 1
    return QUBO(n=n, linear=linear, quadratic=quadratic)


FAMILIES = {
    "sk-spin-glass": lambda n, s: sk_spin_glass(n, seed=s),
    "max-cut": lambda n, s: random_maxcut(n, density=0.5, seed=s),
}
