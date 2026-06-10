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

## Verifiable-computation landscape, and a circuit-cost determination

We checked the one sliver that seemed possibly-open — *arithmetizing an
integer-optimization optimality certificate for transparent on-chain / SNARK
verification* — both in the literature and with a measurement (`benchmarks/
circuit_size.py` → `CIRCUIT_RESULTS.md`).

**Literature.** The space is occupied:
- **Otti** (USENIX Sec '22, [eprint 2021/1436](https://eprint.iacr.org/2021/1436.pdf))
  compiles optimization problems to R1CS and gives zk-SNARK proofs of optimality
  with on-chain commitments — but for **convex** problems (LP/SDP/SGD), where the
  dual certificate is *tight*.
- **OSAC / VAC** ([Cooper et al.](https://www.irit.fr/publis/ADRIA/OSAC.pdf)) and
  **Super-Reparametrizations of WCSPs** ([arXiv 2201.02018](https://arxiv.org/pdf/2201.02018))
  are the reparameterization optimality certificate for *integer* cost-function
  networks — exactly CROWN's certificate, already studied as an optimization
  problem.
- **VeriPB** provides machine-checkable proofs for pseudo-Boolean optimization
  (which includes QUBO).

**Measurement (the integer/convex divide as circuit cost).** QUBO is integer, so
the convex dual has an **integrality gap**; CROWN needs higher-order JGLP clusters
to close it, and each cluster of scope `s` costs `2^s` to verify. On standard
Sherrington–Kirkpatrick and max-cut instances (toulbar2 supplying the optimum):

- the compact certificate **certified only 1–2 of 10 instances** (0/10 spin
  glasses) at i-bound ≤ 10 — for genuinely frustrated QUBO the relaxation has a gap
  the certificate cannot close at any tractable cluster size;
- where it *did* certify, the circuit grew steeply (170 → 2120 R1CS constraints
  from n=12 → n=20), driven by `Σ_c 2^{scope_c}`.

So the integer case has no free lunch: a small i-bound is cheap but rarely
certifies; a large one certifies more but the circuit blows up exponentially. This
is precisely why Otti's convex approach works and the integer analogue does not.

## Honest bottom line — go/no-go: **no-go on the niche**

CROWN is a correct, well-tested, verifiable **reference implementation** of the
certified-optimization stack for QUBO — valuable as a clean-room/teaching artifact.
It is **not** a new algorithm, **not** performance-competitive with toulbar2/Gurobi,
and its certificate sits inside an active research area (Otti / OSAC / VeriPB). The
one possibly-open niche — a compact, transparent, on-chain optimality certificate
for QUBO — **does not survive measurement**: for the hard frustrated instances that
would matter, the compact certificate usually does not exist (integrality gap), and
where it does the verification circuit grows exponentially with the gap-closing
cluster scope. We are ending the novelty chase here, with evidence, rather than
building on a guess. Claims in this repo are scoped to match all of the above.
