# CROWN — Design (grounded)

This document reconciles the CROWN vision (`README.md`) with what is
mathematically sound and buildable today. It is the spec the v0 code in
`crown/` actually implements. Where the vision and the math disagree, the math
wins and the disagreement is documented here so the two stay honest.

> Thesis (defensible form): *We do not claim NP-hard problems become easy. We
> claim many real instances are a large **reducible shell** wrapping a small
> **irreducible core**, and that the shell can be collapsed with a **certified
> lower bound** so the result is independently verifiable — Proof-of-Collapse.*

---

## 1. The vision's five layers, mapped to reality

| CROWN layer (README) | Established name | In v0? | Notes |
|---|---|---|---|
| 1. Energy Grammar | Roof duality / persistency; motif/pattern DBs | partial | Persistency is the rigorous subset; motif mining is future work (§5). |
| 2. Gauge Rewriting | Gauge transforms / Harary balance | **dropped** | See §2 — gauge **cannot** reduce frustration. Kept only as a balance/triviality detector for future use. |
| 3. Frustration Compression | (delivered by persistency + kernelization) | yes | The shell/core split *is* frustration compression, but the mechanism is roof duality, not gauge. |
| 4. Tensor Collapse w/ bounds | Bucket elimination, (weighted) mini-bucket bounds | **yes** | `crown/elimination.py`: exact bucket elimination (cost 2^treewidth, not 2^n) + weighted-mini-bucket lower bounds via cost-shifting. This is the scale path and it closes/​shrinks gaps roof duality can't (§3a). |
| 5. Irreducible Core Extraction | **QPBO / roof duality + kernelization** | yes | The headline layer already has 30+ years of theory. This is what v0 is built around. |

The single most important correction: **layer 5 is the foundation, not the
finale.** QPBO/roof duality already returns a provably optimal partial labeling;
the unlabeled set *is* the irreducible core. v0 implements exactly this.

---

## 2. Why gauge rewriting cannot "concentrate frustration" (the one broken claim)

The README proposes using gauge transforms (flip spin `i`, flip the sign of
every coupling on `i`) to herd frustration into a small region. This is
impossible, and it's worth stating precisely so we don't build it:

- **Frustration is gauge-invariant.** The frustration of a loop is the product
  of the signs of the couplings around it (the plaquette / Wilson-loop product).
  A gauge flip at node `i` flips the sign of an *even* number of a loop's edges
  (0 if the loop misses `i`, 2 if it passes through), so every loop product is
  unchanged. Frustration is a conserved quantity under exactly the operation
  proposed to move it.
- **What gauge can do:** *detect balance* (Harary). If a signed instance has
  zero frustrated loops, gauge maps it to a purely ferromagnetic problem,
  solvable in P by min-cut. So gauge is a **triviality detector**, not a
  frustration concentrator. v0 gets this property for free: a balanced instance
  is fully decided by roof duality and comes back CERTIFIED OPTIMAL.

Net: fold layers 2–3 into layer 5. No capability is lost.

---

## 3. What v0 actually does (the sound subset)

Pipeline (`crown/solve.py`):

```
QUBO ──roof_dual──▶ (certified GLOBAL lower bound, persistencies)
     ──reduce────▶ fixed shell + irreducible core + lift map
     ──solve_core▶ EXACT bucket elimination if core treewidth ≤ 20,
                   else mini-bucket LOWER BOUND + simulated annealing
     ──lift──────▶ full assignment, exact energy on the ORIGINAL problem
     ──certify───▶ certificate_kind ∈ {bound-tight, exact-core, bracket}
```

**Roof duality = the standard linearization LP** (`crown/roofdual.py`). It is
equivalent to QPBO and yields two things from one solve:

1. a **valid lower bound** with a **dual-feasible certificate**. By weak LP
   duality any dual-feasible point lower-bounds the optimum, so the certificate
   is checkable by pure arithmetic — no solver trust required;
2. **persistencies**: integral LP coordinates are fixable variables (the shell).

`reduce.py` substitutes the shell out; what survives is the core. `lift` puts the
shell back. Everything is exact float/integer arithmetic except the core
heuristic for large cores (clearly labeled `simulated-annealing (heuristic)`).

### 3a. Bound-carrying variable elimination (the scale path)

`crown/elimination.py` is "tensor collapse as a proof engine" made concrete.
Each local energy term is a small tensor (factor); we eliminate variables one at
a time, and every elimination message carries a min-marginal:

- **Exact bucket elimination** — runs in O(2^(w+1)) where `w` is the induced
  width of the elimination order (min-fill heuristic), *not* 2^n. A 150-variable
  core with treewidth 2 is solved exactly in milliseconds (demo C) where brute
  force would need 2^150. Returns the exact minimum and an optimal assignment.
- **Mini-bucket elimination** — when `w` is too large, partition each bucket into
  mini-buckets of bounded scope and minimise each independently. Letting the
  eliminated variable differ across mini-buckets is a relaxation, hence a sound
  **lower bound** (Dechter–Rish). With i-bound ≥ w it reduces to exact.
- **Weighted mini-bucket (cost-shifting / moment matching)** — tightens the
  mini-bucket bound. For *minimisation* the looseness is entirely that the
  duplicated variable may disagree across mini-buckets; we reparameterise with a
  zero-sum cost shift that matches the variable's min-marginals across them. Any
  zero-sum shift stays a valid lower bound (`Σ_k min φ'_k ≤ min Σ_k φ'_k`), and
  matching usually tightens it. A single pass is *not* provably monotone over a
  sequential schedule, so `mini_bucket_bound` returns `max(plain, matched)` —
  provably ≥ plain and still sound. In practice this roughly halves the
  gap-to-optimum (demo D: roof-dual bound −86.3 → weighted-MB −66.5, a 61%
  smaller bracket on a width-26 core that exact elimination can't touch).
  (Hölder *weights* tighten the sum/partition-function bound; for MAP/min the
  win comes from cost-shifting, which is what this implements.)
- **Join-graph cost-shifting / JGLP (`join_graph_bound`)** — the *iterated*,
  provably **monotone** version. Single-pass weighted-MB isn't monotone because
  the elimination schedule keeps changing the clusters; JGLP fixes a static
  cluster cover and repeatedly matches min-marginals as block coordinate ascent
  on the dual (each block update is the exact maximiser → never decreases the
  bound). Crucially it matches over **pair separators** (shared variable pairs),
  not just single variables: single-variable matching alone converges to the
  pairwise LP, which *equals* roof duality and adds nothing; **pair-separator
  matching enforces joint two-variable consistency and captures frustrated
  cycles**, pushing the bound strictly past roof duality. On a frustrated
  triangle roof duality gives −3 (true min −1); JGLP reaches −1 exactly. On a
  batch of random cores it cut the average gap-to-optimum from 0.37 to 0.005.
  `wide_core_bound` = max(weighted-MB, JGLP) is the bound CROWN reports for wide
  cores; it upgraded demo D (a width-26 dense core) from `bracket` to
  **`bound-tight-core` / CERTIFIED OPTIMAL** by closing a gap of 12.7 to zero.

### 3b. Bound-guided branch-and-bound (AOBB) — turning bounds into exact proofs

When a core is too wide for exact elimination *and* JGLP doesn't fully close the
gap, `crown/search.py` runs a depth-first branch-and-bound whose node lower bound
is read straight off the JGLP-reparameterised clusters. Because that
reparameterisation preserves the total energy, the conditioned cluster sum

    f(partial) = const + Σ_c min_{free vars} table_c(partial)

never overestimates the best reachable completion (sum of mins ≤ min of sum), so
pruning on `f ≥ incumbent` is **sound** and at a leaf `f` is the exact energy. If
the search completes within the node budget, the optimum is **proven by
exhaustion** — certifiable even though no cheap bound certificate exists.
Conditioning is incremental (only clusters touching the assigned variable are
re-sliced) and the root bound is exactly JGLP, so a near-tight bound means very
few nodes (demo D: JGLP already tight → 1 node; demo E: width-21 core, ~1.5k
nodes; a 60-var frustrated core: 61 nodes). When the budget is hit, `complete` is
false and the result is only an upper bound — never claimed optimal. This
replaces annealing's uncertified guess with a proof wherever the search finishes.

### 3c. AND decomposition (independent components)

Before searching a wide core, `solve_core_exact` splits it into **connected
components** (`crown/search.py`). Independent components are the top-level AND
decomposition: their optima are solved separately and summed, so one wide
component never forces search on the thin ones. Each component takes the best
exact method — bucket elimination if its width is small, else AOBB. Demo F (a
59-variable core that is two independent frustrated blocks, width 21) is solved
`decompose+AOBB+BE`: one block by bucket elimination, the other by AOBB, then
certified — instead of searching the joint 59-variable space. The verifier
re-decomposes identically.

A full **recursive** AND/OR solver with context caching is also implemented and
validated (`aobb_andor_solve`, `build_pseudo_tree`): a pseudo-tree of the
interaction graph makes child subtrees conditionally independent, and subtree
optima are cached by context. It comes in two heuristic strengths:

- **per-factor** (cheap, decomposable) — the default for `aobb_andor_solve`;
- **static mini-bucket + bucket-tree cost-shifting** (`aobb_andor_mb_solve`,
  `crown/andor.py`) — the *unification* of the strong heuristic with the
  recursive decomposition. The global JGLP bound does **not** decompose per
  subtree (cost-shifting moves cost across subtree boundaries), so we use the
  static mini-bucket heuristic (Kask–Dechter): eliminate along the pseudo-tree
  order and, for a subtree's cost-to-go, sum the mini-bucket messages that cross
  out of it. Each message is a min-relaxation, so the sum is a sound per-subtree
  lower bound (validated: 0 violations over 10k context checks, tight at large
  i-bound). **Bucket-tree cost-shifting** then tightens it: within each bucket,
  equalise the eliminated variable's min-marginal across its mini-buckets
  (moment matching). The shift is a zero-sum function of that one variable and
  every mini-bucket here is anchored at the *same* pseudo-tree node, so it
  removes the mini-bucket splitting slack **without crossing a subtree boundary**
  — decomposition is preserved. It makes the heuristic ~45% tighter
  (gap-to-truth 2728→1488 over all contexts) and cut demo E's AND/OR search from
  ~114k to ~19k nodes — *faster in wall-clock than flat JGLP-AOBB* there
  (0.29s vs 0.87s).

  **The tension (a fundamental finding):** going further — matching *pair*
  separators to capture frustrated cycles, which is exactly what lets JGLP beat
  roof duality — would move cost between buckets in *different* subtrees and
  break the per-subtree decomposition (and soundness; verified). So
  within-bucket moment matching is the **strongest cost-shifting compatible with
  AND/OR decomposition**. It makes recursive AND/OR competitive with, and on
  decomposable/dense-connected cores faster than, flat JGLP-AOBB — but flat
  JGLP can still win where its boundary-crossing pair-matching makes the bound
  exactly tight (demo D: 35 nodes vs AND/OR's ~170k). Decomposability and full
  JGLP-strength cost-shifting are genuinely in tension.

Honest benchmarking outcome (this is the load-bearing finding):

| core | flat JGLP-AOBB | AND/OR per-factor | AND/OR + static-MB | AND/OR + MB + cost-shift |
|---|---|---|---|---|
| demo E (dense, w21) | 1.5k / 0.9s | 441k / 12s | 114k / 1.7s | **19k / 0.29s** |
| demo D (JGLP-tight) | 35 / 1.1s | — | — | ~170k / 2.7s |
| chain of frustrated blobs | ~50 / 0.1s | ~600 / 0.01s | ~600 / 0.01s | ~600 / 0.01s |

Bucket-tree cost-shifting made AND/OR competitive with — and on demo E faster
than — flat JGLP-AOBB. But **flat JGLP-AOBB stays the more robust pipeline
choice**: where its pair-separator cost-shifting makes the bound exactly tight
(demo D) it finishes in a handful of nodes, and the AND/OR heuristic cannot match
that without the boundary-crossing matching that would break decomposition. The
recursive solvers are kept as validated, exported tools; the default wide-core
path remains component decomposition + JGLP-guided AOBB.

(A subtle correctness bug surfaced and was fixed here: the AND/OR assignment
extraction used to re-solve pruned subtrees, which could hit the node budget and
mislabel `complete`. Extraction now reads the optimal value-choice recorded
during search — pure lookups, so `complete` reflects only the main search's
exhaustiveness. Tested under budget pressure.)

Why this matters for certification: roof duality gives a *global* lower bound but
it is loose on frustration (demo B gap 8, demo C gap 100). Exact elimination on
the (thin) core, or AOBB on a wide one (per component), computes the true core
optimum, **closing those gaps**. The certificate kinds:

| kind | when | rigour |
|---|---|---|
| `bound-tight` | energy == best rigorous global bound (roof-dual **or full-problem JGLP**) | fully rigorous, persistency-independent, trustless arithmetic. JGLP-on-the-unreduced-problem reaches this on frustrated cores where roof duality is loose (demos B/C/D upgraded from `exact-core`) |
| `exact-core` | core solved exactly — bucket elimination (thin) or AOBB exhaustive search (wide) | optimal **given roof-dual strong persistency** (a theorem; empirically validated by `test_pipeline_solution_is_global_optimum_on_small_instances`) |
| `bound-tight-core` | energy == wide-core bound (max of weighted-MB and JGLP) | optimal given persistency; the tightened bound met the achieved energy on a core too wide to eliminate exactly |
| `bracket` | no bound meets the energy | not certified; report best lower bound (max of roof-dual and weighted-MB), energy, and gap |

### Honesty rules baked into the code
- **`certified_optimal` is true only when found energy == certified lower bound.**
  On frustrated cores the bound is loose, so we report a *bracket*
  `[lower_bound, energy]` and a `gap`, never a false optimality stamp. (Demo B:
  gap = 8 = 2 × four frustrated triangles — the exact frustration the bound
  cannot see.)
- Persistency fixing in v0 reads one LP vertex (roof-dual persistency). It is
  used to *shrink* search; correctness of the final optimality claim never
  depends on it, because that claim is gated on `energy == bound`, both of which
  the verifier re-derives independently.

---

## 4. Proof-of-Collapse — the genuinely novel layer

This is the part with no real prior art in the QUBO solver world and the part
worth the brand. A certificate (`crown/certificate.py`) carries:

- `problem_hash` — sha256 of the canonical original QUBO
- `core_hash` — sha256 of the canonical irreducible core
- `assignment`, `energy`, `lower_bound`, `rigorous_lower_bound`, `gap`
- `dual` — the roof-dual certificate vector `(p, q, r, s)`
- `jglp` — the full-problem JGLP pairwise clusters (a tighter rigorous bound cert)
- `certificate_hash` — sha256 over all of the above

The verifier (`crown/verify.py`, also `python -m crown.verify problem.json
cert.json`) **never calls the solver**. Two tiers:

*Trustless (pure arithmetic):*
1. recomputes `problem_hash` (rejects a swapped problem),
2. re-evaluates the assignment's energy directly (rejects a tampered solution),
3. re-checks the **roof-dual dual** inequalities by arithmetic to recover a lower
   bound, AND re-checks the **JGLP cluster certificate** — that the pairwise
   clusters sum back to the QUBO (the reparameterisation identity) and that each
   cluster's minimum, recomputed by a bounded enumeration, sums to the claimed
   bound. Both are rigorous and persistency-independent; the JGLP one is usually
   far tighter on frustrated structure (demo C: roof dual −354 vs JGLP −254 =
   optimum). Sound for *any* clusters that sum to E — the verifier never trusts
   that JGLP produced them.
4. confirms `max(bound) ≤ energy`, and stamps `bound-tight` optimal iff equal.

*Recompute tier (for `exact-core` / `bound-tight-core`):*
5. reconstructs the core from the problem + the fixed shell, confirms `core_hash`,
   and re-derives optimality with its **own** computation:
   - thin core → exact bucket elimination;
   - wide core, bound already tight → recompute `wide_core_bound` (weighted-MB / JGLP);
   - wide core, bound loose but optimality *claimed* → **re-decompose into
     components and re-solve** each (`solve_core_exact`) seeded with the achieved
     energy, confirming no completion beats it (same deterministic budget — if
     the prover finished, so does the verifier).

   This is sound regardless of how the prover obtained its result; the only
   residual assumption is the roof-dual strong-persistency theorem. Tampering any
   core bit fails this check (tested).

Two more rules keep it honest: this optimality check is **not required for
ACCEPT** (an honest `bracket` certificate fails it and is still accepted), and a
separate **claim-consistency** check *rejects* any certificate that claims
optimality the verifier cannot independently confirm — the prover cannot
overclaim.

Tests in `tests/test_crown.py` confirm it rejects each tampering mode. This maps
cleanly onto an on-chain / SmartLedger verifier: anchor `certificate_hash`, and
anyone can replay steps 1–4 to confirm a claimed optimum was produced from a
specific problem — without re-running the optimizer.

The SAT/ILP analogues are DRAT proofs and Farkas certificates. **Neither exists
as a packaged artifact for QUBO.** That gap is the opportunity.

---

## 5. Roadmap (vision items, in defensible order)

1. **Bound-carrying tensor/bucket contraction + search + decomposition**
   (vision layer 4) — ✅ **done** (`crown/elimination.py`, `crown/search.py`):
   exact bucket elimination, mini-bucket / weighted mini-bucket / **JGLP**
   bounds, **bound-guided AOBB** that proves optima by exhaustion on wide cores,
   and **AND decomposition** into independent components (`solve_core_exact`,
   demo F) plus validated recursive **AND/OR-with-caching** solvers — both
   per-factor (`aobb_andor_solve`) and **static-mini-bucket-guided**
   (`aobb_andor_mb_solve`, the heuristic↔decomposition unification). Benchmarking
   showed flat JGLP-AOBB remains the most robust pipeline solver (§3c).
   **Bucket-tree cost-shifting** (within-bucket moment matching) has now lifted
   the AND/OR heuristic substantially (demo E: 114k→19k nodes, faster than flat
   JGLP) — and established that it is the *strongest cost-shifting compatible
   with decomposition*, since pair-separator matching would break it. Next:
   **cluster pursuit** (adaptively add the triplets where JGLP is still loose).
   ✅ **Running JGLP on the *unreduced* problem** is now done (`crown/rigorous.py`):
   it yields a rigorous, persistency-independent global bound shipped as a
   trustless pairwise-cluster certificate, upgrading demos B/C/D from
   `exact-core` to fully-rigorous `bound-tight`.
2. **Stronger persistency** — full strong-persistency / autarky (true QPBO), and
   QPBO-P/I probing to shrink cores that one LP vertex leaves fractional. Would
   let `exact-core` drop its reliance on the persistency theorem.
3. **Motif / rewrite-rule mining** (vision "theorem miner") — log
   `(motif, reduction, compression, core size)` across runs; surface recurring
   identities. This is e-graph / equality-saturation territory for QUBO.
5. **GPU kernels** — batch the contraction messages on tensor cores (cuTensorNet
   class workloads) once the elimination engine exists.

## 6. What to claim, and what not to

- ✅ "Certified lower bound + verifiable shell collapse on arbitrary QUBO."
- ✅ "Many real instances reduce to a small core" — empirically true (QPBO labels
  80–95% on real vision instances; demo B shows 89%).
- ❌ "Gauge concentrates frustration" — false (§2).
- ❌ "Solves NP-hard problems in P" — never; the core can stay exponential. The
  product is *distillation + certification*, not a complexity miracle.
- ❌ "Competitive with / beating state-of-the-art solvers" — false. toulbar2 (same
  algorithm family, tuned C++) is ~100–1000× faster and proves optima at sizes
  CROWN can't certify (`benchmarks/EXTERNAL_RESULTS.md`). CROWN is a *correct*
  (independently cross-validated) reference implementation, not a fast solver.
- ❌ "The certificate idea is novel" — unverified and probably overstated.
  Certified optimization is an active field (VeriPB, MAP-MRF dual certificates);
  CROWN's certificate is classical LP/Lagrangian duality + reparameterization. See
  **RELATED_WORK.md** for the honest positioning.

---

## Layout

```
crown/
  ising.py        QUBO model, exact energy, Ising view, canonical hashing
  roofdual.py     roof-dual LP: certified bound + dual certificate + persistency
  reduce.py       shell substitution + lift map
  elimination.py  exact bucket elimination + (weighted) mini-bucket + JGLP (layer 4)
  search.py       JGLP-guided AOBB, AND/OR-with-caching, component decomposition
  andor.py        static mini-bucket heuristic + AND/OR-with-MB-heuristic solver
  rigorous.py     full-problem JGLP -> trustless pairwise-cluster lower-bound cert
  solve.py        the distill→reduce→solve→certify pipeline
  certificate.py  Proof-of-Collapse certificate construction
  verify.py       trustless verifier
  qubo_io.py      load/save QUBOs (canonical JSON + sparse triplets)
  cli.py          the `crown` command-line interface (solve/verify/demo/bench)
  generators.py   structured test/demo instances
examples/demo.py  two-regime end-to-end demo
tests/test_crown.py  soundness tests (bound ≤ true min, tamper rejection, …)
```
