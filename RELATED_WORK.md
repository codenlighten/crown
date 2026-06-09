# Related work — where CROWN actually sits

This document positions CROWN honestly against the literature, so no reader is
misled about what is established and what (if anything) is new. Short version:
**every algorithm in CROWN is established prior art, and certified optimization is
an active research field.** CROWN's contribution is a clean, end-to-end,
*verifiable* reference implementation with a compact arithmetic-checkable bound
certificate for QUBO — an engineering/packaging contribution, not a new theorem.

## The algorithms are not ours

| CROWN component | Origin |
|---|---|
| Roof duality, persistency, QPBO | Hammer–Hansen–Simeone (1984); Boros–Hammer; Kolmogorov–Rother |
| Bucket / mini-bucket elimination | Dechter (1996, 1999) |
| Weighted mini-bucket, cost-shifting / JGLP / GDD | Liu–Ihler; Ihler–Flerova–Dechter; Marinescu–Dechter |
| AND/OR search, context caching, static MB heuristic | Dechter–Mateescu; Marinescu–Dechter; Kask–Dechter |

CROWN implements these from scratch and validates them against brute force. That
is a faithful re-implementation of the graphical-models / pseudo-Boolean toolkit,
not a new method. **toulbar2** (Cost Function Network solver, INRA/Toulouse) is the
mature C++ embodiment of the *same* AND/OR-branch-and-bound + mini-bucket family;
`benchmarks/compare.py` measures CROWN against it directly.

## Certified optimization already exists — and is active

The idea that an optimizer should emit a checkable proof of optimality is **not
new**, and QUBO is just unconstrained pseudo-Boolean optimization, squarely inside
this field:

- **VeriPB / pseudo-Boolean proof logging** (Gocht, Nordström, et al.) — a
  machine-verifiable proof format based on the *cutting-planes* proof system
  (linear combination, division, saturation) plus reverse unit propagation. It
  certifies the *reasoning steps* a solver takes.
- **The Pseudo-Boolean Competition** (PB25, PB26) runs an explicit
  *certificate-of-optimality* track; proof-logging branch-and-bound PBO/MaxSAT
  solvers emit VeriPB proofs.
- **Proof systems for integer programming** (certifying symmetry and optimality
  reasoning) and **certified MIP presolve** extend the same idea to 0–1 ILP.
- In **MAP-MRF / graphical models**, dual decomposition / TRW / SOS bounds *are*
  optimality certificates (a dual-feasible reparameterization lower-bounds the
  optimum); when the bound meets a primal assignment, optimality is certified.
  This is exactly the mechanism CROWN uses.

## What CROWN's certificate is, precisely

CROWN's "Proof-of-Collapse" lower-bound certificate is **classical LP/Lagrangian
duality plus an energy reparameterization**:

- the roof-dual **dual vector** is a Farkas-style LP-duality certificate;
- the **JGLP pairwise-cluster** certificate is a reparameterization with
  `const + Σ_c cluster_c(x) ≡ E(x)`, so `Σ_c min cluster_c` is a valid lower
  bound — the standard dual-decomposition bound, shipped as the clusters
  themselves and checkable by summing them back to the problem.

This differs from VeriPB in *mechanism and trade-offs*, not in ambition:

| | CROWN Proof-of-Collapse | VeriPB |
|---|---|---|
| What it proves | a **static bound** (dual + reparameterization) meeting a primal | a **deductive proof log** of the solver's reasoning |
| Proof system | LP/Lagrangian duality + reparameterization | cutting planes + RUP |
| Size | compact (a dual vector + pairwise clusters) | grows with the search/derivation |
| Generality | QUBO bound certificates | general PBO/0–1 ILP, constraints, symmetry |
| Maturity | research-quality, one tool | competition-grade, multiple solvers, formats |

## So what, if anything, is new?

Honestly: **little is novel theoretically.** The most one can claim is *packaging*:
a compact, hash-anchorable, pure-arithmetic bound certificate for QUBO with an
end-to-end "shell-collapse → core → certificate" pipeline, aimed at on-chain /
SmartLedger anchoring. Whether even that packaging is worth a citation would
require (a) comparing certificate size and verification cost against emitting a
VeriPB proof from a QUBO solver, and (b) a use case where a *self-contained
arithmetic* certificate beats a VeriPB proof + the VeriPB checker. That comparison
has **not** been done and should gate any novelty claim.

## Honest bottom line

CROWN is a correct, well-tested, verifiable **reference implementation** of the
certified-optimization stack for QUBO. It is valuable as a teaching/clean-room
artifact and as a substrate for the on-chain-verification idea. It is **not** a new
algorithm, **not** performance-competitive with toulbar2/Gurobi, and its
certificate sits inside an existing, active research area. Claims in this repo are
scoped to match that.
