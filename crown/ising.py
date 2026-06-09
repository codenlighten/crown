"""Core data model: a QUBO over binary variables x_i in {0, 1}.

Energy:

    E(x) = const + sum_i a_i x_i + sum_{i<j} b_ij x_i x_j

Because x_i^2 = x_i for binary variables, the diagonal of a QUBO matrix is the
linear part. We keep linear, quadratic and constant terms separately so the
reduction engine can substitute variables cleanly.

Everything here is exact integer/float arithmetic -- no solver, no
approximation. `energy()` is the trustless ground truth a verifier re-evaluates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Tuple, Sequence

import numpy as np


@dataclass
class QUBO:
    n: int
    linear: Dict[int, float] = field(default_factory=dict)
    quadratic: Dict[Tuple[int, int], float] = field(default_factory=dict)
    const: float = 0.0

    def __post_init__(self) -> None:
        # Normalise quadratic keys to i < j and drop explicit zeros.
        norm: Dict[Tuple[int, int], float] = {}
        for (i, j), b in self.quadratic.items():
            if i == j:
                self.linear[i] = self.linear.get(i, 0.0) + b
                continue
            key = (i, j) if i < j else (j, i)
            norm[key] = norm.get(key, 0.0) + b
        self.quadratic = {k: v for k, v in norm.items() if v != 0.0}
        self.linear = {i: v for i, v in self.linear.items() if v != 0.0}

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_matrix(cls, Q: np.ndarray, const: float = 0.0) -> "QUBO":
        """Build from an n x n matrix. Diagonal -> linear, off-diagonal -> quadratic.

        The matrix is symmetrised: Q_ij and Q_ji both contribute to coupling (i, j).
        """
        Q = np.asarray(Q, dtype=float)
        n = Q.shape[0]
        linear: Dict[int, float] = {}
        quadratic: Dict[Tuple[int, int], float] = {}
        for i in range(n):
            if Q[i, i] != 0.0:
                linear[i] = float(Q[i, i])
            for j in range(i + 1, n):
                b = float(Q[i, j] + Q[j, i])
                if b != 0.0:
                    quadratic[(i, j)] = b
        return cls(n=n, linear=linear, quadratic=quadratic, const=float(const))

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    def energy(self, x: Sequence[int]) -> float:
        """Exact energy of a full assignment x (each entry 0 or 1)."""
        if len(x) != self.n:
            raise ValueError(f"assignment has length {len(x)}, expected {self.n}")
        e = self.const
        for i, a in self.linear.items():
            if x[i]:
                e += a
        for (i, j), b in self.quadratic.items():
            if x[i] and x[j]:
                e += b
        return e

    def edges(self) -> list[Tuple[int, int]]:
        return sorted(self.quadratic.keys())

    # ------------------------------------------------------------------ #
    # Ising view (s = 2x - 1, s in {-1, +1})
    # ------------------------------------------------------------------ #
    def to_ising(self) -> Tuple[Dict[int, float], Dict[Tuple[int, int], float], float]:
        """Return (h, J, offset) with H(s) = offset + sum h_i s_i + sum J_ij s_i s_j."""
        h: Dict[int, float] = {i: 0.0 for i in range(self.n)}
        J: Dict[Tuple[int, int], float] = {}
        offset = self.const
        # x_i = (s_i + 1) / 2
        for i, a in self.linear.items():
            h[i] += a / 2.0
            offset += a / 2.0
        for (i, j), b in self.quadratic.items():
            J[(i, j)] = J.get((i, j), 0.0) + b / 4.0
            h[i] += b / 4.0
            h[j] += b / 4.0
            offset += b / 4.0
        h = {i: v for i, v in h.items() if v != 0.0}
        J = {k: v for k, v in J.items() if v != 0.0}
        return h, J, offset

    # ------------------------------------------------------------------ #
    # Canonical serialisation + hashing (basis of the certificate chain)
    # ------------------------------------------------------------------ #
    def canonical(self) -> dict:
        return {
            "n": self.n,
            "const": _f(self.const),
            "linear": [[i, _f(self.linear[i])] for i in sorted(self.linear)],
            "quadratic": [
                [i, j, _f(self.quadratic[(i, j)])] for (i, j) in self.edges()
            ],
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode()

    def hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _f(x: float) -> str:
    """Stable, round-trippable float string for hashing."""
    return repr(float(x))
