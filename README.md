# CROWN — Certified QUBO/Ising Optimization with Proof-of-Collapse

[![CI](https://github.com/codenlighten/crown/actions/workflows/ci.yml/badge.svg)](https://github.com/codenlighten/crown/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

CROWN is a classical optimizer for **QUBO / Ising** problems that returns not
just a solution but a **machine-checkable proof of optimality** — one a third
party (or a smart contract) can verify by *pure bounded arithmetic*, without
rerunning the solver and, for many frustrated instances, without trusting any
heuristic.

> **Thesis.** We don't claim NP-hard problems are easy. We claim many real
> instances are a large *reducible shell* wrapping a small *irreducible core*,
> that the shell collapses with a **certified lower bound**, and that the whole
> result is independently verifiable — *Proof-of-Collapse*.

```bash
pip install -e .          # or: pip install git+https://github.com/codenlighten/crown

crown solve  problem.qubo --cert c.json --problem p.json   # solve + emit certificate
crown verify p.json c.json                                 # trustless verification
crown demo                                                 # six worked regimes
crown bench --quick                                        # benchmark smoke run
python tests/test_crown.py                                 # 36 tests
```

A problem file is either **canonical JSON** (`.json`) or **sparse triplets**
(`.txt`/`.qubo`, one `i j value` term per line — `i==j` is linear). Or use the
library directly:

```python
from crown import QUBO, crown_solve, build_certificate, verify
res  = crown_solve(QUBO.from_matrix(my_matrix))
cert = build_certificate(qubo, res)        # a Proof-of-Collapse certificate
assert verify(qubo, cert).certified_optimal
```

## What it does

```
QUBO ──roof_dual──▶ certified global bound + persistencies (the shell)
     ──reduce────▶ fixed shell + irreducible core + lift map
     ──solve_core▶ bucket elimination (thin) · AOBB / AND-decomposition (wide)
     ──lift──────▶ full assignment, exact energy on the ORIGINAL problem
     ──certify───▶ a Proof-of-Collapse certificate (see below)
```

Every run emits a certificate carrying the problem/core hashes, the assignment,
two **trustless rigorous lower-bound certificates** (a roof-dual dual vector and
a full-problem **JGLP pairwise-cluster** decomposition), and the claimed kind.
`crown/verify.py` re-checks all of it independently:

| certificate kind | meaning | rigour |
|---|---|---|
| `bound-tight` | energy == best rigorous bound (roof-dual **or** full-problem JGLP) | fully rigorous, persistency-independent, **trustless arithmetic** |
| `exact-core` | the core was solved exactly (elimination / AOBB) | optimal given roof-dual strong persistency (a theorem) |
| `bound-tight-core` | energy == tightened core bound | optimal given persistency |
| `bracket` | no bound met the energy | not certified — reports `[lower bound, energy]` + gap |

The verifier **rejects** a tampered solution, a swapped problem, a fabricated
bound, or an optimality *over*-claim it cannot independently confirm.

## What's established vs. what's new

The individual algorithms are well-established and were implemented from scratch
and validated against brute force: **roof duality** (Hammer–Hansen–Simeone,
Boros–Hammer), **bucket / mini-bucket elimination** (Dechter), **weighted
mini-bucket / JGLP cost-shifting** (Ihler, Marinescu–Dechter), **AND/OR
branch-and-bound**.

The novel synthesis is the **trustless optimization certificate** —
*Proof-of-Collapse*: a hash-chained, arithmetic-checkable proof of a claimed
optimum (or an honest bracket), suitable for on-chain anchoring. The key
identity is that JGLP reparameterizes the energy into pairwise clusters with
`const + Σ_c table_c(x) ≡ E(x)`, so shipping the clusters lets anyone verify the
lower bound `const + Σ_c min table_c` by summing the clusters back to the problem
and recomputing per-cluster minima — sound regardless of how they were produced.

See **[DESIGN.md](DESIGN.md)** for the grounded technical spec (including the
honest findings: why gauge can't concentrate frustration, why single-variable
cost-shifting equals roof duality, the decomposability↔JGLP-strength tension),
and **[VISION.md](VISION.md)** for the original north-star vision.

## Layout

```
crown/
  ising.py        QUBO model, exact energy, Ising view, canonical hashing
  roofdual.py     roof-dual LP: certified bound + dual certificate + persistency
  reduce.py       shell substitution + lift map
  elimination.py  bucket elimination + (weighted) mini-bucket + JGLP
  search.py       JGLP-guided AOBB, AND/OR-with-caching, component decomposition
  andor.py        static mini-bucket heuristic + bucket-tree cost-shifting
  rigorous.py     full-problem JGLP -> trustless pairwise-cluster bound certificate
  circuit.py      certificate-as-arithmetic-circuit cost + validity-preserving minimiser
  solve.py        the distill -> reduce -> solve -> certify pipeline
  certificate.py  Proof-of-Collapse certificate construction
  verify.py       trustless verifier
  qubo_io.py      load/save QUBOs (canonical JSON + sparse triplets)
  cli.py          the `crown` command-line interface
  generators.py   structured test/demo instances
examples/demo.py  six end-to-end regimes
benchmarks/       self-benchmark (RESULTS.md) + SOTA comparison (compare.py,
                  external_solvers.py, instances.py, EXTERNAL_RESULTS.md)
tests/            36 soundness + correctness tests (validated vs brute force)
```

## Benchmarks

`python benchmarks/run_benchmark.py` runs CROWN across four instance families and
validates it end-to-end. From the latest full run (80 instances, n up to 44 —
full table in **[benchmarks/RESULTS.md](benchmarks/RESULTS.md)**):

- **Correctness:** **40/40** — CROWN's energy matched brute force on every
  instance small enough to enumerate. It never returned a wrong optimum.
- **Trustless verification:** **80/80** certificates independently re-verified,
  with **0** optimality over-claims.
- **Certified optimality:** 100% on the structured families; **90%** on
  dense-random (n ≤ 44), of which **70%** carry the strongest fully-rigorous
  `bound-tight` proof.
- **Rigorous bound tightening:** full-problem JGLP cut the mean gap-to-optimum
  from **6.04** (roof duality) to **0.25**.
- **Scale:** on 40 instances beyond brute-force reach (up to 2⁴⁴), CROWN
  returned a **certified** optimum **95%** of the time — proofs, not guesses.

### Validated against state-of-the-art

`python benchmarks/compare.py` runs CROWN head-to-head against **toulbar2** (the
*same* AND/OR-branch-and-bound + mini-bucket algorithm family, in tuned C++) and
**SCIP**, on standard Sherrington–Kirkpatrick spin-glass and max-cut instances —
see **[benchmarks/EXTERNAL_RESULTS.md](benchmarks/EXTERNAL_RESULTS.md)**. Two
honest findings:

- **Correctness is corroborated by an independent SOTA solver.** CROWN's optima
  matched toulbar2 on **20/20** instances and brute force on **8/8**; on the
  **19** it reported as *certified* it matched toulbar2's proven optimum every
  time; it never undercut a proven optimum and never certified a wrong one.
- **CROWN is *not* performance-competitive.** toulbar2 was **~110× faster**
  (median) — it proves in well under a second the spin-glasses that take CROWN
  tens of seconds, and certifies n=28 instances that CROWN's pure-Python search
  cannot certify at all. CROWN's value is the *verifiable certificate* and the
  clean reference implementation — not raw solve speed.

## Status & honest scope

Research-quality, fully tested (36/36), benchmarked, and cross-validated against
toulbar2/SCIP. To be clear about what CROWN is and isn't (see
**[RELATED_WORK.md](RELATED_WORK.md)**):

- The algorithms (roof duality, bucket/mini-bucket elimination, JGLP, AND/OR
  search) are **established prior art**, implemented from scratch and validated.
- Certified optimization is an **active field** (VeriPB / pseudo-Boolean proof
  logging, MAP-MRF dual certificates); CROWN's certificate is classical LP/
  Lagrangian duality + reparameterization. The most CROWN claims is a *compact,
  arithmetic-checkable, hash-anchorable bound certificate for QUBO* — an
  engineering/packaging contribution, not a new theorem.
- It is **not** competitive with toulbar2/Gurobi on speed or scale.

We probed the one possibly-open niche — a compact, transparent, on-chain
optimality certificate for QUBO — and **closed it with evidence**
(`benchmarks/CIRCUIT_RESULTS.md`): for hard frustrated instances the compact
certificate usually doesn't exist (the integrality gap), and where it does the
verification circuit grows exponentially with cluster scope. The honest verdict
and landscape are in **[RELATED_WORK.md](RELATED_WORK.md)**.

## License

Apache-2.0. Copyright 2026 the CROWN contributors.

🤖 Built with [Claude Code](https://claude.com/claude-code).
