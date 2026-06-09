"""Command-line interface for CROWN.

    crown solve   PROBLEM [--cert C.json] [--problem P.json] [--seed N]
    crown verify  PROBLEM.json CERT.json
    crown demo
    crown bench   [--quick]

PROBLEM is a QUBO in canonical JSON (`.json`) or sparse-triplet text
(`.txt`/`.qubo`); see crown/qubo_io.py. Also runs as `python -m crown ...`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .certificate import build_certificate, save_certificate
from .qubo_io import load_qubo, qubo_from_canonical, save_qubo
from .solve import crown_solve
from .verify import verify


def _cmd_solve(args: argparse.Namespace) -> int:
    qubo = load_qubo(args.problem)
    res = crown_solve(qubo, seed=args.seed)
    print(res.summary())
    if args.problem_out:
        save_qubo(qubo, args.problem_out)
        print(f"\nwrote problem  -> {args.problem_out}")
    if args.cert:
        save_certificate(build_certificate(qubo, res), args.cert)
        print(f"wrote certificate -> {args.cert}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    with open(args.problem) as fh:
        qubo = qubo_from_canonical(json.load(fh))
    with open(args.cert) as fh:
        cert = json.load(fh)
    report = verify(qubo, cert)
    print(report)
    return 0 if report.ok else 1


_REPO_ONLY = ("this command needs the source tree (examples/ and benchmarks/ are "
              "not part of the installed package) -- run it from a CROWN checkout.")


def _cmd_demo(_args: argparse.Namespace) -> int:
    try:
        from examples import demo  # type: ignore
    except ModuleNotFoundError:
        print(f"crown demo: {_REPO_ONLY}", file=sys.stderr)
        return 2
    demo.main()
    return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    try:
        from benchmarks import run_benchmark  # type: ignore
    except ModuleNotFoundError:
        print(f"crown bench: {_REPO_ONLY}", file=sys.stderr)
        return 2
    return run_benchmark.main(["bench"] + (["--quick"] if args.quick else []))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crown", description="Certified QUBO/Ising optimization.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="solve a QUBO and emit a Proof-of-Collapse certificate")
    s.add_argument("problem", help="QUBO file (.json canonical or .txt/.qubo triplets)")
    s.add_argument("--cert", help="write the certificate JSON here")
    s.add_argument("--problem", dest="problem_out", help="write the canonical problem JSON here")
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=_cmd_solve)

    v = sub.add_parser("verify", help="trustlessly verify a certificate against a problem")
    v.add_argument("problem", help="canonical problem JSON")
    v.add_argument("cert", help="certificate JSON")
    v.set_defaults(func=_cmd_verify)

    d = sub.add_parser("demo", help="run the six end-to-end demo regimes")
    d.set_defaults(func=_cmd_demo)

    b = sub.add_parser("bench", help="run the benchmark harness")
    b.add_argument("--quick", action="store_true")
    b.set_defaults(func=_cmd_bench)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
