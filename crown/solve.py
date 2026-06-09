"""The CROWN pipeline: distill -> reduce -> solve core -> lift -> certify.

Hardness distillation, restricted to provably-sound parts:

    1. roof_dual      -> certified GLOBAL lower bound + persistencies (shell)
    2. reduce_qubo    -> irreducible core + lift map
    3. solve_core     -> EXACT bucket elimination when the core's induced width
                         is small (scales to large thin cores), else a
                         mini-bucket LOWER BOUND plus a simulated-annealing
                         solution
    4. lift           -> full assignment, exact energy on the ORIGINAL problem
    5. certify        -> see `certificate_kind`:
         "bound-tight": energy == roof-dual global lower bound. Fully rigorous,
                        independent of persistency.
         "exact-core" : the core was solved exactly (bucket elimination), so the
                        lifted assignment is globally optimal -- relying on
                        roof-dual strong persistency (a theorem; also validated
                        empirically by the test suite). Closes gaps that the
                        roof-dual bound alone leaves open (e.g. frustrated cores).
         "bracket"    : neither; we report best-found energy and a lower bound
                        bracketing the true optimum, with the gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .elimination import bucket_elimination, min_fill_order, wide_core_bound
from .rigorous import jglp_certificate
from .search import aobb_solve, solve_core_exact

AOBB_BUDGET = 300_000
from .ising import QUBO
from .reduce import Reduction, lift, reduce_qubo
from .roofdual import RoofDualResult, roof_dual

EXACT_WIDTH_LIMIT = 20    # exact elimination feasible up to 2^(width+1) tables
DEFAULT_IBOUND = 16


@dataclass
class CoreSolution:
    assignment: List[int]
    energy: float
    method: str
    width: int
    is_exact: bool
    core_lower_bound: float    # exact value (if exact) or mini-bucket bound


@dataclass
class CrownResult:
    n: int
    core_size: int
    core_width: int
    compression_ratio: float
    lower_bound: float            # roof-dual global bound (has a trustless dual cert)
    rigorous_lower_bound: float   # max(roof dual, full-problem JGLP) -- both rigorous
    core_lower_bound: float       # elimination bound on the core
    energy: float
    gap: float                    # energy - best lower bound
    certified_optimal: bool
    certificate_kind: str         # bound-tight | exact-core | bound-tight-core | bracket
    solve_method: str
    assignment: List[int]
    fixed: Dict[int, int]
    roof: RoofDualResult = field(repr=False)
    reduction: Reduction = field(repr=False)
    jglp_cert: dict = field(default=None, repr=False)

    def summary(self) -> str:
        lines = [
            f"variables           : {self.n}",
            f"irreducible core    : {self.core_size}  (induced width {self.core_width})",
            f"compression ratio   : {self.compression_ratio:.1%} of variables decided pre-search",
            f"roof-dual lower bnd : {self.lower_bound:.6g}   (global, rigorous, dual cert)",
            f"JGLP rigorous bnd   : {self.rigorous_lower_bound:.6g}   (global, rigorous, cluster cert)",
            f"core elim lower bnd : {self.core_lower_bound:.6g}   (tighter, persistency-conditional)",
            f"core solved by      : {self.solve_method}",
            f"best energy found   : {self.energy:.6g}",
            f"optimality gap      : {self.gap:.6g}   (vs best lower bound)",
            f"certificate kind    : {self.certificate_kind}",
            f"CERTIFIED OPTIMAL   : {self.certified_optimal}",
        ]
        return "\n".join(lines)


def solve_core(core: QUBO, seed: int = 0, ibound: int = DEFAULT_IBOUND) -> CoreSolution:
    if core.n == 0:
        return CoreSolution([], core.const, "trivial (empty core)", 0, True, core.const)

    order, width = min_fill_order(core)
    if width <= EXACT_WIDTH_LIMIT:
        energy, x = bucket_elimination(core, order)
        return CoreSolution(x, energy, f"exact-elimination (width {width})", width, True, energy)

    # too wide to eliminate exactly: report the JGLP bound, then decompose into
    # independent components (AND) and prove each exactly (BE / bound-guided B&B).
    lb = wide_core_bound(core, order=order)
    e, x, complete, m = solve_core_exact(core, seed=seed, flat_budget=AOBB_BUDGET)
    if complete:                                  # every component proven optimal
        return CoreSolution(x, e, f"decompose+{m} (width {width})", width, True, e)
    return CoreSolution(x, e, f"JGLP bound + decompose+{m}(partial) (width {width})",
                        width, False, lb)


_JGLP_CERT_MAX_VARS = 400          # skip the (polynomial) full-problem JGLP above this


def crown_solve(qubo: QUBO, seed: int = 0, tol: float = 1e-6) -> CrownResult:
    roof = roof_dual(qubo)
    reduction = reduce_qubo(qubo, roof.persistencies)
    core_sol = solve_core(reduction.core, seed=seed)
    x = lift(reduction, core_sol.assignment, qubo.n)
    energy = qubo.energy(x)

    # A rigorous, persistency-INDEPENDENT global bound: JGLP on the UNREDUCED
    # problem, shipped as a trustless cluster certificate. Tighter than roof
    # duality on frustrated structure, so it lifts many results to `bound-tight`.
    jglp_cert, jglp_lb = None, float("-inf")
    if qubo.n <= _JGLP_CERT_MAX_VARS:
        out = jglp_certificate(qubo)
        if out is not None:
            jglp_cert, jglp_lb = out
    rigorous_lb = max(roof.lower_bound, jglp_lb)

    decided = qubo.n - reduction.core.n
    best_lb = max(rigorous_lb, core_sol.core_lower_bound)
    gap = energy - best_lb
    tolabs = max(tol, tol * abs(energy))

    if abs(energy - rigorous_lb) <= tolabs:
        kind, certified = "bound-tight", True            # rigorous, trustless
    elif core_sol.is_exact:
        kind, certified = "exact-core", True             # exact elimination
    elif abs(energy - core_sol.core_lower_bound) <= tolabs:
        kind, certified = "bound-tight-core", True       # weighted-MB bound met
    else:
        kind, certified = "bracket", False

    return CrownResult(
        n=qubo.n,
        core_size=reduction.core.n,
        core_width=core_sol.width,
        compression_ratio=(decided / qubo.n) if qubo.n else 1.0,
        lower_bound=roof.lower_bound,
        rigorous_lower_bound=rigorous_lb,
        core_lower_bound=core_sol.core_lower_bound,
        energy=energy,
        gap=gap,
        certified_optimal=certified,
        certificate_kind=kind,
        solve_method=core_sol.method,
        assignment=x,
        fixed=reduction.fixed,
        roof=roof,
        reduction=reduction,
        jglp_cert=jglp_cert,
    )
