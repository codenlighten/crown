"""End-to-end CROWN v0 demo.

Run:  python -m examples.demo   (from the project root)

Shows two regimes:
  A) a field-dominated instance that is fully reduced and CERTIFIED OPTIMAL,
  B) a large shell wrapped around frustrated triangles -- high compression,
     small irreducible core solved exactly, with an honest residual bound gap.

Both runs emit a Proof-of-Collapse certificate and re-verify it trustlessly.
"""

from __future__ import annotations

import json
import os

import random

from crown import QUBO, build_certificate, crown_solve, save_certificate, verify
from crown.generators import make_field_dominated, make_random, make_shell_with_core


def make_two_blocks(block=30, seed=6):
    """Two independent frustrated blocks -> a wide, DISCONNECTED core. The pipeline
    decomposes it into components and solves each on its own (one may be thin
    enough for bucket elimination while the other needs AOBB)."""
    a = make_random(block, density=0.5, seed=seed, scale=2.0)
    b = make_random(block, density=0.5, seed=seed + 100, scale=2.0)
    lin = dict(a.linear)
    quad = dict(a.quadratic)
    for i, v in b.linear.items():
        lin[i + block] = v
    for (i, j), v in b.quadratic.items():
        quad[(i + block, j + block)] = v
    return QUBO(n=2 * block, linear=lin, quadratic=quad)

OUT = os.path.dirname(__file__)


def run(name: str, qubo) -> None:
    print("\n" + "#" * 60)
    print(f"# {name}   (problem hash {qubo.hash()[:12]}…)")
    print("#" * 60)

    result = crown_solve(qubo)
    print(result.summary())

    cert = build_certificate(qubo, result)
    cert_path = os.path.join(OUT, f"{name}.cert.json")
    prob_path = os.path.join(OUT, f"{name}.problem.json")
    save_certificate(cert, cert_path)
    with open(prob_path, "w") as fh:
        json.dump(qubo.canonical(), fh, indent=2)

    print("\n-- independent verification (no solver) --")
    report = verify(qubo, cert)
    print(report)
    print(f"\nwrote {os.path.relpath(prob_path)} and {os.path.relpath(cert_path)}")


def main() -> None:
    run("A_field_dominated", make_field_dominated(n=60, seed=7))
    run("B_shell_with_core", make_shell_with_core(shell=100, n_triangles=4, seed=3))
    # C: a 130-variable irreducible core (2^130 by brute force) but treewidth 2,
    #    solved EXACTLY and certified by bucket elimination in milliseconds.
    run("C_wide_thin_core", make_shell_with_core(shell=80, n_triangles=50, seed=11))
    # D: a dense core too wide for exact elimination -- weighted mini-bucket
    #    tightens the lower bound well past roof duality, shrinking the bracket.
    run("D_dense_wide_core", make_random(34, density=0.6, seed=3, scale=2.0))
    # E: a width-21 core (beyond exact elimination) where JGLP leaves a gap and
    #    AOBB proves the optimum by exhaustive bound-guided search.
    run("E_aobb_wide_core", make_random(30, density=0.5, seed=6, scale=2.0))
    # F: two independent frustrated blocks -- the core is wide AND disconnected;
    #    the pipeline decomposes it (AND) and solves each component separately.
    run("F_decomposable_core", make_two_blocks(block=30, seed=6))


if __name__ == "__main__":
    main()
