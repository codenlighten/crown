"""Reduction / lift: collapse the reducible shell, keep the irreducible core.

Given persistencies (variable -> fixed 0/1) from roof duality, we substitute
those variables out of the QUBO. What remains is a smaller QUBO over the
undecided variables -- the irreducible core. `lift` reconstructs a full
assignment from a core assignment by re-inserting the fixed values.

Substituting x_i = v into the energy:
  * const            += a_i * v
  * b_ij x_i x_j  ->  (b_ij * v) x_j        (becomes linear on the survivor)
  * if both endpoints fixed, the term folds entirely into const.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .ising import QUBO


@dataclass
class Reduction:
    core: QUBO
    fixed: Dict[int, int]          # original variable -> fixed value
    core_to_orig: List[int]        # core index -> original variable index
    orig_to_core: Dict[int, int]   # original variable -> core index


def reduce_qubo(qubo: QUBO, persistencies: Dict[int, int]) -> Reduction:
    survivors = [i for i in range(qubo.n) if i not in persistencies]
    orig_to_core = {orig: k for k, orig in enumerate(survivors)}

    const = qubo.const
    linear: Dict[int, float] = {}

    def add_lin(orig: int, val: float) -> None:
        k = orig_to_core[orig]
        linear[k] = linear.get(k, 0.0) + val

    for i, a in qubo.linear.items():
        if i in persistencies:
            const += a * persistencies[i]
        else:
            add_lin(i, a)

    quadratic: Dict[tuple, float] = {}
    for (i, j), b in qubo.quadratic.items():
        fi = i in persistencies
        fj = j in persistencies
        if fi and fj:
            const += b * persistencies[i] * persistencies[j]
        elif fi:
            if persistencies[i]:
                add_lin(j, b)
        elif fj:
            if persistencies[j]:
                add_lin(i, b)
        else:
            quadratic[(orig_to_core[i], orig_to_core[j])] = b

    core = QUBO(n=len(survivors), linear=linear, quadratic=quadratic, const=const)
    return Reduction(
        core=core,
        fixed=dict(persistencies),
        core_to_orig=survivors,
        orig_to_core=orig_to_core,
    )


def lift(reduction: Reduction, core_assignment: List[int], n: int) -> List[int]:
    """Reconstruct a full length-n assignment from a core assignment."""
    x = [0] * n
    for orig, val in reduction.fixed.items():
        x[orig] = val
    for k, orig in enumerate(reduction.core_to_orig):
        x[orig] = core_assignment[k]
    return x
