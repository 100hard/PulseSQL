"""
PulseSQL Engine Package
=======================
Core engines powering AI Product Analytics:
- SemanticRouter: Matches user intent to canonical YAML definitions.
- SQLSynthesizer: Produces read-only SQL queries guarded by AST validation.
- SelfHealingExecutor: Resilient execution loop with automated DB feedback.
- RCAAnomalySlicer: One-click multi-dimensional root-cause analysis engine.
"""

from engine.semantic_router import SemanticMetricRouter, SemanticRoutingResult
from engine.sql_synthesizer import SQLSynthesizer, ReadOnlyGuardrailViolation, verify_readonly_ast
from engine.self_healing_executor import SelfHealingSQLExecutor, ExecutionCycleResult
from engine.rca_anomaly_slicer import RCAAnomalySlicer, RootCauseDiagnosticReport

__all__ = [
    "SemanticMetricRouter",
    "SemanticRoutingResult",
    "SQLSynthesizer",
    "ReadOnlyGuardrailViolation",
    "verify_readonly_ast",
    "SelfHealingSQLExecutor",
    "ExecutionCycleResult",
    "RCAAnomalySlicer",
    "RootCauseDiagnosticReport",
]
