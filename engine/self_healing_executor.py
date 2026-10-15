"""
PulseSQL Self-Healing SQL Executor
==================================
Executes SQL queries against the analytical database within a resilient,
self-healing feedback loop. Intercepts database operational errors,
feeds diagnostic tracebacks back into the synthesis engine, and re-executes
up to 2 repair iterations while strictly enforcing read-only AST safety.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from engine.semantic_router import SemanticMetricRouter, SemanticRoutingResult
from engine.sql_synthesizer import (
    ReadOnlyGuardrailViolation,
    SQLSynthesizer,
    verify_readonly_ast,
)


@dataclass
class ExecutionCycleResult:
    """Encapsulates the full execution lifecycle and self-healing diagnostics."""
    query_result_dataframe: pd.DataFrame
    executed_sql: str
    initial_execution_passed: bool
    healed_execution_passed: bool
    healing_iterations_used: int
    execution_latency_ms: float
    error_traces: List[str] = field(default_factory=list)
    ast_guardrail_passed: bool = True
    guardrail_violation_reason: Optional[str] = None
    semantic_routing: Optional[SemanticRoutingResult] = None


class SelfHealingSQLExecutor:
    """
    Manages guarded execution and self-healing retries for product queries.
    """

    def __init__(
        self,
        database_url: str = "sqlite:///pulsesql_edtech.db",
        max_healing_attempts: int = 2,
        router: Optional[SemanticMetricRouter] = None,
        synthesizer: Optional[SQLSynthesizer] = None,
    ):
        self.database_url = database_url
        self.max_healing_attempts = max_healing_attempts
        self.database_engine = create_engine(database_url)

        # Detect dialect
        dialect_name = self.database_engine.dialect.name
        self.router = router or SemanticMetricRouter()
        self.synthesizer = synthesizer or SQLSynthesizer(database_dialect=dialect_name)

    def execute_analytical_query(
        self,
        user_natural_query: str,
        injected_sql_override: Optional[str] = None,
    ) -> ExecutionCycleResult:
        """
        Executes a natural language query through the semantic router,
        SQL synthesizer, AST guardrail firewall, and self-healing execution loop.
        """
        start_execution_timestamp = time.perf_counter()

        # Step 1: Semantic Routing
        routing_decision = self.router.route_query_to_metric(user_natural_query)

        # Step 2: Initial SQL Synthesis
        if injected_sql_override:
            draft_sql = injected_sql_override
        else:
            draft_sql = self.synthesizer.synthesize_sql(
                user_natural_query=user_natural_query,
                routing_decision=routing_decision,
            )

        # Step 3: AST Guardrail Verification
        is_guardrail_valid, guardrail_message = verify_readonly_ast(draft_sql)
        if not is_guardrail_valid:
            elapsed_ms = (time.perf_counter() - start_execution_timestamp) * 1000.0
            return ExecutionCycleResult(
                query_result_dataframe=pd.DataFrame(),
                executed_sql=draft_sql,
                initial_execution_passed=False,
                healed_execution_passed=False,
                healing_iterations_used=0,
                execution_latency_ms=elapsed_ms,
                error_traces=[f"Guardrail Blocked: {guardrail_message}"],
                ast_guardrail_passed=False,
                guardrail_violation_reason=guardrail_message,
                semantic_routing=routing_decision,
            )

        # Step 4: Execution & Self-Healing Loop
        current_sql = draft_sql
        captured_error_traces: List[str] = []
        initial_passed = False
        healed_passed = False
        iterations_used = 0

        for attempt_number in range(self.max_healing_attempts + 1):
            try:
                with self.database_engine.connect() as db_connection:
                    executed_result = db_connection.execute(text(current_sql))
                    fetched_rows = executed_result.fetchall()
                    column_names = list(executed_result.keys())

                query_dataframe = pd.DataFrame(fetched_rows, columns=column_names)
                elapsed_execution_ms = (time.perf_counter() - start_execution_timestamp) * 1000.0

                if attempt_number == 0:
                    initial_passed = True
                    healed_passed = True
                else:
                    initial_passed = False
                    healed_passed = True

                return ExecutionCycleResult(
                    query_result_dataframe=query_dataframe,
                    executed_sql=current_sql,
                    initial_execution_passed=initial_passed,
                    healed_execution_passed=healed_passed,
                    healing_iterations_used=iterations_used,
                    execution_latency_ms=elapsed_execution_ms,
                    error_traces=captured_error_traces,
                    ast_guardrail_passed=True,
                    semantic_routing=routing_decision,
                )

            except (OperationalError, ProgrammingError, DBAPIError, Exception) as database_exception:
                error_diagnostic_string = str(database_exception)
                captured_error_traces.append(f"Attempt {attempt_number + 1} Failed: {error_diagnostic_string}")

                # If attempts exhausted, break and return failure
                if attempt_number >= self.max_healing_attempts:
                    break

                # Self-Healing Iteration
                iterations_used += 1
                try:
                    repaired_sql = self.synthesizer.synthesize_sql(
                        user_natural_query=user_natural_query,
                        routing_decision=routing_decision,
                        repair_context=f"Failed SQL: {current_sql}\nError Traceback: {error_diagnostic_string}",
                    )
                    # Verify repaired SQL guardrail
                    is_repaired_safe, repaired_guardrail_msg = verify_readonly_ast(repaired_sql)
                    if not is_repaired_safe:
                        captured_error_traces.append(f"Healed SQL Guardrail Rejected: {repaired_guardrail_msg}")
                        break
                    current_sql = repaired_sql
                except Exception as repair_exception:
                    captured_error_traces.append(f"Repair synthesis failed: {str(repair_exception)}")
                    break

        elapsed_failure_ms = (time.perf_counter() - start_execution_timestamp) * 1000.0
        return ExecutionCycleResult(
            query_result_dataframe=pd.DataFrame(),
            executed_sql=current_sql,
            initial_execution_passed=False,
            healed_execution_passed=False,
            healing_iterations_used=iterations_used,
            execution_latency_ms=elapsed_failure_ms,
            error_traces=captured_error_traces,
            ast_guardrail_passed=True,
            semantic_routing=routing_decision,
        )
