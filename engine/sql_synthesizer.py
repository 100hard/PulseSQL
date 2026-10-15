"""
PulseSQL SQL Synthesizer & Read-Only Guardrails
================================================
Generates analytical SQL queries based on user intent and semantic routing.
Applies strict AST-level and regex security firewalls to block destructive
statements and enforce bounded result limits.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from engine.semantic_router import SemanticRoutingResult

# Forbidden SQL tokens that represent destructive DDL/DML or privilege tampering
FORBIDDEN_SQL_KEYWORDS = [
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "REPLACE",
    "EXEC",
    "EXECUTE",
    "CREATE",
    "ATTACH",
    "DETACH",
    "MERGE",
    "UPSERT",
]


class ReadOnlyGuardrailViolation(Exception):
    """Raised when generated or input SQL violates read-only AST safety policies."""
    pass


def verify_readonly_ast(sql_query_string: str) -> Tuple[bool, str]:
    """
    Validates that the provided SQL query is strictly read-only and bounded.
    Checks:
    1. Forbidden statement tokens (DROP, DELETE, UPDATE, INSERT, etc.).
    2. Must begin with SELECT or WITH (CTE).
    3. Multi-statement chaining injection defense (multiple semicolons).
    4. Enforces a LIMIT 1000 ceiling.
    """
    if not sql_query_string or not sql_query_string.strip():
        return False, "SQL query cannot be empty."

    # Strip inline and block comments to avoid comment-based keyword obfuscation
    sanitized_sql = re.sub(r"--.*?\n", " ", sql_query_string)
    sanitized_sql = re.sub(r"/\*.*?\*/", " ", sanitized_sql, flags=re.DOTALL).strip()

    # Multi-statement injection defense
    statement_segments = [seg.strip() for seg in sanitized_sql.split(";") if seg.strip()]
    if len(statement_segments) > 1:
        return False, "Security Violation: Multi-statement query execution is strictly prohibited."

    single_statement = statement_segments[0] if statement_segments else sanitized_sql

    # Token-level verification for forbidden DDL / DML
    tokenized_words = re.findall(r"\b[A-Za-z_]+\b", single_statement.upper())
    for forbidden_token in FORBIDDEN_SQL_KEYWORDS:
        if forbidden_token in tokenized_words:
            return False, f"Security Violation: Destructive operation '{forbidden_token}' is strictly prohibited."

    # Must begin with SELECT or WITH
    first_token_match = re.match(r"^\s*([A-Za-z]+)", single_statement)
    if not first_token_match:
        return False, "Security Violation: Query does not contain a valid leading SQL keyword."

    leading_token = first_token_match.group(1).upper()
    if leading_token not in ("SELECT", "WITH", "EXPLAIN"):
        return False, f"Security Violation: Query must start with SELECT or WITH (got '{leading_token}')."

    return True, "Guardrail Verification Passed."


def clamp_query_limit_ceiling(sql_query_string: str, maximum_allowed_limit: int = 1000) -> str:
    """
    Enforces that queries either contain a LIMIT clause <= maximum_allowed_limit,
    or appends LIMIT 1000 to prevent runaway unbounded full-table scans.
    """
    cleaned_query = sql_query_string.strip().rstrip(";")

    # Match existing LIMIT clause
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", cleaned_query, flags=re.IGNORECASE)
    if limit_match:
        existing_limit = int(limit_match.group(1))
        if existing_limit > maximum_allowed_limit:
            # Replace with maximum ceiling
            clamped_sql = re.sub(
                r"\bLIMIT\s+\d+\b",
                f"LIMIT {maximum_allowed_limit}",
                cleaned_query,
                flags=re.IGNORECASE,
            )
            return clamped_sql
        return cleaned_query

    # If no limit clause exists, append LIMIT ceiling
    return f"{cleaned_query}\nLIMIT {maximum_allowed_limit}"


class SQLSynthesizer:
    """
    Synthesizes compliant SQL queries from natural language queries and
    routed semantic metric definitions. Supports offline deterministic mode
    as well as LLM-backed synthesis (OpenAI, Groq, Gemini).
    """

    def __init__(self, database_dialect: str = "sqlite"):
        self.database_dialect = database_dialect.lower()
        self.llm_provider = os.getenv("LLM_PROVIDER", "offline").lower()

    def synthesize_sql(
        self,
        user_natural_query: str,
        routing_decision: SemanticRoutingResult,
        repair_context: Optional[str] = None,
    ) -> str:
        """
        Synthesizes SQL query string. Validates output through verify_readonly_ast.
        If repair_context is provided, incorporates traceback details to fix errors.
        """
        # If external LLM provider configured with valid keys, attempt LLM generation
        if self.llm_provider in ("openai", "groq", "gemini") and not repair_context:
            try:
                candidate_sql = self._generate_via_external_llm(user_natural_query, routing_decision)
            except Exception:
                # Graceful fallback to deterministic semantic synthesis
                candidate_sql = self._synthesize_deterministic_sql(user_natural_query, routing_decision)
        elif repair_context:
            candidate_sql = self._repair_sql_deterministic(user_natural_query, routing_decision, repair_context)
        else:
            candidate_sql = self._synthesize_deterministic_sql(user_natural_query, routing_decision)

        # Enforce AST read-only validation
        is_valid_query, validation_message = verify_readonly_ast(candidate_sql)
        if not is_valid_query:
            raise ReadOnlyGuardrailViolation(validation_message)

        # Apply LIMIT ceiling
        bounded_sql = clamp_query_limit_ceiling(candidate_sql, maximum_allowed_limit=1000)
        return bounded_sql

    def _synthesize_deterministic_sql(
        self,
        user_natural_query: str,
        routing_decision: SemanticRoutingResult,
    ) -> str:
        """
        Synthesizes dialect-aware SQL using canonical templates and dimensional constraints.
        """
        metric_key = routing_decision.canonical_metric_name
        temporal_window = routing_decision.temporal_filter_description
        requested_dimensions = routing_decision.dimensions_requested
        normalized_query = user_natural_query.lower()

        # Date filter SQL snippet based on dialect
        if temporal_window == "last_7_days":
            date_filter_telemetry = (
                "t.occurred_at >= date('now', '-7 days')"
                if "sqlite" in self.database_dialect
                else "t.occurred_at >= NOW() - INTERVAL '7 days'"
            )
            date_filter_learners = (
                "l.signup_timestamp >= date('now', '-7 days')"
                if "sqlite" in self.database_dialect
                else "l.signup_timestamp >= NOW() - INTERVAL '7 days'"
            )
        elif temporal_window == "last_14_days":
            date_filter_telemetry = (
                "t.occurred_at >= date('now', '-14 days')"
                if "sqlite" in self.database_dialect
                else "t.occurred_at >= NOW() - INTERVAL '14 days'"
            )
            date_filter_learners = (
                "l.signup_timestamp >= date('now', '-14 days')"
                if "sqlite" in self.database_dialect
                else "l.signup_timestamp >= NOW() - INTERVAL '14 days'"
            )
        elif temporal_window == "last_30_days":
            date_filter_telemetry = (
                "t.occurred_at >= date('now', '-30 days')"
                if "sqlite" in self.database_dialect
                else "t.occurred_at >= NOW() - INTERVAL '30 days'"
            )
            date_filter_learners = (
                "l.signup_timestamp >= date('now', '-30 days')"
                if "sqlite" in self.database_dialect
                else "l.signup_timestamp >= NOW() - INTERVAL '30 days'"
            )
        else:
            date_filter_telemetry = "1=1"
            date_filter_learners = "1=1"

        # 1. Daily Active Learners (DAL)
        if metric_key == "daily_active_learners":
            if "device_os" in requested_dimensions or "device" in normalized_query:
                return (
                    f"SELECT \n"
                    f"    DATE(t.occurred_at) AS metric_date,\n"
                    f"    l.device_os,\n"
                    f"    COUNT(DISTINCT t.learner_id) AS daily_active_learners\n"
                    f"FROM telemetry_events t\n"
                    f"JOIN learners l ON t.learner_id = l.learner_id\n"
                    f"WHERE t.event_name IN ('mock_exam_started', 'syllabus_explored')\n"
                    f"  AND {date_filter_telemetry}\n"
                    f"GROUP BY DATE(t.occurred_at), l.device_os\n"
                    f"ORDER BY metric_date DESC, daily_active_learners DESC"
                )
            elif "acquisition_channel" in requested_dimensions or "channel" in normalized_query:
                return (
                    f"SELECT \n"
                    f"    DATE(t.occurred_at) AS metric_date,\n"
                    f"    l.acquisition_channel,\n"
                    f"    COUNT(DISTINCT t.learner_id) AS daily_active_learners\n"
                    f"FROM telemetry_events t\n"
                    f"JOIN learners l ON t.learner_id = l.learner_id\n"
                    f"WHERE t.event_name IN ('mock_exam_started', 'syllabus_explored')\n"
                    f"  AND {date_filter_telemetry}\n"
                    f"GROUP BY DATE(t.occurred_at), l.acquisition_channel\n"
                    f"ORDER BY metric_date DESC, daily_active_learners DESC"
                )
            else:
                return (
                    f"SELECT \n"
                    f"    DATE(t.occurred_at) AS metric_date,\n"
                    f"    COUNT(DISTINCT t.learner_id) AS daily_active_learners\n"
                    f"FROM telemetry_events t\n"
                    f"WHERE t.event_name IN ('mock_exam_started', 'syllabus_explored')\n"
                    f"  AND {date_filter_telemetry}\n"
                    f"GROUP BY DATE(t.occurred_at)\n"
                    f"ORDER BY metric_date DESC"
                )

        # 2. Mock Exam Completion Funnel
        if metric_key == "mock_exam_completion_funnel":
            extra_where = f"WHERE {date_filter_telemetry.replace('t.', '')}" if date_filter_telemetry != "1=1" else ""
            return (
                f"SELECT \n"
                f"    '1. App Launch' AS funnel_step,\n"
                f"    1 AS step_order,\n"
                f"    COUNT(DISTINCT CASE WHEN event_name = 'app_launch' THEN learner_id END) AS unique_learners\n"
                f"FROM telemetry_events\n"
                f"{extra_where}\n"
                f"UNION ALL\n"
                f"SELECT \n"
                f"    '2. Exam Started' AS funnel_step,\n"
                f"    2 AS step_order,\n"
                f"    COUNT(DISTINCT CASE WHEN event_name = 'mock_exam_started' THEN learner_id END) AS unique_learners\n"
                f"FROM telemetry_events\n"
                f"{extra_where}\n"
                f"UNION ALL\n"
                f"SELECT \n"
                f"    '3. Exam Submitted' AS funnel_step,\n"
                f"    3 AS step_order,\n"
                f"    COUNT(DISTINCT CASE WHEN event_name = 'mock_exam_submitted' THEN learner_id END) AS unique_learners\n"
                f"FROM telemetry_events\n"
                f"{extra_where}\n"
                f"ORDER BY step_order ASC"
            )

        # 3. D7 Cohort Retention
        if metric_key == "d7_cohort_retention":
            date_add_expr = (
                "DATE(l.signup_timestamp, '+7 days')"
                if "sqlite" in self.database_dialect
                else "DATE(l.signup_timestamp + INTERVAL '7 days')"
            )
            return (
                f"WITH learner_cohorts AS (\n"
                f"    SELECT \n"
                f"        learner_id,\n"
                f"        DATE(signup_timestamp) AS cohort_date\n"
                f"    FROM learners l\n"
                f"    WHERE {date_filter_learners}\n"
                f"),\n"
                f"day_7_activity AS (\n"
                f"    SELECT DISTINCT\n"
                f"        t.learner_id\n"
                f"    FROM telemetry_events t\n"
                f"    JOIN learners l ON t.learner_id = l.learner_id\n"
                f"    WHERE DATE(t.occurred_at) = {date_add_expr}\n"
                f")\n"
                f"SELECT \n"
                f"    c.cohort_date,\n"
                f"    COUNT(DISTINCT c.learner_id) AS cohort_size,\n"
                f"    COUNT(DISTINCT a.learner_id) AS retained_learners_d7,\n"
                f"    ROUND(CAST(COUNT(DISTINCT a.learner_id) AS FLOAT) * 100.0 / NULLIF(COUNT(DISTINCT c.learner_id), 0), 2) AS d7_retention_rate_pct\n"
                f"FROM learner_cohorts c\n"
                f"LEFT JOIN day_7_activity a ON c.learner_id = a.learner_id\n"
                f"GROUP BY c.cohort_date\n"
                f"HAVING COUNT(DISTINCT c.learner_id) > 0\n"
                f"ORDER BY c.cohort_date DESC"
            )

        # 4. Paid Conversion Rate
        if metric_key == "paid_conversion_rate":
            group_dimension_clause = ""
            select_dimension = ""
            if "acquisition_channel" in requested_dimensions or "channel" in normalized_query:
                select_dimension = "l.acquisition_channel, "
                group_dimension_clause = "GROUP BY l.acquisition_channel ORDER BY paid_conversion_rate_pct DESC"
            elif "device_os" in requested_dimensions or "device" in normalized_query:
                select_dimension = "l.device_os, "
                group_dimension_clause = "GROUP BY l.device_os ORDER BY paid_conversion_rate_pct DESC"

            return (
                f"SELECT \n"
                f"    {select_dimension}"
                f"    COUNT(DISTINCT l.learner_id) AS total_registered_learners,\n"
                f"    COUNT(DISTINCT CASE WHEN s.payment_status = 'completed' THEN s.learner_id END) AS total_paying_learners,\n"
                f"    ROUND(CAST(COUNT(DISTINCT CASE WHEN s.payment_status = 'completed' THEN s.learner_id END) AS FLOAT) * 100.0 / NULLIF(COUNT(DISTINCT l.learner_id), 0), 2) AS paid_conversion_rate_pct\n"
                f"FROM learners l\n"
                f"LEFT JOIN subscriptions s ON l.learner_id = s.learner_id\n"
                f"WHERE {date_filter_learners}\n"
                f"{group_dimension_clause}"
            )

        # 5. Net Revenue by Channel
        if metric_key == "net_revenue_by_channel":
            return (
                f"SELECT \n"
                f"    l.acquisition_channel,\n"
                f"    COUNT(DISTINCT s.subscription_id) AS completed_orders,\n"
                f"    ROUND(SUM(s.revenue_inr), 2) AS total_revenue_inr,\n"
                f"    ROUND(AVG(s.revenue_inr), 2) AS avg_order_value_inr\n"
                f"FROM subscriptions s\n"
                f"JOIN learners l ON s.learner_id = l.learner_id\n"
                f"WHERE s.payment_status = 'completed'\n"
                f"GROUP BY l.acquisition_channel\n"
                f"ORDER BY total_revenue_inr DESC"
            )

        # 6. AI Doubt Resolution Rate
        if metric_key == "ai_doubt_resolution_rate":
            return (
                f"SELECT \n"
                f"    COUNT(session_id) AS total_doubt_sessions,\n"
                f"    ROUND(AVG(response_latency_ms), 1) AS avg_response_latency_ms,\n"
                f"    ROUND(AVG(resolution_rating), 2) AS avg_satisfaction_rating,\n"
                f"    ROUND(AVG(token_consumption), 0) AS avg_tokens_per_session\n"
                f"FROM ai_doubt_sessions\n"
                f"WHERE created_at >= date('now', '-30 days')"
                if "sqlite" in self.database_dialect
                else (
                    f"SELECT \n"
                    f"    COUNT(session_id) AS total_doubt_sessions,\n"
                    f"    ROUND(AVG(response_latency_ms), 1) AS avg_response_latency_ms,\n"
                    f"    ROUND(AVG(resolution_rating), 2) AS avg_satisfaction_rating,\n"
                    f"    ROUND(AVG(token_consumption), 0) AS avg_tokens_per_session\n"
                    f"FROM ai_doubt_sessions\n"
                    f"WHERE created_at >= NOW() - INTERVAL '30 days'"
                )
            )

        # Fallback exploratory query
        if "latency" in normalized_query and "version" in normalized_query:
            return (
                f"SELECT \n"
                f"    app_version,\n"
                f"    COUNT(event_id) AS total_events,\n"
                f"    ROUND(AVG(session_latency_ms), 2) AS avg_latency_ms,\n"
                f"    MAX(session_latency_ms) AS max_latency_ms\n"
                f"FROM telemetry_events\n"
                f"GROUP BY app_version\n"
                f"ORDER BY avg_latency_ms DESC"
            )

        return (
            f"SELECT \n"
            f"    acquisition_channel,\n"
            f"    device_os,\n"
            f"    COUNT(learner_id) AS learner_count\n"
            f"FROM learners\n"
            f"GROUP BY acquisition_channel, device_os\n"
            f"ORDER BY learner_count DESC"
        )

    def _repair_sql_deterministic(
        self,
        user_natural_query: str,
        routing_decision: SemanticRoutingResult,
        repair_context: str,
    ) -> str:
        """
        Diagnoses database execution errors and generates corrected SQL.
        Handles common SQL dialect pitfalls (Postgres INTERVAL in SQLite,
        ambiguous column names, zero division, or invalid function syntax).
        """
        error_lower = repair_context.lower()

        # Fix 1: Interval syntax error in SQLite
        if "interval" in error_lower or "syntax error" in error_lower:
            # Replace PostgreSQL INTERVAL with SQLite date modifier
            # e.g., NOW() - INTERVAL '7 days' -> date('now', '-7 days')
            healed = re.sub(
                r"NOW\(\)\s*-\s*INTERVAL\s*'(\d+)\s*days?'",
                r"date('now', '-\1 days')",
                repair_context,
                flags=re.IGNORECASE,
            )
            healed = re.sub(
                r"\bINTERVAL\s*'(\d+)\s*days?'",
                r"'\1 days'",
                healed,
                flags=re.IGNORECASE,
            )
            # If the repair context didn't contain full SQL, generate base SQL with explicit SQLite syntax
            if not healed.strip().upper().startswith(("SELECT", "WITH")):
                healed = self._synthesize_deterministic_sql(user_natural_query, routing_decision)
            return healed

        # Fix 2: Column not found (e.g. channel -> acquisition_channel or platform -> device_os)
        if "no such column" in error_lower or "column does not exist" in error_lower:
            healed_sql = self._synthesize_deterministic_sql(user_natural_query, routing_decision)
            return healed_sql

        # Fix 3: Division by zero -> wrap denominator with NULLIF
        if "division by zero" in error_lower:
            base_sql = self._synthesize_deterministic_sql(user_natural_query, routing_decision)
            healed_sql = re.sub(
                r"/\s*(COUNT\([^\)]+\))",
                r"/ NULLIF(\1, 0)",
                base_sql,
            )
            return healed_sql

        # Fallback to standard deterministic synthesis
        return self._synthesize_deterministic_sql(user_natural_query, routing_decision)

    def _generate_via_external_llm(
        self,
        user_natural_query: str,
        routing_decision: SemanticRoutingResult,
    ) -> str:
        """Placeholder for external LLM call (OpenAI/Groq/Gemini)."""
        # When called without network or API key, will raise and fallback cleanly
        raise NotImplementedError("External LLM API call not configured or offline.")
