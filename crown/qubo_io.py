"""Read/write QUBO problems in two formats.

* canonical JSON  (``.json``): ``{"n", "const", "linear": [[i,a]],
  "quadratic": [[i,j,b]]}`` -- the same form `QUBO.canonical()` emits and the
  certificate chain hashes, so it round-trips exactly.

* sparse triplet  (``.txt`` / ``.qubo``): one term per line, easy to hand-write
  and to export from other tools::

      # comment lines start with '#'
      n 5            # optional explicit variable count (else inferred)
      c -2.0         # optional constant ('c' or 'const')
      0 0  1.5       # i == j  -> linear term on variable 0
      0 3 -2.0       # i != j  -> quadratic coupling (0,3)
"""

from __future__ import annotations

import json
from typing import Dict, Tuple

from .ising import QUBO


def qubo_from_canonical(obj: dict) -> QUBO:
    linear = {int(i): float(a) for i, a in obj.get("linear", [])}
    quadratic = {(int(i), int(j)): float(b) for i, j, b in obj.get("quadratic", [])}
    return QUBO(n=int(obj["n"]), linear=linear, quadratic=quadratic,
                const=float(obj.get("const", 0.0)))


def _load_triplets(text: str) -> QUBO:
    n = None
    const = 0.0
    linear: Dict[int, float] = {}
    quadratic: Dict[Tuple[int, int], float] = {}
    max_idx = -1
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tok = line.split()
        head = tok[0].lower()
        if head == "n":
            n = int(tok[1])
            continue
        if head in ("c", "const"):
            const = float(tok[1])
            continue
        if len(tok) != 3:
            raise ValueError(f"bad triplet line: {raw!r}")
        i, j, v = int(tok[0]), int(tok[1]), float(tok[2])
        max_idx = max(max_idx, i, j)
        if i == j:
            linear[i] = linear.get(i, 0.0) + v
        else:
            key = (i, j) if i < j else (j, i)
            quadratic[key] = quadratic.get(key, 0.0) + v
    if n is None:
        n = max_idx + 1
    return QUBO(n=n, linear=linear, quadratic=quadratic, const=const)


def load_qubo(path: str) -> QUBO:
    with open(path) as fh:
        text = fh.read()
    if path.endswith(".json"):
        return qubo_from_canonical(json.loads(text))
    return _load_triplets(text)


def save_qubo(qubo: QUBO, path: str) -> None:
    with open(path, "w") as fh:
        json.dump(qubo.canonical(), fh, indent=2)
