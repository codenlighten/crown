"""CROWN v0 -- a roof-duality-based hardness-distillation compiler for QUBO/Ising.

This is the buildable, provably-sound subset of the CROWN vision (see DESIGN.md):
distill the reducible shell with roof duality, extract the irreducible core,
solve it, and emit a trustless Proof-of-Collapse certificate.
"""

from .ising import QUBO
from .roofdual import roof_dual, verify_dual_bound, RoofDualResult
from .reduce import reduce_qubo, lift, Reduction
from .elimination import (
    bucket_elimination,
    mini_bucket,
    weighted_mini_bucket,
    mini_bucket_bound,
    join_graph_bound,
    join_graph_clusters,
    wide_core_bound,
    min_fill_order,
)
from .search import (
    aobb_solve,
    aobb_andor_solve,
    build_pseudo_tree,
    connected_components,
    solve_core_exact,
    SearchResult,
)
from .andor import aobb_andor_mb_solve, build_static_mb_heuristic, StaticMBHeuristic
from .rigorous import jglp_certificate, verify_jglp_certificate
from .solve import crown_solve, CrownResult, solve_core
from .certificate import build_certificate, save_certificate, load_certificate
from .verify import verify, qubo_from_canonical, VerificationReport

__all__ = [
    "QUBO",
    "roof_dual",
    "verify_dual_bound",
    "RoofDualResult",
    "reduce_qubo",
    "lift",
    "Reduction",
    "bucket_elimination",
    "mini_bucket",
    "weighted_mini_bucket",
    "mini_bucket_bound",
    "join_graph_bound",
    "join_graph_clusters",
    "wide_core_bound",
    "min_fill_order",
    "aobb_solve",
    "aobb_andor_solve",
    "aobb_andor_mb_solve",
    "build_static_mb_heuristic",
    "StaticMBHeuristic",
    "build_pseudo_tree",
    "connected_components",
    "solve_core_exact",
    "SearchResult",
    "jglp_certificate",
    "verify_jglp_certificate",
    "crown_solve",
    "CrownResult",
    "solve_core",
    "build_certificate",
    "save_certificate",
    "load_certificate",
    "verify",
    "qubo_from_canonical",
    "VerificationReport",
]
