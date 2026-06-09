"""Proof-of-Collapse: a self-contained, hash-chained certificate of a run.

The certificate is designed so an independent party (or a smart contract /
on-chain verifier) can confirm the result WITHOUT trusting the solver:

  * problem_hash   - sha256 of the canonical original QUBO
  * core_hash      - sha256 of the canonical irreducible core
  * dual           - roof-dual certificate (re-checkable by arithmetic)
  * assignment     - the full solution (its energy is re-evaluated directly)
  * lower_bound    - claimed certified bound (re-derived from `dual`)
  * energy         - claimed energy (re-evaluated from problem + assignment)

`certified_optimal` is true exactly when re-evaluated energy == re-derived
lower bound. See crown/verify.py for the trustless checker.
"""

from __future__ import annotations

import hashlib
import json
from typing import List

from .ising import QUBO
from .solve import CrownResult

CERT_VERSION = "crown-poc/0.1"


def _hash_obj(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_certificate(qubo: QUBO, result: CrownResult) -> dict:
    core = result.reduction.core
    cert = {
        "version": CERT_VERSION,
        "problem_hash": qubo.hash(),
        "core_hash": core.hash(),
        "n": qubo.n,
        "core_size": core.n,
        "core_width": result.core_width,
        "compression_ratio": result.compression_ratio,
        "fixed": {str(k): v for k, v in sorted(result.fixed.items())},
        "core_to_orig": result.reduction.core_to_orig,
        "assignment": list(map(int, result.assignment)),
        "lower_bound": result.lower_bound,
        "rigorous_lower_bound": result.rigorous_lower_bound,
        "core_lower_bound": result.core_lower_bound,
        "energy": result.energy,
        "gap": result.gap,
        "solve_method": result.solve_method,
        "certificate_kind": result.certificate_kind,
        "claimed_certified_optimal": result.certified_optimal,
        "dual": result.roof.certificate,
        "jglp": result.jglp_cert,
    }
    cert["certificate_hash"] = _hash_obj(
        {k: cert[k] for k in cert if k != "certificate_hash"}
    )
    return cert


def save_certificate(cert: dict, path: str) -> None:
    with open(path, "w") as fh:
        json.dump(cert, fh, indent=2, sort_keys=True)


def load_certificate(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)
