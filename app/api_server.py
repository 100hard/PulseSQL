"""
PulseSQL FastAPI Backend Server
===============================
Provides RESTful APIs for natural language analytics query execution,
semantic metric catalog inspection, and automated Root-Cause Analysis (RCA).
"""

import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure repository root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from database.seed_synthetic_edtech_data import resolve_database_url
from engine.rca_anomaly_slicer import RCAAnomalySlicer
from engine.self_healing_executor import SelfHealingSQLExecutor
from engine.semantic_router import SemanticMetricRouter
from engine.sql_synthesizer import SQLSynthesizer

app = FastAPI(
    title="PulseSQL: AI Product Analytics & Cohort Copilot API",
    description="High-velocity Product Analytics Copilot with Semantic Layer, Self-Healing SQL, and One-Click RCA.",
    version="1.0.0",
)

# Enable CORS for dashboard and external consumers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Engine Singletons
database_connection_url = resolve_database_url()
semantic_metric_router = SemanticMetricRouter()
sql_query_synthesizer = SQLSynthesizer(database_dialect="sqlite")
self_healing_sql_executor = SelfHealingSQLExecutor(
    database_url=database_connection_url,
    max_healing_attempts=2,
    router=semantic_metric_router,
    synthesizer=sql_query_synthesizer,
)
rca_anomaly_slicer = RCAAnomalySlicer(database_url=database_connection_url)


# --- Request and Response Schemas ---

class AnalyticsQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language product analytics query", example="Show mock exam completion funnel in the last 7 days")
    sql_override: Optional[str] = Field(None, description="Optional explicit SQL override for testing")


class AnalyticsQueryResponse(BaseModel):
    canonical_metric_name: str
    display_title: str
    is_ambiguous: bool
    ambiguity_clarification_prompt: Optional[str] = None
    executed_sql: str
    initial_execution_passed: bool
    healed_execution_passed: bool
    healing_iterations_used: int
    execution_latency_ms: float
    row_count: int
    columns: List[str]
    rows: List[Dict[str, Any]]
    ast_guardrail_passed: bool
    guardrail_violation_reason: Optional[str] = None
    error_traces: List[str]


class RootCauseAnalysisRequest(BaseModel):
    target_metric: str = Field("mock_exam_completion_funnel", description="Target metric identifier")
    baseline_days: int = Field(7, description="Baseline comparison window in days")
    test_days: int = Field(7, description="Test period window in days")


class RootCauseAnalysisResponse(BaseModel):
    target_metric_name: str
    baseline_window_label: str
    test_window_label: str
    overall_baseline_conversion_pct: float
    overall_test_conversion_pct: float
    overall_delta_pct: float
    top_culprit_segment: str
    executive_diagnostic_bullets: List[str]
    device_os_breakdown: List[Dict[str, Any]]
    app_version_breakdown: List[Dict[str, Any]]
    acquisition_channel_breakdown: List[Dict[str, Any]]


class HealthStatusResponse(BaseModel):
    status: str
    database_connected: bool
    database_url_target: str
    version: str


# --- API Endpoints ---

@app.get("/health", response_model=HealthStatusResponse, tags=["System Health"])
def check_service_health() -> HealthStatusResponse:
    """Checks database connectivity and server health."""
    is_db_connected = False
    try:
        from sqlalchemy import text
        with self_healing_sql_executor.database_engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
            is_db_connected = True
    except Exception:
        is_db_connected = False

    return HealthStatusResponse(
        status="healthy" if is_db_connected else "degraded",
        database_connected=is_db_connected,
        database_url_target=database_connection_url,
        version="1.0.0",
    )


@app.get("/metrics-catalog", tags=["Semantic Layer"])
def retrieve_metrics_catalog() -> Dict[str, Any]:
    """Retrieves all registered canonical product metrics from YAML dictionary."""
    metrics_list = semantic_metric_router.list_all_canonical_metrics()
    return {
        "total_metrics": len(metrics_list),
        "domain": semantic_metric_router.semantic_metric_catalog.get("domain", "edtech"),
        "metrics": metrics_list,
    }


@app.post("/query", response_model=AnalyticsQueryResponse, tags=["Analytics Execution"])
def execute_natural_language_query(request: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
    """
    Routes user query through semantic layer, synthesizes guarded SQL,
    and executes via self-healing loop.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter cannot be empty.",
        )

    execution_result = self_healing_sql_executor.execute_analytical_query(
        user_natural_query=request.query,
        injected_sql_override=request.sql_override,
    )

    result_dataframe = execution_result.query_result_dataframe
    column_names = list(result_dataframe.columns) if not result_dataframe.empty else []
    data_rows = result_dataframe.to_dict(orient="records") if not result_dataframe.empty else []

    routing_info = execution_result.semantic_routing

    return AnalyticsQueryResponse(
        canonical_metric_name=routing_info.canonical_metric_name if routing_info else "unknown",
        display_title=routing_info.display_title if routing_info else "Product Query",
        is_ambiguous=routing_info.is_ambiguous if routing_info else False,
        ambiguity_clarification_prompt=routing_info.ambiguity_clarification_prompt if routing_info else None,
        executed_sql=execution_result.executed_sql,
        initial_execution_passed=execution_result.initial_execution_passed,
        healed_execution_passed=execution_result.healed_execution_passed,
        healing_iterations_used=execution_result.healing_iterations_used,
        execution_latency_ms=round(execution_result.execution_latency_ms, 2),
        row_count=len(data_rows),
        columns=column_names,
        rows=data_rows,
        ast_guardrail_passed=execution_result.ast_guardrail_passed,
        guardrail_violation_reason=execution_result.guardrail_violation_reason,
        error_traces=execution_result.error_traces,
    )


@app.post("/rca-slice", response_model=RootCauseAnalysisResponse, tags=["Root Cause Analysis"])
def run_root_cause_slice(request: RootCauseAnalysisRequest) -> RootCauseAnalysisResponse:
    """
    Executes automated dimensional decomposition across device_os, app_version,
    and acquisition_channel to diagnose metric drop root cause.
    """
    try:
        diagnostic_report = rca_anomaly_slicer.execute_root_cause_analysis(
            target_metric=request.target_metric,
            baseline_days_window=request.baseline_days,
            test_days_window=request.test_days,
        )

        return RootCauseAnalysisResponse(
            target_metric_name=diagnostic_report.target_metric_name,
            baseline_window_label=diagnostic_report.baseline_window_label,
            test_window_label=diagnostic_report.test_window_label,
            overall_baseline_conversion_pct=diagnostic_report.overall_baseline_conversion_pct,
            overall_test_conversion_pct=diagnostic_report.overall_test_conversion_pct,
            overall_delta_pct=diagnostic_report.overall_delta_pct,
            top_culprit_segment=diagnostic_report.top_culprit_segment,
            executive_diagnostic_bullets=diagnostic_report.executive_diagnostic_bullets,
            device_os_breakdown=diagnostic_report.device_os_breakdown.to_dict(orient="records"),
            app_version_breakdown=diagnostic_report.app_version_breakdown.to_dict(orient="records"),
            acquisition_channel_breakdown=diagnostic_report.acquisition_channel_breakdown.to_dict(orient="records"),
        )
    except Exception as rca_exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Root Cause Analysis failed: {str(rca_exception)}",
        )


if __name__ == "__main__":
    import uvicorn

    server_host = os.getenv("API_HOST", "0.0.0.0")
    server_port = int(os.getenv("API_PORT", "8000"))
    print(f"Starting PulseSQL API Server on {server_host}:{server_port}...")
    uvicorn.run("api_server:app", host=server_host, port=server_port, reload=False)
