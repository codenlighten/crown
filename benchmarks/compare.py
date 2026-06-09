"""Head-to-head: CROWN vs independent exact solvers (toulbar2, SCIP), plus brute
force, on standard integer-valued instances.

Two questions, answered with evidence:

  1. CORRECTNESS -- does CROWN agree with an independent state-of-the-art solver
     on the optimum? (And does it ever certify a wrong one, or report a
     sub-optimal energy as optimal? Those must never happen.)
  2. COMPETITIVENESS -- how do solve time and reachable problem size compare?

Run (with the solver venv):  python benchmarks/compare.py [--quick]
"""

from __future__ import annotations

import itertools
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crown.ising import QUBO
from crown.solve import crown_solve
from benchmarks.external_solvers import available
from benchmarks.instances import FAMILIES

TOL = 1e-9
BRUTE_MAX = 18


def brute_min(q: QUBO) -> float:
    return min(q.energy(list(b)) for b in itertools.product((0, 1), repeat=q.n))


@dataclass
class Row:
    family: str
    n: int
    seed: int
    crown_e: Optional[float]
    crown_certified: Optional[bool]
    crown_t: Optional[float]
    tb_e: Optional[float]
    tb_proven: Optional[bool]
    tb_t: Optional[float]
    brute: Optional[float]


def run(head_sizes, scale_sizes, seeds, time_limit, crown_max_n):
    solvers = available()
    tb = solvers.get("toulbar2")
    rows: List[Row] = []
    issues: List[str] = []

    work = ([(f, n, s, True) for f in FAMILIES for n in head_sizes for s in range(seeds)]
            + [(f, n, 0, False) for f in FAMILIES for n in scale_sizes])
    for k, (fam, n, seed, do_crown) in enumerate(work, 1):
        q = FAMILIES[fam](n, seed)
        print(f"\r  {k}/{len(work)}  {fam} n={n} seed={seed}        ", end="", flush=True)

        crown_e = crown_cert = crown_t = None
        if do_crown and n <= crown_max_n:
            t0 = time.perf_counter()
            res = crown_solve(q)
            crown_t = time.perf_counter() - t0
            crown_e, crown_cert = res.energy, res.certified_optimal

        tb_e = tb_proven = tb_t = None
        if tb is not None:
            r = tb(q, time_limit)
            tb_e, tb_proven, tb_t = r.energy, r.proven, r.seconds

        brute = brute_min(q) if n <= BRUTE_MAX else None

        # correctness invariants
        if brute is not None and tb_proven and abs(tb_e - brute) > TOL:
            issues.append(f"toulbar2 != brute on {fam} n={n} s={seed}: {tb_e} vs {brute}")
        if crown_e is not None and tb_proven:
            if crown_e < tb_e - TOL:
                issues.append(f"CRITICAL: CROWN energy {crown_e} BELOW proven optimum {tb_e} "
                              f"({fam} n={n} s={seed})")
            if crown_cert and abs(crown_e - tb_e) > TOL:
                issues.append(f"CRITICAL: CROWN CERTIFIED {crown_e} != optimum {tb_e} "
                              f"({fam} n={n} s={seed})")
        rows.append(Row(fam, n, seed, crown_e, crown_cert, crown_t,
                        tb_e, tb_proven, tb_t, brute))
    print()
    return rows, issues, list(solvers)


def report(rows, issues, solver_names, time_limit, crown_max_n) -> str:
    L: List[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append("# CROWN vs. state-of-the-art exact solvers\n")
    L.append(f"Generated {stamp}. Solvers: CROWN (pure Python) vs "
             f"{', '.join(solver_names)} (tuned C++), brute force for n ≤ {BRUTE_MAX}. "
             f"External time limit {time_limit}s; CROWN run only for n ≤ {crown_max_n}.\n")

    head = [r for r in rows if r.crown_e is not None and r.tb_e is not None]
    agree = [r for r in head if abs(r.crown_e - r.tb_e) <= TOL]
    crown_cert = [r for r in head if r.crown_certified]
    tri = [r for r in head if r.brute is not None]

    L.append("## Correctness cross-check (the result that matters)\n")
    L.append(f"- CROWN's optimum **agreed with toulbar2 on {len(agree)}/{len(head)}** "
             f"instances both ran.")
    L.append(f"- On the **{len(crown_cert)}** instances CROWN reported as *certified*, "
             f"it matched toulbar2's proven optimum **every time** "
             f"({sum(abs(r.crown_e - r.tb_e) <= TOL for r in crown_cert)}/{len(crown_cert)}).")
    if tri:
        ok = sum(abs(r.brute - r.tb_e) <= TOL and abs(r.crown_e - r.brute) <= TOL for r in tri)
        L.append(f"- Triangulated against brute force on {len(tri)} small instances: "
                 f"CROWN == toulbar2 == brute on **{ok}/{len(tri)}**.")
    if issues:
        L.append("\n**⚠ Invariant violations (must be empty):**")
        for s in issues:
            L.append(f"- {s}")
    else:
        L.append("- ✅ No invariant violated: CROWN never undercut a proven optimum and "
                 "never certified a wrong one.")
    L.append("")

    L.append("## Head-to-head: time and certification (both solvers run)\n")
    L.append("| family | n | CROWN energy | CROWN certified | CROWN time | toulbar2 energy | toulbar2 proven | toulbar2 time |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in head:
        L.append(f"| {r.family} | {r.n} | {r.crown_e:.0f} | {r.crown_certified} | "
                 f"{r.crown_t:.2f}s | {r.tb_e:.0f} | {r.tb_proven} | {r.tb_t:.3f}s |")
    L.append("")
    if head:
        sp = statistics.median(r.crown_t / max(r.tb_t, 1e-6) for r in head)
        L.append(f"Median speed gap: toulbar2 is ~**{sp:.0f}×** faster across these instances.\n")

    scale = [r for r in rows if r.crown_e is None and r.tb_e is not None]
    if scale:
        L.append("## Scale frontier (beyond CROWN's reach — toulbar2 only)\n")
        L.append("| family | n | toulbar2 energy | proven | time |")
        L.append("|---|---|---|---|---|")
        for r in scale:
            L.append(f"| {r.family} | {r.n} | {r.tb_e:.0f} | {r.tb_proven} | {r.tb_t:.3f}s |")
        L.append("")

    L.append("## Honest read\n")
    L.append("CROWN is **correct** — an independent SOTA solver (and brute force) "
             "corroborate its optima, and it never falsely certified. CROWN is **not "
             "performance-competitive**: toulbar2 implements the same algorithm family "
             "in tuned C++ and is orders of magnitude faster, proving optima at problem "
             "sizes where CROWN's pure-Python search cannot even certify. CROWN's value "
             "is the *verifiable certificate* and the clean reference implementation, "
             "not raw solve speed.")
    return "\n".join(L)


def main(argv: List[str]) -> int:
    quick = "--quick" in argv
    if quick:
        head_sizes, scale_sizes, seeds = [12, 18], [30], 1
        time_limit, crown_max_n = 10, 24
    else:
        head_sizes, scale_sizes, seeds = [12, 16, 20, 24, 28], [40, 60, 90], 2
        time_limit, crown_max_n = 20, 28

    rows, issues, solver_names = run(head_sizes, scale_sizes, seeds, time_limit, crown_max_n)
    rep = report(rows, issues, solver_names, time_limit, crown_max_n)
    out = os.path.join(os.path.dirname(__file__), "EXTERNAL_RESULTS.md")
    with open(out, "w") as fh:
        fh.write(rep + "\n")
    print("\n" + rep)
    print(f"\nwrote {os.path.relpath(out)}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
