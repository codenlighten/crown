# CROWN — Certified QUBO/Ising Optimization with Proof-of-Collapse

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
pip install -r requirements.txt
python -m examples.demo          # six worked regimes, each solved + verified
python tests/test_crown.py       # 36 soundness/correctness tests
python -m crown.verify examples/C_wide_thin_core.problem.json \
                        examples/C_wide_thin_core.cert.json   # trustless verifier
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
  solve.py        the distill -> reduce -> solve -> certify pipeline
  certificate.py  Proof-of-Collapse certificate construction
  verify.py       trustless verifier (CLI: python -m crown.verify ...)
  generators.py   structured test/demo instances
examples/demo.py  six end-to-end regimes
tests/            36 soundness + correctness tests (validated vs brute force)
```

## Status

Research-quality, fully tested (36/36). Not yet benchmarked against
state-of-the-art exact solvers (Gurobi, QPBO, toulbar2) — that comparison, plus a
write-up, is the natural next step toward making this useful to others.

## License

Apache-2.0. Copyright 2026 the CROWN contributors.

🤖 Built with [Claude Code](https://claude.com/claude-code).
