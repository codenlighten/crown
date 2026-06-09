# CROWN vs. state-of-the-art exact solvers

Generated 2026-06-09 18:33 UTC. Solvers: CROWN (pure Python) vs toulbar2, scip (tuned C++), brute force for n ≤ 18. External time limit 20s; CROWN run only for n ≤ 28.

## Correctness cross-check (the result that matters)

- CROWN's optimum **agreed with toulbar2 on 20/20** instances both ran.
- On the **19** instances CROWN reported as *certified*, it matched toulbar2's proven optimum **every time** (19/19).
- Triangulated against brute force on 8 small instances: CROWN == toulbar2 == brute on **8/8**.
- ✅ No invariant violated: CROWN never undercut a proven optimum and never certified a wrong one.

## Head-to-head: time and certification (both solvers run)

| family | n | CROWN energy | CROWN certified | CROWN time | toulbar2 energy | toulbar2 proven | toulbar2 time |
|---|---|---|---|---|---|---|---|
| sk-spin-glass | 12 | -26 | True | 0.39s | -26 | True | 0.001s |
| sk-spin-glass | 12 | -28 | True | 0.39s | -28 | True | 0.001s |
| sk-spin-glass | 16 | -42 | True | 0.42s | -42 | True | 0.003s |
| sk-spin-glass | 16 | -42 | True | 0.76s | -42 | True | 0.004s |
| sk-spin-glass | 20 | -62 | True | 1.38s | -62 | True | 0.013s |
| sk-spin-glass | 20 | -66 | True | 1.40s | -66 | True | 0.013s |
| sk-spin-glass | 24 | -82 | True | 7.75s | -82 | True | 0.073s |
| sk-spin-glass | 24 | -78 | True | 11.87s | -78 | True | 0.106s |
| sk-spin-glass | 28 | -100 | False | 36.39s | -100 | True | 0.626s |
| sk-spin-glass | 28 | -118 | True | 15.94s | -118 | True | 0.309s |
| max-cut | 12 | -19 | True | 0.04s | -19 | True | 0.000s |
| max-cut | 12 | -27 | True | 0.02s | -27 | True | 0.000s |
| max-cut | 16 | -33 | True | 0.07s | -33 | True | 0.000s |
| max-cut | 16 | -40 | True | 0.11s | -40 | True | 0.001s |
| max-cut | 20 | -61 | True | 0.24s | -61 | True | 0.002s |
| max-cut | 20 | -61 | True | 0.33s | -61 | True | 0.003s |
| max-cut | 24 | -83 | True | 0.46s | -83 | True | 0.014s |
| max-cut | 24 | -90 | True | 0.65s | -90 | True | 0.020s |
| max-cut | 28 | -122 | True | 0.95s | -122 | True | 0.086s |
| max-cut | 28 | -125 | True | 0.92s | -125 | True | 0.073s |

Median speed gap: toulbar2 is ~**110×** faster across these instances.

## Scale frontier (beyond CROWN's reach — toulbar2 only)

| family | n | toulbar2 energy | proven | time |
|---|---|---|---|---|
| sk-spin-glass | 40 | -176 | False | 20.003s |
| sk-spin-glass | 60 | -298 | False | 20.011s |
| sk-spin-glass | 90 | -537 | False | 20.014s |
| max-cut | 40 | -248 | True | 14.039s |
| max-cut | 60 | -528 | False | 20.036s |
| max-cut | 90 | -1126 | False | 20.013s |

## Honest read

CROWN is **correct** — an independent SOTA solver (and brute force) corroborate its optima, and it never falsely certified. CROWN is **not performance-competitive**: toulbar2 implements the same algorithm family in tuned C++ and is orders of magnitude faster, proving optima at problem sizes where CROWN's pure-Python search cannot even certify. CROWN's value is the *verifiable certificate* and the clean reference implementation, not raw solve speed.
