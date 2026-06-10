"""Measure a Proof-of-Collapse certificate *as an arithmetic circuit*.

The certificate is verified by pure arithmetic (see `crown/verify.py`), so its
on-chain / SNARK cost is the size of that arithmetic. We count it here.

The verifier does three things; we count each:

  1. evaluate Q(x*)  -- one multiplication per quadratic term (the upper bound);
  2. reparameterisation identity  -- accumulate the clusters' pairwise
     coefficients and compare to Q (additions + equality checks); and
  3. per-cluster minima  -- for a cluster of scope s, enumerate 2^s assignments
     and take the min (2^s evaluations + 2^s - 1 comparisons), then check the
     total equals the optimum.

Headline metric: ``r1cs_constraints ≈ m_Q + Σ_c 2^{scope_c}`` -- the
multiplications and comparison gates that dominate a SNARK / on-chain verifier.
The dominant, controllable term is ``Σ_c 2^{scope_c}``, which is exactly what the
greedy `minimize_certificate` shrinks (fewer / non-overlapping clusters) while
provably preserving the certificate (it stays a valid, tight reparameterisation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .ising import QUBO


@dataclass
class CertificateCost:
    mults: int                # multiplications  (Q(x*) evaluation)
    comparisons: int          # comparisons      (cluster minima)
    equalities: int           # equality checks  (reparam identity + final bound)
    adds: int                 # additions        (everything else)
    r1cs_constraints: int     # SNARK/on-chain proxy:  m_Q + Σ_c 2^{scope_c}
    n_clusters: int
    max_scope: int
    n_coeffs: int             # nonzero cluster coefficients
    n_bytes: int              # serialized certificate size

    def summary(self) -> str:
        return (f"clusters={self.n_clusters} max_scope={self.max_scope} "
                f"coeffs={self.n_coeffs} bytes={self.n_bytes} | "
                f"r1cs≈{self.r1cs_constraints} (mults={self.mults} "
                f"comparisons={self.comparisons})")


def certificate_cost(qubo: QUBO, cert: dict) -> CertificateCost:
    m_q = len(qubo.quadratic)
    mults = m_q
    adds = len(qubo.linear) + m_q              # eval Q(x*)
    comparisons = 0
    sum_enum = 0
    max_scope = 0
    n_coeffs = 0
    for cl in cert["clusters"]:
        s = len(cl["vars"])
        sc = 1 << s
        sum_enum += sc
        max_scope = max(max_scope, s)
        terms = len(cl["linear"]) + len(cl["quadratic"])
        n_coeffs += (1 if cl.get("const") else 0) + terms
        comparisons += sc - 1                  # min over 2^s values
        adds += sc * terms                     # evaluate each of the 2^s costs
    adds += n_coeffs                           # accumulate clusters back to Q
    equalities = len(qubo.linear) + len(qubo.quadratic) + 1 + 1  # identity + bound
    r1cs = m_q + sum_enum
    n_bytes = len(json.dumps(cert, separators=(",", ":")).encode())
    return CertificateCost(mults, comparisons, equalities, adds, r1cs,
                           len(cert["clusters"]), max_scope, n_coeffs, n_bytes)


# --------------------------------------------------------------------------- #
# Validity-preserving minimiser
# --------------------------------------------------------------------------- #
def _is_zero(cl: dict, tol: float = 1e-12) -> bool:
    return (abs(cl.get("const", 0.0)) <= tol
            and all(abs(a) <= tol for _, a in cl["linear"])
            and all(abs(b) <= tol for *_, b in cl["quadratic"]))


def _prune_scope(cl: dict) -> None:
    """Drop variables that have no coefficient in the cluster -- lossless: the
    cluster's min (and the 2^scope enumeration) is unchanged, the cost shrinks.
    This is the main lever on the dominant 2^scope term."""
    used = {i for i, _ in cl["linear"]}
    for i, j, _ in cl["quadratic"]:
        used.add(i)
        used.add(j)
    cl["vars"] = [v for v in cl["vars"] if v in used]


def _merge_into(dst: dict, src: dict) -> None:
    """Add src's coefficients into dst (dst's scope must contain src's)."""
    dst["const"] = dst.get("const", 0.0) + src.get("const", 0.0)
    lin = {i: a for i, a in dst["linear"]}
    for i, a in src["linear"]:
        lin[i] = lin.get(i, 0.0) + a
    dst["linear"] = [[i, a] for i, a in lin.items() if abs(a) > 1e-12]
    quad = {(i, j): b for i, j, b in dst["quadratic"]}
    for i, j, b in src["quadratic"]:
        key = (i, j) if i < j else (j, i)
        quad[key] = quad.get(key, 0.0) + b
    dst["quadratic"] = [[i, j, b] for (i, j), b in quad.items() if abs(b) > 1e-12]


def minimize_certificate(cert: dict) -> dict:
    """Shrink the certificate's circuit (fewer / non-overlapping clusters) WITHOUT
    changing what it proves.

    Every move preserves both invariants the verifier checks:
      * the clusters still sum to Q (we only move coefficients between clusters,
        never change the total), and
      * the bound stays tight: merging can only raise `Σ_c min cluster_c`, and it
        is always ≤ the true minimum, so a tight bound stays tight.

    Moves: drop all-zero clusters; merge clusters with identical scope; absorb a
    cluster whose scope is a subset of another's. All strictly reduce
    `Σ_c 2^{scope_c}` (the dominant cost) or the cluster count.
    """
    clusters = [dict(vars=list(c["vars"]), const=float(c.get("const", 0.0)),
                     linear=[list(t) for t in c["linear"]],
                     quadratic=[list(t) for t in c["quadratic"]])
                for c in cert["clusters"]]

    changed = True
    while changed:
        changed = False
        for c in clusters:
            _prune_scope(c)                    # lossless: shrink each scope first
        clusters = [c for c in clusters if not _is_zero(c)]
        # merge identical scopes
        by_scope: Dict[Tuple[int, ...], dict] = {}
        merged: List[dict] = []
        for c in clusters:
            key = tuple(sorted(c["vars"]))
            if key in by_scope:
                _merge_into(by_scope[key], c)
                changed = True
            else:
                by_scope[key] = c
                merged.append(c)
        clusters = merged
        # absorb a subset-scope cluster into a strict superset
        clusters.sort(key=lambda c: len(c["vars"]))
        i = 0
        while i < len(clusters):
            ci = clusters[i]
            si = set(ci["vars"])
            host = next((cj for cj in clusters if cj is not ci and si < set(cj["vars"])), None)
            if host is not None:
                _merge_into(host, ci)
                clusters.pop(i)
                changed = True
            else:
                i += 1

    out = {"const": cert["const"], "clusters": []}
    for c in clusters:
        out["clusters"].append({
            "vars": sorted(c["vars"]),
            "const": c["const"],
            "linear": [[i, a] for i, a in c["linear"]],
            "quadratic": [[min(i, j), max(i, j), b] for i, j, b in c["quadratic"]],
        })
    return out
