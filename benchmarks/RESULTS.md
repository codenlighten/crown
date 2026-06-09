# CROWN benchmark results

Generated 2026-06-09 14:23 UTC · 80 instances · families ['field-dominated', 'shell+core', 'random-sparse', 'random-dense'] · sizes [12, 16, 28, 44] · 5 seeds each.

## Correctness (vs brute force)

- CROWN matched the brute-force optimum on **40/40** instances with n ≤ 18.

## Certificate self-verification

- Re-verified **80/80** Proof-of-Collapse certificates (independent verifier accepted).
- Verifier verdict matched the prover's claim on **80/80** (no over-claims).

## Per-family summary

| family | #inst | certified | rigorous `bound-tight` | mean compression | SA reached optimum | median t (CROWN) | median t (SA) |
|---|---|---|---|---|---|---|---|
| field-dominated | 20 | 100% | 100% | 100% | 100% | 5 ms | 51 ms |
| shell+core | 20 | 100% | 100% | 39% | 100% | 5 ms | 50 ms |
| random-sparse | 20 | 100% | 85% | 78% | 100% | 13 ms | 61 ms |
| random-dense | 20 | 90% | 70% | 32% | 100% | 238 ms | 81 ms |

## Rigorous bound quality (certified instances, optimum known)

- Mean gap-to-optimum: **roof duality 6.035** → **full-problem JGLP 0.253** (lower is tighter).
- JGLP closed the gap to a fully-rigorous `bound-tight` proof on **71/78** certified instances.

## Scale (beyond brute force)

- On the **40** instances with n > 18 (up to n=44, 2^44 configurations), CROWN returned a **certified optimum** on **95%** — proofs, not just heuristic guesses.

