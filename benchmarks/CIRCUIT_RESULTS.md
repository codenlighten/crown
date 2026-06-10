# CROWN certificate as a verification circuit

Generated 2026-06-10 01:29 UTC. Decouple find-from-prove: toulbar2 supplies the optimum, CROWN's JGLP attempts to certify it. Cost metric `r1cs ≈ m_Q + Σ_c 2^(scope_c)` (the SNARK/on-chain driver), after a validity-preserving minimiser. Sizes [12, 16, 20, 24, 28], i-bounds [5, 10].

## i-bound = 5

| family | n | certifies? | r1cs constraints | max cluster scope | bytes |
|---|---|---|---|---|---|
| sk-spin-glass | 12 | **no** (gap) | — | — | — |
| sk-spin-glass | 16 | **no** (gap) | — | — | — |
| sk-spin-glass | 20 | **no** (gap) | — | — | — |
| sk-spin-glass | 24 | **no** (gap) | — | — | — |
| sk-spin-glass | 28 | **no** (gap) | — | — | — |
| max-cut | 12 | yes | 170 | 5 | 2487 |
| max-cut | 16 | **no** (gap) | — | — | — |
| max-cut | 20 | **no** (gap) | — | — | — |
| max-cut | 24 | **no** (gap) | — | — | — |
| max-cut | 28 | **no** (gap) | — | — | — |

## i-bound = 10

| family | n | certifies? | r1cs constraints | max cluster scope | bytes |
|---|---|---|---|---|---|
| sk-spin-glass | 12 | **no** (gap) | — | — | — |
| sk-spin-glass | 16 | **no** (gap) | — | — | — |
| sk-spin-glass | 20 | **no** (gap) | — | — | — |
| sk-spin-glass | 24 | **no** (gap) | — | — | — |
| sk-spin-glass | 28 | **no** (gap) | — | — | — |
| max-cut | 12 | yes | 170 | 5 | 2487 |
| max-cut | 16 | **no** (gap) | — | — | — |
| max-cut | 20 | yes | 2120 | 9 | 8288 |
| max-cut | 24 | **no** (gap) | — | — | — |
| max-cut | 28 | **no** (gap) | — | — | — |

## Findings

- **i-bound 5**: certified 1/10; where certified, r1cs 170–170 (largest: n=12, 170 constraints, scope 5, 2487 bytes).
- **i-bound 10**: certified 2/10; where certified, r1cs 170–2120 (largest: n=20, 2120 constraints, scope 9, 8288 bytes).

## Honest read

The certificate is small in **bytes** but its **verification circuit** is driven by `Σ_c 2^(scope_c)`: closing the QUBO integrality gap needs higher-order clusters, each costing `2^scope` to check, and more of them as frustration grows. A small i-bound keeps the circuit cheap but fails to certify the hard instances; a large i-bound certifies more but blows up the circuit. This is the integer/convex divide (vs. Otti's convex SNARKs) appearing directly as circuit cost.
