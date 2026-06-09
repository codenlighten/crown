"""CROWN benchmark harness.

Runs CROWN across instance families and reports, per family:
  * correctness   -- CROWN's energy vs brute-force ground truth (small n);
  * certification -- fraction proven optimal, and fraction with a fully-rigorous
                     `bound-tight` certificate;
  * compression   -- fraction of variables decided before any search;
  * bound quality -- gap-to-optimum of roof duality vs full-problem JGLP;
  * baseline      -- whether a simulated-annealing run reaches CROWN's optimum;
  * self-check    -- every Proof-of-Collapse certificate is re-verified, and the
                     verifier's verdict must match the prover's claim.

No external solver is required. A plug-in seam (`EXTERNAL_SOLVERS`) lets you add
Gurobi / QPBO / dwave-neal adapters later without touching the rest.

Run:   python benchmarks/run_benchmark.py            # full
       python benchmarks/run_benchmark.py --quick    # fast smoke run
"""

from __future__ import annotations

import itertools
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crown import QUBO, build_certificate, crown_solve, verify
from crown.generators import make_field_dominated, make_random, make_shell_with_core

BRUTE_MAX = 18            # exact ground truth by enumeration up to here
TOL = 1e-6


# --------------------------------------------------------------------------- #
# Instance families
# --------------------------------------------------------------------------- #
def _shell_core(n: int, seed: int) -> QUBO:
    return make_shell_with_core(shell=max(0, n - 12), n_triangles=4, seed=seed)


FAMILIES: Dict[str, Callable[[int, int], QUBO]] = {
    "field-dominated": lambda n, s: make_field_dominated(n, seed=s),
    "shell+core": _shell_core,
    "random-sparse": lambda n, s: make_random(n, density=0.25, seed=s, scale=2.0),
    "random-dense": lambda n, s: make_random(n, density=0.6, seed=s, scale=2.0),
}


# --------------------------------------------------------------------------- #
# Baselines
# --------------------------------------------------------------------------- #
def brute_min(q: QUBO) -> float:
    best = float("inf")
    for bits in itertools.product((0, 1), repeat=q.n):
        e = q.energy(list(bits))
        if e < best:
            best = e
    return best


def sa_baseline(q: QUBO, restarts: int = 12, iters: int = 4000, seed: int = 0) -> float:
    """Fast incremental-delta simulated annealing -- a heuristic with no guarantee."""
    adj: Dict[int, List] = {i: [] for i in range(q.n)}
    for (i, j), b in q.quadratic.items():
        adj[i].append((j, b))
        adj[j].append((i, b))
    lin = q.linear
    best = float("inf")
    rng = random.Random(seed)
    for r in range(restarts):
        x = [rng.randint(0, 1) for _ in range(q.n)]
        e = q.energy(x)
        cur_best = e
        t0, t1 = 2.0, 0.01
        for t in range(iters):
            temp = t0 * (t1 / t0) ** (t / max(1, iters - 1))
            i = rng.randrange(q.n)
            v = x[i]
            delta = (1 - 2 * v) * (lin.get(i, 0.0) + sum(b * x[j] for (j, b) in adj[i]))
            if delta <= 0 or rng.random() < math.exp(-delta / temp):
                x[i] = 1 - v
                e += delta
                if e < cur_best:
                    cur_best = e
        best = min(best, cur_best)
    return best


# Adapter seam for external solvers: name -> fn(QUBO) -> energy. Empty by default.
EXTERNAL_SOLVERS: Dict[str, Callable[[QUBO], float]] = {}


# --------------------------------------------------------------------------- #
# Per-instance run
# --------------------------------------------------------------------------- #
@dataclass
class Record:
    family: str
    n: int
    seed: int
    energy: float
    kind: str
    certified: bool
    compression: float
    core_size: int
    core_width: int
    roof_lb: float
    rigorous_lb: float
    t_crown: float
    brute: Optional[float]
    crown_correct: Optional[bool]
    cert_ok: bool
    cert_consistent: bool
    sa_energy: float
    sa_matched: Optional[bool]
    t_sa: float


def run_instance(family: str, n: int, seed: int) -> Record:
    q = FAMILIES[family](n, seed)

    t0 = time.perf_counter()
    res = crown_solve(q)
    t_crown = time.perf_counter() - t0

    cert = build_certificate(q, res)
    rep = verify(q, cert)
    cert_ok = rep.ok
    cert_consistent = (rep.certified_optimal == res.certified_optimal)

    brute = brute_min(q) if q.n <= BRUTE_MAX else None
    crown_correct = None if brute is None else abs(res.energy - brute) <= max(TOL, TOL * abs(brute))

    t1 = time.perf_counter()
    sa = sa_baseline(q, seed=seed)
    t_sa = time.perf_counter() - t1
    sa_matched = None
    if res.certified_optimal:
        sa_matched = sa <= res.energy + max(TOL, TOL * abs(res.energy))

    return Record(
        family=family, n=q.n, seed=seed, energy=res.energy, kind=res.certificate_kind,
        certified=res.certified_optimal, compression=res.compression_ratio,
        core_size=res.core_size, core_width=res.core_width,
        roof_lb=res.lower_bound, rigorous_lb=res.rigorous_lower_bound, t_crown=t_crown,
        brute=brute, crown_correct=crown_correct, cert_ok=cert_ok,
        cert_consistent=cert_consistent, sa_energy=sa, sa_matched=sa_matched, t_sa=t_sa,
    )


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _pct(num: int, den: int) -> str:
    return "n/a" if den == 0 else f"{100 * num / den:.0f}%"


def build_report(records: List[Record], sizes: List[int], seeds: int) -> str:
    L: List[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append(f"# CROWN benchmark results\n")
    L.append(f"Generated {stamp} · {len(records)} instances · "
             f"families {list(FAMILIES)} · sizes {sizes} · {seeds} seeds each.\n")

    # correctness
    checked = [r for r in records if r.crown_correct is not None]
    wrong = [r for r in checked if not r.crown_correct]
    L.append("## Correctness (vs brute force)\n")
    L.append(f"- CROWN matched the brute-force optimum on **{len(checked) - len(wrong)}/"
             f"{len(checked)}** instances with n ≤ {BRUTE_MAX}.")
    if wrong:
        L.append("- ❌ MISMATCHES (must be zero):")
        for r in wrong:
            L.append(f"    - {r.family} n={r.n} seed={r.seed}: CROWN {r.energy:.6g} vs brute {r.brute:.6g}")
    L.append("")

    # certificate self-verification
    bad_ok = [r for r in records if not r.cert_ok]
    bad_cons = [r for r in records if not r.cert_consistent]
    L.append("## Certificate self-verification\n")
    L.append(f"- Re-verified **{len(records) - len(bad_ok)}/{len(records)}** Proof-of-Collapse "
             f"certificates (independent verifier accepted).")
    L.append(f"- Verifier verdict matched the prover's claim on **{len(records) - len(bad_cons)}/"
             f"{len(records)}** (no over-claims).\n")

    # per-family table
    L.append("## Per-family summary\n")
    L.append("| family | #inst | certified | rigorous `bound-tight` | mean compression | "
             "SA reached optimum | median t (CROWN) | median t (SA) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for fam in FAMILIES:
        rs = [r for r in records if r.family == fam]
        if not rs:
            continue
        cert = sum(r.certified for r in rs)
        bt = sum(r.kind == "bound-tight" for r in rs)
        comp = statistics.mean(r.compression for r in rs)
        sa_ev = [r for r in rs if r.sa_matched is not None]
        sa_hit = sum(r.sa_matched for r in sa_ev)
        tc = statistics.median(r.t_crown for r in rs)
        ts = statistics.median(r.t_sa for r in rs)
        L.append(f"| {fam} | {len(rs)} | {_pct(cert, len(rs))} | {_pct(bt, len(rs))} | "
                 f"{comp:.0%} | {_pct(sa_hit, len(sa_ev))} | {tc * 1e3:.0f} ms | {ts * 1e3:.0f} ms |")
    L.append("")

    # bound tightness (on certified instances, where the optimum is known)
    cert_recs = [r for r in records if r.certified]
    if cert_recs:
        groof = statistics.mean(r.energy - r.roof_lb for r in cert_recs)
        grig = statistics.mean(r.energy - r.rigorous_lb for r in cert_recs)
        closed = sum(abs(r.energy - r.rigorous_lb) <= max(TOL, TOL * abs(r.energy)) for r in cert_recs)
        L.append("## Rigorous bound quality (certified instances, optimum known)\n")
        L.append(f"- Mean gap-to-optimum: **roof duality {groof:.3f}** → "
                 f"**full-problem JGLP {grig:.3f}** (lower is tighter).")
        L.append(f"- JGLP closed the gap to a fully-rigorous `bound-tight` proof on "
                 f"**{closed}/{len(cert_recs)}** certified instances.\n")

    # scale (instances beyond brute force) -- certified without ground-truth enumeration
    scale = [r for r in records if r.brute is None]
    if scale:
        sc_cert = sum(r.certified for r in scale)
        big = max(r.n for r in scale)
        L.append("## Scale (beyond brute force)\n")
        L.append(f"- On the **{len(scale)}** instances with n > {BRUTE_MAX} (up to n={big}, "
                 f"2^{big} configurations), CROWN returned a **certified optimum** on "
                 f"**{_pct(sc_cert, len(scale))}** — proofs, not just heuristic guesses.\n")

    return "\n".join(L)


def main(argv: List[str]) -> int:
    quick = "--quick" in argv
    sizes = [12, 24] if quick else [12, 16, 28, 44]
    seeds = 3 if quick else 5

    combos = [(f, n, s) for f in FAMILIES for n in sizes for s in range(seeds)]
    records: List[Record] = []
    print(f"running {len(combos)} instances ({'quick' if quick else 'full'})...")
    for k, (f, n, s) in enumerate(combos, 1):
        records.append(run_instance(f, n, s))
        print(f"\r  {k}/{len(combos)}  {f} n={n} seed={s}        ", end="", flush=True)
    print()

    report = build_report(records, sizes, seeds)
    out = os.path.join(os.path.dirname(__file__), "RESULTS.md")
    with open(out, "w") as fh:
        fh.write(report + "\n")
    print("\n" + report)
    print(f"\nwrote {os.path.relpath(out)}")

    wrong = [r for r in records if r.crown_correct is False]
    bad = [r for r in records if not r.cert_ok or not r.cert_consistent]
    return 1 if (wrong or bad) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
