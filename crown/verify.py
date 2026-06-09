"""Trustless verifier for a Proof-of-Collapse certificate.

Run as:  python -m crown.verify <problem.json> <certificate.json>

The verifier NEVER calls the solver. It only:
  1. recomputes the problem hash and compares it to the certificate,
  2. re-evaluates the assignment's energy directly against the problem,
  3. re-checks the roof-dual certificate by arithmetic to recover the bound,
  4. confirms the bound <= energy, and flags optimality iff they are equal.

A tampered solution, a swapped problem, or a bogus lower bound all fail here.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import List

from .elimination import min_fill_order, wide_core_bound
from .ising import QUBO
from .reduce import reduce_qubo
from .rigorous import verify_jglp_certificate
from .roofdual import verify_dual_bound
from .search import solve_core_exact

_EXACT_WIDTH_LIMIT = 20
_AOBB_BUDGET = 300_000


@dataclass
class VerificationReport:
    ok: bool
    checks: List[tuple]      # (name, passed, detail)
    energy: float
    lower_bound: float
    certified_optimal: bool

    def __str__(self) -> str:
        lines = ["Proof-of-Collapse verification", "=" * 32]
        for name, passed, detail, required in self.checks:
            mark = "PASS" if passed else ("FAIL" if required else "----")
            tag = "" if required else "  (optimality, not required for ACCEPT)"
            lines.append(f"[{mark}] {name}: {detail}{tag}")
        lines.append("-" * 32)
        lines.append(f"verified energy      : {self.energy:.6g}")
        lines.append(f"verified lower bound : {self.lower_bound:.6g}")
        lines.append(f"CERTIFIED OPTIMAL    : {self.certified_optimal}")
        lines.append(f"OVERALL              : {'ACCEPT' if self.ok else 'REJECT'}")
        return "\n".join(lines)


def qubo_from_canonical(obj: dict) -> QUBO:
    linear = {int(i): float(a) for i, a in obj.get("linear", [])}
    quadratic = {(int(i), int(j)): float(b) for i, j, b in obj.get("quadratic", [])}
    return QUBO(n=int(obj["n"]), linear=linear, quadratic=quadratic, const=float(obj.get("const", 0.0)))


def verify(qubo: QUBO, cert: dict, tol: float = 1e-5) -> VerificationReport:
    # checks are (name, passed, detail, required_for_ACCEPT)
    checks: List[tuple] = []
    tolabs = lambda val: max(tol, tol * abs(val))

    # 1. problem identity
    ok_hash = qubo.hash() == cert.get("problem_hash")
    checks.append(("problem hash", ok_hash,
                   "matches" if ok_hash else "MISMATCH (certificate is for a different problem)", True))

    # 2. assignment well-formed + energy re-evaluation
    x = cert.get("assignment", [])
    ok_assign = len(x) == qubo.n and all(v in (0, 1) for v in x)
    energy = float("nan")
    if ok_assign:
        energy = qubo.energy(x)
        ok_energy = abs(energy - cert.get("energy", float("inf"))) <= tolabs(energy)
        checks.append(("assignment shape", True, f"{qubo.n} binary vars", True))
        checks.append(("energy re-evaluation", ok_energy,
                       f"recomputed {energy:.6g} vs claimed {cert.get('energy')}", True))
    else:
        checks.append(("assignment shape", False, "assignment missing/invalid", True))

    # 3. dual certificate -> lower bound, by arithmetic only
    ok_dual, lb, msg = verify_dual_bound(qubo, cert["dual"], tol=tol)
    checks.append(("dual lower-bound certificate", ok_dual, msg, True))
    if ok_dual:
        ok_lb_claim = abs(lb - cert.get("lower_bound", lb)) <= tolabs(lb)
        checks.append(("lower-bound matches claim", ok_lb_claim,
                       f"recomputed {lb:.6g} vs claimed {cert.get('lower_bound')}", True))

    # 3b. JGLP cluster certificate -> a (usually tighter) rigorous bound, by
    #     arithmetic only: the pairwise clusters must sum back to the QUBO and
    #     each cluster's minimum is recomputed. Sound for ANY such clusters.
    jglp_lb = float("-inf")
    if cert.get("jglp") is not None:
        ok_j, jlb, jmsg = verify_jglp_certificate(qubo, cert["jglp"], tol=tol)
        checks.append(("JGLP cluster certificate", ok_j, jmsg, True))
        if ok_j:
            jglp_lb = jlb

    # 4. soundness: the best trustless rigorous bound must not exceed the energy
    bound_tight = False
    if ok_assign and ok_dual:
        rigorous_lb = max(lb, jglp_lb)
        ok_bracket = rigorous_lb <= energy + tolabs(energy)
        checks.append(("rigorous bound <= energy (sound bracket)", ok_bracket,
                       f"{rigorous_lb:.6g} <= {energy:.6g}", True))
        bound_tight = abs(energy - rigorous_lb) <= tolabs(energy)

    # 5. core reconstruction + independent core lower bound (recompute tier).
    #    The verifier computes its OWN lower bound on the core; if it meets the
    #    achieved energy the solution is optimal -- sound regardless of how the
    #    prover obtained its bound (the only residual assumption is roof-dual
    #    strong persistency, used to reduce the shell). This is NOT required for
    #    ACCEPT: an honest `bracket` certificate fails it and is still accepted.
    core_opt_ok = False
    if ok_assign:
        fixed = {int(k): int(v) for k, v in cert.get("fixed", {}).items()}
        reduction = reduce_qubo(qubo, fixed)
        core = reduction.core
        ok_core_hash = core.hash() == cert.get("core_hash")
        checks.append(("core hash (shell reduction)", ok_core_hash,
                       "matches" if ok_core_hash else "MISMATCH", True))
        if ok_core_hash:
            order, width = min_fill_order(core)
            core_x = [x[orig] for orig in reduction.core_to_orig]
            consistent = abs(core.energy(core_x) - energy) <= tolabs(energy)
            claimed_opt = bool(cert.get("claimed_certified_optimal", False))
            if width <= _EXACT_WIDTH_LIMIT:
                proven, _, complete, _ = solve_core_exact(core)
                core_opt_ok = consistent and complete and abs(proven - energy) <= tolabs(energy)
                label = f"core optimal via exact re-solve (width {width})"
                detail = f"recomputed core min {proven:.6g} vs energy {energy:.6g}"
            else:
                core_lb = wide_core_bound(core, order=order)
                if core_lb >= energy - tolabs(energy):
                    core_opt_ok = consistent
                    label = f"core optimal via weighted-MB/JGLP bound (width {width})"
                    detail = f"recomputed core bound {core_lb:.6g} vs energy {energy:.6g}"
                elif claimed_opt:
                    # the bound alone doesn't prove it -- re-decompose and re-solve
                    # each component to confirm no completion beats `energy`.
                    proven, _, complete, _ = solve_core_exact(
                        core, incumbent_energy=energy, incumbent_x=core_x, flat_budget=_AOBB_BUDGET)
                    core_opt_ok = consistent and complete and abs(proven - energy) <= tolabs(energy)
                    label = f"core optimal via decompose + exhaustive re-search (width {width})"
                    detail = f"re-solved core min {proven:.6g} vs energy {energy:.6g}, complete={complete}"
                else:
                    core_opt_ok = False           # honest bracket; not claiming optimality
                    label = f"core lower bound (width {width})"
                    detail = f"bound {core_lb:.6g} < energy {energy:.6g} (bracket)"
            checks.append((label, core_opt_ok, detail, False))

    certified_optimal = bool(bound_tight or core_opt_ok)

    # 6. claim consistency: the prover may not overclaim optimality.
    claimed = bool(cert.get("claimed_certified_optimal", False))
    ok_claim = (not claimed) or certified_optimal
    checks.append(("optimality claim consistency", ok_claim,
                   f"claimed={claimed}, verifier_certified={certified_optimal}", True))

    ok = all(passed for _, passed, _, required in checks if required)
    return VerificationReport(
        ok=ok,
        checks=checks,
        energy=energy,
        lower_bound=max(lb, jglp_lb) if ok_dual else float("nan"),
        certified_optimal=certified_optimal,
    )


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m crown.verify <problem.json> <certificate.json>")
        return 2
    with open(argv[1]) as fh:
        qubo = qubo_from_canonical(json.load(fh))
    with open(argv[2]) as fh:
        cert = json.load(fh)
    report = verify(qubo, cert)
    print(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
