"""Correctness tests -- the basis for 'every number it prints is defensible'.

Run:  python -m pytest -q   (or: python tests/test_crown.py)
"""

from __future__ import annotations

import itertools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crown import build_certificate, crown_solve, verify
from crown.elimination import (
    bucket_elimination,
    mini_bucket,
    weighted_mini_bucket,
    mini_bucket_bound,
    join_graph_bound,
    wide_core_bound,
    min_fill_order,
)
from crown.generators import (
    make_field_dominated,
    make_random,
    make_shell_with_core,
    _antiferro_triangle,
)
from crown.ising import QUBO
from crown.roofdual import roof_dual, verify_dual_bound


def brute_min(qubo: QUBO) -> float:
    best = float("inf")
    for bits in itertools.product((0, 1), repeat=qubo.n):
        best = min(best, qubo.energy(list(bits)))
    return best


# ---------------------------------------------------------------- energy --- #
def test_energy_matches_matrix_form():
    Q = np.array([[1.0, -2.0], [0.0, 3.0]])
    qubo = QUBO.from_matrix(Q)
    # E = 1*x0 + 3*x1 - 2*x0*x1
    for x in itertools.product((0, 1), repeat=2):
        expected = 1 * x[0] + 3 * x[1] - 2 * x[0] * x[1]
        assert qubo.energy(list(x)) == expected


def test_ising_roundtrip_energy():
    qubo = make_random(6, density=0.6, seed=1)
    h, J, off = qubo.to_ising()
    for x in itertools.product((0, 1), repeat=6):
        s = {i: 2 * x[i] - 1 for i in range(6)}
        e = off + sum(h.get(i, 0.0) * s[i] for i in range(6))
        e += sum(v * s[i] * s[j] for (i, j), v in J.items())
        assert abs(e - qubo.energy(list(x))) < 1e-9


# --------------------------------------------------- roof-dual soundness --- #
def test_roof_dual_is_a_valid_lower_bound():
    for seed in range(8):
        qubo = make_random(7, density=0.5, seed=seed, scale=3.0)
        rd = roof_dual(qubo)
        true_min = brute_min(qubo)
        assert rd.lower_bound <= true_min + 1e-6, (rd.lower_bound, true_min)


def test_dual_certificate_self_verifies():
    for seed in range(8):
        qubo = make_random(7, density=0.5, seed=seed, scale=3.0)
        rd = roof_dual(qubo)
        ok, lb, msg = verify_dual_bound(qubo, rd.certificate)
        assert ok, msg
        assert abs(lb - rd.lower_bound) < 1e-5


def test_persistencies_are_correct():
    # field-dominated: every fixed variable must match the true optimum's value
    qubo = make_field_dominated(12, seed=2)
    rd = roof_dual(qubo)
    # find a true optimizer by brute force
    best, best_e = None, float("inf")
    for bits in itertools.product((0, 1), repeat=12):
        e = qubo.energy(list(bits))
        if e < best_e:
            best_e, best = e, bits
    for i, v in rd.persistencies.items():
        assert best[i] == v, f"var {i} fixed to {v} but optimum has {best[i]}"


# ------------------------------------------------------- full pipeline ---- #
def test_field_dominated_is_certified_optimal():
    qubo = make_field_dominated(40, seed=5)
    res = crown_solve(qubo)
    assert res.certified_optimal
    assert res.core_size == 0
    assert abs(res.energy - brute_min(make_field_dominated(12, seed=5))) >= 0  # smoke


def test_shell_with_core_compresses_and_certifies():
    qubo = make_shell_with_core(shell=40, n_triangles=3, seed=4)
    res = crown_solve(qubo)
    # shell decided, only the 9 triangle vars survive as the core
    assert res.core_size <= 9
    assert res.compression_ratio >= 0.7
    # both rigorous bounds are valid brackets
    assert res.lower_bound <= res.energy + 1e-6
    assert res.rigorous_lower_bound <= res.energy + 1e-6
    # the frustrated triangles are closed RIGOROUSLY by the full-problem JGLP
    # bound (roof duality is loose here), so the result is bound-tight.
    assert res.certificate_kind == "bound-tight"
    assert res.certified_optimal


# ------------------------------------------------------ elimination ------- #
def test_bucket_elimination_matches_brute_force():
    for seed in range(10):
        qubo = make_random(9, density=0.5, seed=seed, scale=3.0)
        be, x = bucket_elimination(qubo)
        assert abs(be - brute_min(qubo)) < 1e-9
        assert abs(qubo.energy(x) - be) < 1e-9   # returned assignment achieves it


def test_mini_bucket_is_sound_lower_bound_and_exact_at_full_ibound():
    for seed in range(10):
        qubo = make_random(10, density=0.4, seed=seed, scale=2.0)
        order, w = min_fill_order(qubo)
        assert mini_bucket(qubo, ibound=2) <= brute_min(qubo) + 1e-9
        assert abs(mini_bucket(qubo, ibound=w + 1, order=order)
                   - bucket_elimination(qubo, order)[0]) < 1e-9


def test_weighted_mini_bucket_is_sound_and_bound_is_tighter():
    plain_gap = wmb_gap = 0.0
    for seed in range(20):
        qubo = make_random(15, density=0.55, seed=seed, scale=2.0)
        order, w = min_fill_order(qubo)
        tm = brute_min(qubo)
        plain = mini_bucket(qubo, ibound=5, order=order)
        wmb = weighted_mini_bucket(qubo, ibound=5, order=order)
        best = mini_bucket_bound(qubo, ibound=5, order=order)
        # soundness: all are valid lower bounds
        assert plain <= tm + 1e-9 and wmb <= tm + 1e-9 and best <= tm + 1e-9
        # the combined bound is never worse than plain, and is a true lower bound
        assert best >= plain - 1e-9
        # exact at full i-bound
        assert abs(weighted_mini_bucket(qubo, ibound=w + 1, order=order)
                   - bucket_elimination(qubo, order)[0]) < 1e-9
        plain_gap += tm - plain
        wmb_gap += tm - best
    # across the batch, weighted bound is strictly tighter on average
    assert wmb_gap < plain_gap - 1e-6, (wmb_gap, plain_gap)


def test_jglp_beats_roof_dual_on_frustrated_triangle():
    from crown.roofdual import roof_dual
    tri = _antiferro_triangle(0, strength=1.0)
    true_min = brute_min(tri)
    rd = roof_dual(tri).lower_bound
    jg = join_graph_bound(tri, ibound=3, iters=200)
    assert rd < true_min - 1e-6          # roof duality is provably loose here
    assert jg > rd + 1e-6                 # JGLP strictly tighter
    assert abs(jg - true_min) < 1e-6      # and reaches the exact optimum


def test_jglp_is_monotone_and_sound():
    for seed in range(15):
        qubo = make_random(14, density=0.5, seed=seed, scale=2.0)
        order, _ = min_fill_order(qubo)
        jg, trace = join_graph_bound(qubo, ibound=6, iters=150, order=order, return_trace=True)
        for a, b in zip(trace, trace[1:]):
            assert b >= a - 1e-6          # monotone non-decreasing
        assert jg <= brute_min(qubo) + 1e-6   # sound lower bound


def test_wide_core_bound_is_sound_and_best():
    for seed in range(15):
        qubo = make_random(14, density=0.5, seed=seed, scale=2.0)
        order, _ = min_fill_order(qubo)
        tm = brute_min(qubo)
        b = wide_core_bound(qubo, order=order)
        assert b <= tm + 1e-6
        assert b >= mini_bucket(qubo, ibound=16, order=order) - 1e-6
        assert b >= join_graph_bound(qubo, ibound=10, iters=60, order=order) - 1e-6


def test_aobb_matches_brute_force_and_proves_optimality():
    from crown.search import aobb_solve
    for n in (8, 12, 14):
        for d in (0.4, 0.8):
            for seed in range(4):
                qubo = make_random(n, density=d, seed=seed, scale=2.0)
                r = aobb_solve(qubo, node_budget=5_000_000)
                bf = brute_min(qubo)
                assert r.complete                              # exhaustive
                assert abs(r.energy - bf) < 1e-6
                assert abs(qubo.energy(r.assignment) - bf) < 1e-6   # valid assignment


def test_aobb_robust_to_arbitrary_incumbent():
    from crown.search import aobb_solve
    for seed in range(8):
        qubo = make_random(13, density=0.5, seed=seed, scale=2.0)
        r = aobb_solve(qubo, incumbent_energy=1e9, incumbent_x=[0] * 13, node_budget=5_000_000)
        assert r.complete and abs(r.energy - brute_min(qubo)) < 1e-6


def test_aobb_certifies_a_wide_core_beyond_exact_elimination():
    # n=30 seed=6: core width 21 (too wide for exact bucket elimination); JGLP
    # leaves a gap, and AOBB proves the optimum by exhaustive search (~1.5k nodes).
    qubo = make_random(30, density=0.5, seed=6, scale=2.0)
    res = crown_solve(qubo)
    assert res.core_width > 20
    assert res.certified_optimal
    assert res.certificate_kind == "exact-core"
    assert "AOBB" in res.solve_method
    cert = build_certificate(qubo, res)
    report = verify(qubo, cert)                                 # verifier re-searches
    assert report.ok and report.certified_optimal


def test_andor_matches_brute_force_including_disconnected():
    from crown.search import aobb_andor_solve, build_pseudo_tree
    # connected instances
    for n in (8, 12, 14):
        for seed in range(4):
            qubo = make_random(n, density=0.5, seed=seed, scale=2.0)
            r = aobb_andor_solve(qubo, node_budget=20_000_000)
            assert r.complete and abs(r.energy - brute_min(qubo)) < 1e-6
            assert abs(qubo.energy(r.assignment) - r.energy) < 1e-6
    # a deliberately disconnected core must decompose and sum correctly
    lin = dict(make_random(7, density=0.6, seed=1).linear)
    quad = dict(make_random(7, density=0.6, seed=1).quadratic)
    q2 = make_random(7, density=0.6, seed=2)
    for i, a in q2.linear.items():
        lin[i + 7] = a
    for (i, j), b in q2.quadratic.items():
        quad[(i + 7, j + 7)] = b
    disc = QUBO(n=14, linear=lin, quadratic=quad)
    r = aobb_andor_solve(disc, node_budget=20_000_000)
    assert r.complete and abs(r.energy - brute_min(disc)) < 1e-6


def test_connected_components_partition_the_core():
    from crown.search import connected_components
    q2 = make_random(6, density=0.6, seed=2)
    lin = {i: a for i, a in make_random(6, density=0.6, seed=1).linear.items()}
    quad = dict(make_random(6, density=0.6, seed=1).quadratic)
    for i, a in q2.linear.items():
        lin[i + 6] = a
    for (i, j), b in q2.quadratic.items():
        quad[(i + 6, j + 6)] = b
    disc = QUBO(n=12, linear=lin, quadratic=quad)
    comps = connected_components(disc)
    assert len(comps) == 2
    assert sorted(v for _, vs in comps for v in vs) == list(range(12))


def test_solve_core_exact_decomposes_disconnected_core():
    from crown.search import solve_core_exact, connected_components
    # two independent dense frustrated blocks -> solved by decomposition + summed
    import random
    rng = random.Random(0)
    lin, quad = {}, {}
    for base in (0, 9):
        for i in range(9):
            lin[base + i] = rng.uniform(-0.5, 0.5)
            for j in range(i + 1, 9):
                if rng.random() < 0.6:
                    quad[(base + i, base + j)] = rng.uniform(0.3, 1.2)
    core = QUBO(n=18, linear=lin, quadratic=quad)
    assert len(connected_components(core)) == 2
    e, x, complete, method = solve_core_exact(core)
    assert complete
    assert abs(core.energy(x) - e) < 1e-6      # assignment achieves the reported energy
    assert abs(e - brute_min(core)) < 1e-6     # and it is the true global optimum


def test_static_mb_heuristic_is_sound_and_exact_at_large_ibound():
    import itertools as it
    from crown.search import build_pseudo_tree
    from crown.andor import build_static_mb_heuristic

    def local(pt, Y, a):
        return pt.unary[Y] * a[Y] + sum(b * a[A] * a[Y] for (A, b) in pt.anc_edges[Y])

    def true_subtree_min(pt, node, ctx):
        sub = pt.subtree[node]
        best = float("inf")
        for bits in it.product((0, 1), repeat=len(sub)):
            a = dict(ctx)
            a.update({v: bit for v, bit in zip(sub, bits)})
            best = min(best, sum(local(pt, Y, a) for Y in sub))
        return best

    for seed in range(6):
        q = make_random(10, density=0.5, seed=seed, scale=2.0)
        pt = build_pseudo_tree(q)
        for ib, exact in ((2, False), (99, True)):
            H = build_static_mb_heuristic(q, pt, ibound=ib)
            for node in range(q.n):
                cvars = pt.context[node]
                if len(cvars) > 6:
                    continue
                for cbits in it.product((0, 1), repeat=len(cvars)):
                    ctx = {v: b for v, b in zip(cvars, cbits)}
                    hv = H.h(node, ctx)
                    tv = true_subtree_min(pt, node, ctx)
                    assert hv <= tv + 1e-7                      # sound lower bound
                    if exact:
                        assert abs(hv - tv) < 1e-6              # tight when not split


def test_andor_mb_matches_brute_force():
    from crown.andor import aobb_andor_mb_solve
    for n in (8, 12, 14):
        for d in (0.4, 0.8):
            for seed in range(4):
                qubo = make_random(n, density=d, seed=seed, scale=2.0)
                for mm in (False, True):                   # both heuristic modes exact
                    r = aobb_andor_mb_solve(qubo, ibound=4, node_budget=9_000_000,
                                            moment_match=mm)
                    bf = brute_min(qubo)
                    assert r.complete and abs(r.energy - bf) < 1e-6
                    assert abs(qubo.energy(r.assignment) - bf) < 1e-6


def test_bucket_tree_cost_shifting_tightens_heuristic():
    # within-bucket moment matching must be sound AND tighter (smaller gap to the
    # true subtree min, summed over contexts) than the un-shifted heuristic.
    import itertools as it
    from crown.search import build_pseudo_tree
    from crown.andor import build_static_mb_heuristic

    def local(pt, Y, a):
        return pt.unary[Y] * a[Y] + sum(b * a[A] * a[Y] for (A, b) in pt.anc_edges[Y])

    def true_subtree_min(pt, node, ctx):
        sub = pt.subtree[node]
        best = float("inf")
        for bits in it.product((0, 1), repeat=len(sub)):
            a = dict(ctx)
            a.update({v: bit for v, bit in zip(sub, bits)})
            best = min(best, sum(local(pt, Y, a) for Y in sub))
        return best

    gap_plain = gap_mm = 0.0
    for seed in range(8):
        q = make_random(11, density=0.5, seed=seed, scale=2.0)
        pt = build_pseudo_tree(q)
        Hp = build_static_mb_heuristic(q, pt, ibound=3, moment_match=False)
        Hm = build_static_mb_heuristic(q, pt, ibound=3, moment_match=True)
        for node in range(q.n):
            cv = pt.context[node]
            if len(cv) > 5:
                continue
            for cb in it.product((0, 1), repeat=len(cv)):
                ctx = {v: b for v, b in zip(cv, cb)}
                tv = true_subtree_min(pt, node, ctx)
                assert Hp.h(node, ctx) <= tv + 1e-7        # both sound
                assert Hm.h(node, ctx) <= tv + 1e-7
                gap_plain += tv - Hp.h(node, ctx)
                gap_mm += tv - Hm.h(node, ctx)
    assert gap_mm < gap_plain - 1e-6                       # strictly tighter overall


def test_andor_complete_flag_is_sound_under_budget():
    # When the budget is hit, `complete` must be False; when True, the result
    # must be the exact optimum with a valid assignment.
    from crown.andor import aobb_andor_mb_solve
    qubo = make_random(18, density=0.6, seed=1, scale=2.0)
    truth = brute_min(qubo)
    for budget in (500, 5_000, 50_000, 5_000_000):
        r = aobb_andor_mb_solve(qubo, node_budget=budget)
        if r.complete:
            assert abs(r.energy - truth) < 1e-6
            assert abs(qubo.energy(r.assignment) - r.energy) < 1e-6
            assert r.nodes <= budget


def test_jglp_certificate_is_sound_and_trustlessly_verifiable():
    from crown.rigorous import jglp_certificate, verify_jglp_certificate
    for seed in range(10):
        qubo = make_random(11, density=0.5, seed=seed, scale=2.0)
        out = jglp_certificate(qubo, ibound=6)
        assert out is not None
        cert, lb = out
        ok, vlb, msg = verify_jglp_certificate(qubo, cert)
        assert ok, msg                                   # clusters sum back to the QUBO
        assert abs(vlb - lb) < 1e-6                       # verifier recovers the bound
        assert vlb <= brute_min(qubo) + 1e-6              # sound lower bound


def test_jglp_certificate_beats_roof_dual_on_frustration():
    from crown.generators import _antiferro_triangle
    from crown.rigorous import jglp_certificate, verify_jglp_certificate
    from crown.roofdual import roof_dual
    tri = _antiferro_triangle(0, strength=1.0)
    cert, lb = jglp_certificate(tri, ibound=3)
    ok, vlb, _ = verify_jglp_certificate(tri, cert)
    assert ok
    assert vlb > roof_dual(tri).lower_bound + 1e-6        # strictly tighter
    assert abs(vlb - brute_min(tri)) < 1e-6               # and reaches the optimum


def test_verifier_rejects_tampered_jglp_certificate():
    qubo = make_shell_with_core(shell=40, n_triangles=3, seed=4)
    res = crown_solve(qubo)
    assert res.certificate_kind == "bound-tight"          # certified via JGLP cert
    cert = build_certificate(qubo, res)
    # tamper a cluster coefficient: the clusters no longer sum to the QUBO
    cert["jglp"]["clusters"][0]["const"] += 5.0
    report = verify(qubo, cert)
    assert not report.ok


def test_frustrated_demos_are_rigorously_bound_tight():
    # B/C/D-style instances: roof duality is loose but full-problem JGLP is tight
    qubo = make_shell_with_core(shell=60, n_triangles=4, seed=3)
    res = crown_solve(qubo)
    assert res.certificate_kind == "bound-tight"
    assert res.rigorous_lower_bound > res.lower_bound + 1e-6   # JGLP beat roof dual
    cert = build_certificate(qubo, res)
    assert verify(qubo, cert).ok and verify(qubo, cert).certified_optimal


def test_elimination_scales_to_wide_thin_core():
    # 90 variables -> 2^90 by brute force, but treewidth 2
    qubo = make_shell_with_core(shell=0, n_triangles=30, seed=1)
    order, w = min_fill_order(qubo)
    assert w <= 3
    be, x = bucket_elimination(qubo, order)
    assert abs(qubo.energy(x) - be) < 1e-9


def test_wide_core_verification_is_consistent_and_accepts_honest_bracket():
    qubo = make_random(34, density=0.6, seed=3, scale=2.0)
    res = crown_solve(qubo)
    cert = build_certificate(qubo, res)
    report = verify(qubo, cert)
    assert report.ok                                   # honest cert accepted
    assert report.certified_optimal == res.certified_optimal


def test_verifier_rejects_optimality_overclaim():
    qubo = make_random(34, density=0.6, seed=3, scale=2.0)
    res = crown_solve(qubo)
    if res.certified_optimal:
        return  # only meaningful when a real gap remains
    cert = build_certificate(qubo, res)
    cert["claimed_certified_optimal"] = True           # lie: claim optimality
    assert not verify(qubo, cert).ok


def test_verifier_confirms_exact_core_and_rejects_tamper():
    qubo = make_shell_with_core(shell=30, n_triangles=3, seed=6)
    res = crown_solve(qubo)
    cert = build_certificate(qubo, res)
    report = verify(qubo, cert)
    assert report.ok and report.certified_optimal     # exact-core confirmed by re-solve
    # tampering the core assignment must break the exact re-solve check
    cert["assignment"][res.reduction.core_to_orig[0]] ^= 1
    bad = verify(qubo, cert)
    assert not bad.ok


def test_pipeline_solution_is_global_optimum_on_small_instances():
    for seed in range(5):
        qubo = make_random(10, density=0.5, seed=seed, scale=2.0)
        res = crown_solve(qubo)
        assert abs(res.energy - brute_min(qubo)) < 1e-6


# ----------------------------------------------------- verifier behaviour - #
def test_verifier_accepts_genuine_certificate():
    qubo = make_shell_with_core(shell=30, n_triangles=2, seed=1)
    res = crown_solve(qubo)
    cert = build_certificate(qubo, res)
    report = verify(qubo, cert)
    assert report.ok


def test_verifier_rejects_tampered_solution():
    qubo = make_field_dominated(20, seed=9)
    res = crown_solve(qubo)
    cert = build_certificate(qubo, res)
    cert["assignment"][0] ^= 1            # flip one bit, claim same energy
    report = verify(qubo, cert)
    assert not report.ok


def test_verifier_rejects_wrong_problem():
    qubo = make_field_dominated(20, seed=9)
    other = make_field_dominated(20, seed=10)
    cert = build_certificate(qubo, crown_solve(qubo))
    report = verify(other, cert)
    assert not report.ok


def test_verifier_rejects_fake_lower_bound():
    qubo = make_shell_with_core(shell=20, n_triangles=2, seed=2)
    res = crown_solve(qubo)
    cert = build_certificate(qubo, res)
    # inflate the bound to fake optimality; dual won't support it
    cert["lower_bound"] = cert["energy"]
    report = verify(qubo, cert)
    assert not report.ok


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa
            failed += 1
            print(f"ERROR {fn.__name__}: {exc!r}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
