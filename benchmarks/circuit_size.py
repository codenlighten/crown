"""Probe: how big is CROWN's optimality certificate *as a verification circuit*?

Decouple find-from-prove: an independent solver (toulbar2) finds the optimum
fast; we then ask whether CROWN's JGLP reparameterisation *certifies* it (bound ==
optimum) and, if so, measure the certificate's circuit cost (`crown.circuit`).

The question this answers: is the transparent on-chain certificate cheap enough to
matter, and how does its cost scale with problem size and with the i-bound (the
cluster-size knob that trades certificate existence against `2^scope` blow-up)?

Run (with the solver venv):  python benchmarks/circuit_size.py [--quick]
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crown.circuit import certificate_cost, minimize_certificate
from crown.rigorous import jglp_certificate, verify_jglp_certificate
from benchmarks.external_solvers import available
from benchmarks.instances import FAMILIES

TOL = 1e-6


def measure(family: str, n: int, seed: int, ibound: int, tb) -> dict:
    q = FAMILIES[family](n, seed)
    estar = tb(q, 20).energy                       # toulbar2 finds the optimum
    row = {"family": family, "n": n, "ibound": ibound, "certifies": False}
    out = jglp_certificate(q, ibound=ibound, iters=120)
    if out is None:
        row["note"] = "non-pairwise"
        return row
    cert, lb = out
    if abs(lb - estar) > max(TOL, TOL * abs(estar)):
        row["note"] = "gap"                        # JGLP can't close the integrality gap here
        return row

    cmin = minimize_certificate(cert)
    ok, vlb, _ = verify_jglp_certificate(q, cmin)  # independent re-check of the minimised cert
    c = certificate_cost(q, cmin)
    row.update(certifies=True,
               verified=bool(ok and abs(vlb - estar) <= max(TOL, TOL * abs(estar))),
               r1cs=c.r1cs_constraints, max_scope=c.max_scope,
               bytes=c.n_bytes, clusters=c.n_clusters)
    return row


def build_report(rows: List[dict], sizes, ibounds) -> str:
    L: List[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append("# CROWN certificate as a verification circuit\n")
    L.append(f"Generated {stamp}. Decouple find-from-prove: toulbar2 supplies the "
             f"optimum, CROWN's JGLP attempts to certify it. Cost metric "
             f"`r1cs ≈ m_Q + Σ_c 2^(scope_c)` (the SNARK/on-chain driver), after a "
             f"validity-preserving minimiser. Sizes {sizes}, i-bounds {ibounds}.\n")

    for ib in ibounds:
        L.append(f"## i-bound = {ib}\n")
        L.append("| family | n | certifies? | r1cs constraints | max cluster scope | bytes |")
        L.append("|---|---|---|---|---|---|")
        for r in [r for r in rows if r["ibound"] == ib]:
            if r["certifies"]:
                L.append(f"| {r['family']} | {r['n']} | yes | {r['r1cs']} | {r['max_scope']} | {r['bytes']} |")
            else:
                L.append(f"| {r['family']} | {r['n']} | **no** ({r.get('note','gap')}) | — | — | — |")
        L.append("")

    L.append("## Findings\n")
    for ib in ibounds:
        rs = [r for r in rows if r["ibound"] == ib]
        cert = [r for r in rs if r["certifies"]]
        if cert:
            big = max(cert, key=lambda r: r["r1cs"])
            L.append(f"- **i-bound {ib}**: certified {len(cert)}/{len(rs)}; where certified, "
                     f"r1cs {min(r['r1cs'] for r in cert)}–{max(r['r1cs'] for r in cert)} "
                     f"(largest: n={big['n']}, {big['r1cs']} constraints, scope {big['max_scope']}, "
                     f"{big['bytes']} bytes).")
        else:
            L.append(f"- **i-bound {ib}**: certified 0/{len(rs)} — no compact certificate at this i-bound.")
    L.append("")
    L.append("## Honest read\n")
    L.append("The certificate is small in **bytes** but its **verification circuit** is "
             "driven by `Σ_c 2^(scope_c)`: closing the QUBO integrality gap needs "
             "higher-order clusters, each costing `2^scope` to check, and more of them as "
             "frustration grows. A small i-bound keeps the circuit cheap but fails to "
             "certify the hard instances; a large i-bound certifies more but blows up the "
             "circuit. This is the integer/convex divide (vs. Otti's convex SNARKs) "
             "appearing directly as circuit cost.")
    return "\n".join(L)


def main(argv: List[str]) -> int:
    quick = "--quick" in argv
    sizes = [12, 18] if quick else [12, 16, 20, 24, 28]
    ibounds = [10] if quick else [5, 10]
    solvers = available()
    tb = solvers.get("toulbar2")
    if tb is None:
        print("needs pytoulbar2 (run with the solver venv)")
        return 2

    rows: List[dict] = []
    combos = [(f, n, ib) for ib in ibounds for f in FAMILIES for n in sizes]
    for k, (f, n, ib) in enumerate(combos, 1):
        print(f"\r  {k}/{len(combos)}  {f} n={n} ib={ib}        ", end="", flush=True)
        rows.append(measure(f, n, 0, ib, tb))
    print()

    bad = [r for r in rows if r.get("certifies") and not r.get("verified", True)]
    rep = build_report(rows, sizes, ibounds)
    out = os.path.join(os.path.dirname(__file__), "CIRCUIT_RESULTS.md")
    with open(out, "w") as fh:
        fh.write(rep + "\n")
    print("\n" + rep)
    if bad:
        print(f"\n⚠ {len(bad)} certificates failed independent verification")
    print(f"\nwrote {os.path.relpath(out)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
