"""
PulseSQL 3-Pane Analytics Dashboard UI
======================================
Left Pane:   Semantic Metric Catalog (Canonical Definitions & Formulas)
Center Pane: Conversational Query Input + Plotly Visualizer + Verified SQL Pill
Right Pane:  One-Click Automated Root-Cause Analysis (RCA) Drawer
"""

import os
import sys
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Ensure repository root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from database.seed_synthetic_edtech_data import (
    populate_edtech_database,
    resolve_database_url,
)
from engine.rca_anomaly_slicer import RCAAnomalySlicer
from engine.self_healing_executor import SelfHealingSQLExecutor
from engine.semantic_router import SemanticMetricRouter
from engine.sql_synthesizer import SQLSynthesizer
from sqlalchemy import create_engine, text

# Page Configuration
st.set_page_config(
    page_title="PulseSQL: AI Product Analytics & Cohort Copilot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for Enterprise Analytics Cockpit
st.markdown(
    """
    <style>
    .main-header {
        font-size: 26px;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 2px;
    }
    .sub-header {
        font-size: 14px;
        color: #475569;
        margin-bottom: 16px;
    }
    .metric-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .pill-green { background-color: #DCFCE7; color: #166534; }
    .pill-blue { background-color: #DBEAFE; color: #1E40AF; }
    .pill-amber { background-color: #FEF3C7; color: #92400E; }
    .pill-red { background-color: #FEE2E2; color: #991B1B; }
    .sql-box {
        background-color: #0F172A;
        color: #E2E8F0;
        padding: 12px;
        border-radius: 8px;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        margin-top: 10px;
    }
    .rca-card {
        background-color: #FFF7ED;
        border-left: 4px solid #EA580C;
        padding: 12px;
        border-radius: 6px;
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine_instances():
    """Initializes and caches singleton engine instances."""
    db_url = resolve_database_url()
    db_engine = create_engine(db_url)

    # Auto-seed if database is empty
    try:
        with db_engine.connect() as check_conn:
            learner_count = check_conn.execute(text("SELECT COUNT(*) FROM learners;")).scalar()
            if not learner_count or learner_count < 100:
                schema_path = os.path.join(ROOT_DIR, "database", "schema.sql")
                populate_edtech_database(db_engine, schema_path)
    except Exception:
        schema_path = os.path.join(ROOT_DIR, "database", "schema.sql")
        populate_edtech_database(db_engine, schema_path)

    router = SemanticMetricRouter()
    synthesizer = SQLSynthesizer(database_dialect="sqlite")
    executor = SelfHealingSQLExecutor(
        database_url=db_url,
        max_healing_attempts=2,
        router=router,
        synthesizer=synthesizer,
    )
    slicer = RCAAnomalySlicer(database_url=db_url)
    return router, executor, slicer, db_url


router_inst, executor_inst, slicer_inst, current_db_url = get_engine_instances()

# --- TOP NAVIGATION BAR ---
col_logo, col_badges = st.columns([6, 4])
with col_logo:
    st.markdown('<div class="main-header">⚡ PulseSQL: AI Product Analytics & Cohort Copilot</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Zero-Data-Wait Natural Language Analytics • YAML Semantic Layer • Self-Healing SQL • One-Click RCA</div>', unsafe_allow_html=True)

with col_badges:
    st.markdown(
        f"""
        <div style="text-align: right; margin-top: 8px;">
            <span class="metric-pill pill-blue">Database: SQLite Local (Zero-Config)</span>
            <span class="metric-pill pill-green">Firewall: Read-Only AST (100% Guarded)</span>
            <span class="metric-pill pill-amber">Self-Healing: Max 2 Retries</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()

# --- 3-PANE LAYOUT ---
# Left Pane: 2.8, Center Pane: 5.6, Right Pane: 3.6
left_col, center_col, right_col = st.columns([2.8, 5.6, 3.6], gap="medium")


# ==============================================================================
# PANE 1: SEMANTIC METRIC CATALOG (LEFT)
# ==============================================================================
with left_col:
    st.subheader("📚 Semantic Catalog")
    st.caption("Canonical YAML Metric Dictionary (single source of truth).")

    metric_search_term = st.text_input("🔍 Search canonical metrics...", placeholder="Filter by name, synonym...").lower()

    canonical_metrics = router_inst.list_all_canonical_metrics()
    filtered_metrics = [
        m for m in canonical_metrics
        if metric_search_term in m["title"].lower() or metric_search_term in m["description"].lower() or any(metric_search_term in s.lower() for s in m["synonyms"])
    ] if metric_search_term else canonical_metrics

    for metric_item in filtered_metrics:
        with st.expander(f"**{metric_item['title']}**", expanded=(metric_item["metric_id"] == "mock_exam_completion_funnel")):
            st.markdown(f"**Category:** `{metric_item['category']}`")
            st.markdown(f"**Definition:** {metric_item['description']}")
            st.markdown("**Synonyms:** " + ", ".join([f"`{syn}`" for syn in metric_item["synonyms"]]))

            st.caption("Canonical SQL Formula:")
            st.code(metric_item["sql_formula"], language="sql")

            if st.button(f"Load '{metric_item['metric_id']}' Query", key=f"btn_{metric_item['metric_id']}"):
                if metric_item["metric_id"] == "mock_exam_completion_funnel":
                    st.session_state["active_query_text"] = "Show mock exam completion funnel in the last 7 days"
                elif metric_item["metric_id"] == "daily_active_learners":
                    st.session_state["active_query_text"] = "What is our Daily Active Learners count for each day over the last 7 days?"
                elif metric_item["metric_id"] == "d7_cohort_retention":
                    st.session_state["active_query_text"] = "Calculate D7 cohort retention rate for all signup dates"
                elif metric_item["metric_id"] == "paid_conversion_rate":
                    st.session_state["active_query_text"] = "Paid subscription conversion rate broken down by acquisition channel"
                elif metric_item["metric_id"] == "net_revenue_by_channel":
                    st.session_state["active_query_text"] = "Show total recognized revenue and completed orders by acquisition channel"
                elif metric_item["metric_id"] == "ai_doubt_resolution_rate":
                    st.session_state["active_query_text"] = "Average AI doubt solver response latency and satisfaction rating"
                st.rerun()


# ==============================================================================
# PANE 2: CONVERSATIONAL QUERY & VISUALIZATION (CENTER)
# ==============================================================================
with center_col:
    st.subheader("💬 Product Copilot & Visualizer")

    sample_questions_list = [
        "Show mock exam completion funnel in the last 7 days",
        "Calculate D7 cohort retention rate for all signup dates",
        "What is our Daily Active Learners count for each day over the last 7 days?",
        "Daily Active Learners grouped by device OS in the past 7 days",
        "Show total recognized revenue and completed orders by acquisition channel",
        "Paid subscription conversion rate broken down by acquisition channel",
        "Average session latency in milliseconds for each app version",
        "Average AI doubt solver response latency and satisfaction rating",
        "Adversarial Test: DELETE FROM learners WHERE learner_id = 'test';",
    ]

    selected_sample = st.selectbox("💡 Sample PM Analytics Questions:", ["-- Select a sample query --"] + sample_questions_list)
    if selected_sample != "-- Select a sample query --":
        st.session_state["active_query_text"] = selected_sample

    current_query_input = st.text_area(
        "Ask any product analytics question (Funnel, Cohort, Retention, Revenue):",
        value=st.session_state.get("active_query_text", "Show mock exam completion funnel in the last 7 days"),
        height=70,
    )

    query_trigger_button = st.button("🚀 Execute Guarded Analytics Query", type="primary", use_container_width=True)

    if query_trigger_button or "last_query_result" in st.session_state:
        if query_trigger_button:
            with st.spinner("Synthesizing and executing guarded SQL..."):
                query_execution_result = executor_inst.execute_analytical_query(current_query_input)
                st.session_state["last_query_result"] = query_execution_result
        else:
            query_execution_result = st.session_state["last_query_result"]

        # Ambiguity Notice
        routing_info = query_execution_result.semantic_routing
        if routing_info and routing_info.is_ambiguous:
            st.warning(f"⚠️ **Semantic Ambiguity Detected:** {routing_info.ambiguity_clarification_prompt}")

        # Guardrail Rejection Notice
        if not query_execution_result.ast_guardrail_passed:
            st.error(f"🛑 **AST Security Firewall Blocked Query:** {query_execution_result.guardrail_violation_reason}")
            st.code(query_execution_result.executed_sql, language="sql")
        else:
            # Status Strip
            status_chip = "pill-green" if query_execution_result.initial_execution_passed else "pill-amber"
            status_text = "PASSED (1st ATTEMPT)" if query_execution_result.initial_execution_passed else f"SELF-HEALED ({query_execution_result.healing_iterations_used} retry)"

            st.markdown(
                f"""
                <div>
                    <span class="metric-pill {status_chip}">Execution: {status_text}</span>
                    <span class="metric-pill pill-blue">Latency: {query_execution_result.execution_latency_ms:.1f}ms</span>
                    <span class="metric-pill pill-green">AST Guardrail: READ-ONLY VALIDATED</span>
                    <span class="metric-pill pill-blue">Rows: {len(query_execution_result.query_result_dataframe)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            result_df = query_execution_result.query_result_dataframe

            if not result_df.empty:
                # Plotly Visualizer
                columns_list = list(result_df.columns)

                # Case 1: Funnel Chart
                if "funnel_step" in columns_list and "unique_learners" in columns_list:
                    sorted_funnel_df = result_df.sort_values(by="step_order" if "step_order" in columns_list else "unique_learners", ascending=True)
                    fig = go.Figure(
                        go.Funnel(
                            y=sorted_funnel_df["funnel_step"],
                            x=sorted_funnel_df["unique_learners"],
                            textinfo="value+percent previous+percent initial",
                            marker=dict(color=["#3B82F6", "#60A5FA", "#93C5FD"]),
                        )
                    )
                    fig.update_layout(title="Mock Exam Step-by-Step Conversion Funnel", margin=dict(l=20, r=20, t=40, b=20), height=320)
                    st.plotly_chart(fig, use_container_width=True)

                # Case 2: Time Series Chart
                elif "metric_date" in columns_list and "daily_active_learners" in columns_list:
                    if "device_os" in columns_list:
                        fig = px.line(
                            result_df,
                            x="metric_date",
                            y="daily_active_learners",
                            color="device_os",
                            title="Daily Active Learners (DAL) by Device OS",
                            markers=True,
                        )
                    elif "acquisition_channel" in columns_list:
                        fig = px.line(
                            result_df,
                            x="metric_date",
                            y="daily_active_learners",
                            color="acquisition_channel",
                            title="Daily Active Learners (DAL) by Channel",
                            markers=True,
                        )
                    else:
                        fig = px.area(
                            result_df,
                            x="metric_date",
                            y="daily_active_learners",
                            title="Daily Active Learners (DAL) Trend",
                        )
                    fig.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)

                # Case 3: Cohort Retention Table / Chart
                elif "cohort_date" in columns_list and "d7_retention_rate_pct" in columns_list:
                    fig = px.bar(
                        result_df.head(15),
                        x="cohort_date",
                        y="d7_retention_rate_pct",
                        title="D7 Cohort Retention Rate (%)",
                        color="d7_retention_rate_pct",
                        color_continuous_scale="Blues",
                    )
                    fig.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)

                # Case 4: Revenue or Channel Breakdown
                elif "acquisition_channel" in columns_list and ("total_revenue_inr" in columns_list or "paid_conversion_rate_pct" in columns_list):
                    val_col = "total_revenue_inr" if "total_revenue_inr" in columns_list else "paid_conversion_rate_pct"
                    title_text = "Net Revenue by Channel (INR)" if val_col == "total_revenue_inr" else "Paid Conversion Rate by Channel (%)"
                    fig = px.bar(
                        result_df,
                        x="acquisition_channel",
                        y=val_col,
                        title=title_text,
                        color=val_col,
                        color_continuous_scale="Viridis",
                    )
                    fig.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)

                # Case 5: Latency by version
                elif "app_version" in columns_list and "avg_latency_ms" in columns_list:
                    fig = px.bar(
                        result_df,
                        x="app_version",
                        y="avg_latency_ms",
                        title="Average Session Latency by App Version (ms)",
                        color="avg_latency_ms",
                        color_continuous_scale="Reds",
                    )
                    fig.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig, use_container_width=True)

                # Tabular Inspection
                st.dataframe(result_df, use_container_width=True, height=200)

            # Verified SQL Pill
            with st.expander("🛡️ Verified SQL & Execution Plan", expanded=False):
                st.code(query_execution_result.executed_sql, language="sql")
                if query_execution_result.error_traces:
                    st.caption("Self-Healing Diagnostic Trace:")
                    for trace in query_execution_result.error_traces:
                        st.text(trace)


# ==============================================================================
# PANE 3: ONE-CLICK ROOT-CAUSE ANALYSIS (RCA) DRAWER (RIGHT)
# ==============================================================================
with right_col:
    st.subheader("🔍 One-Click RCA Drawer")
    st.caption("Automated multi-dimensional decomposition across Device OS, App Version, and Acquisition Channel.")

    st.markdown(
        """
        <div class="rca-card">
            <strong>Target Investigation:</strong> <code>mock_exam_completion_funnel</code><br>
            <span style="font-size: 13px; color: #9A3412;">
            Comparing <strong>Last 7 Days (Test Window)</strong> against <strong>Previous 7 Days (Baseline)</strong>.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    execute_rca_button = st.button("🚨 Run Root-Cause Slice", type="secondary", use_container_width=True)

    # Execute on button click or default initial load
    if execute_rca_button or "cached_rca_report" not in st.session_state:
        with st.spinner("Decomposing dimensional slices and calculating deltas..."):
            rca_report = slicer_inst.execute_root_cause_analysis()
            st.session_state["cached_rca_report"] = rca_report
    else:
        rca_report = st.session_state["cached_rca_report"]

    # Top Culprit Callout Pill
    st.markdown(
        f"""
        <div style="background-color: #FEF2F2; border: 1px solid #F87171; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="font-size: 12px; font-weight: 700; color: #B91C1C; text-transform: uppercase;">Top Anomaly Culprit Identified</div>
            <div style="font-size: 18px; font-weight: 800; color: #7F1D1D; margin-top: 2px;">{rca_report.top_culprit_segment}</div>
            <div style="font-size: 12px; color: #991B1B; margin-top: 4px;">Overall Funnel Delta: <strong>{rca_report.overall_delta_pct}%</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Executive Diagnostic Bullets
    st.markdown("##### 📌 Diagnostic Findings")
    for bullet_text in rca_report.executive_diagnostic_bullets:
        st.markdown(f"- {bullet_text}")

    st.divider()

    # Dimension Breakdown Tabs
    st.markdown("##### 📊 Dimensional Breakdown Slices")
    tab_os, tab_version, tab_channel = st.tabs(["Device OS", "App Version", "Channel"])

    with tab_os:
        st.caption("Mock Exam Starts vs Submissions by Operating System:")
        os_display_df = rca_report.device_os_breakdown[
            ["device_os", "baseline_conversion_pct", "test_conversion_pct", "delta_pct"]
        ].rename(
            columns={
                "device_os": "Platform",
                "baseline_conversion_pct": "Baseline %",
                "test_conversion_pct": "Test %",
                "delta_pct": "Delta %",
            }
        )
        st.dataframe(os_display_df, use_container_width=True, hide_index=True)

        # Plotly OS Delta Chart
        fig_os = px.bar(
            rca_report.device_os_breakdown,
            x="device_os",
            y="delta_pct",
            title="Conversion Rate Delta by OS (%)",
            color="delta_pct",
            color_continuous_scale="RdBu",
        )
        fig_os.update_layout(height=240, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_os, use_container_width=True)

    with tab_version:
        st.caption("Conversion Delta & Latency by App Version:")
        version_display_df = rca_report.app_version_breakdown[
            ["app_version", "test_starts", "test_conversion_pct", "delta_pct", "avg_latency_ms"]
        ].rename(
            columns={
                "app_version": "Build",
                "test_starts": "Starts",
                "test_conversion_pct": "Test %",
                "delta_pct": "Delta %",
                "avg_latency_ms": "Avg Latency (ms)",
            }
        )
        st.dataframe(version_display_df, use_container_width=True, hide_index=True)

        fig_ver = px.scatter(
            rca_report.app_version_breakdown,
            x="avg_latency_ms",
            y="delta_pct",
            text="app_version",
            size="test_starts",
            title="Latency vs Conversion Delta by Version",
            color="delta_pct",
            color_continuous_scale="Reds_r",
        )
        fig_ver.update_traces(textposition="top center")
        fig_ver.update_layout(height=240, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_ver, use_container_width=True)

    with tab_channel:
        st.caption("Performance Across Marketing Acquisition Channels:")
        channel_display_df = rca_report.acquisition_channel_breakdown[
            ["acquisition_channel", "baseline_conversion_pct", "test_conversion_pct", "delta_pct"]
        ].rename(
            columns={
                "acquisition_channel": "Channel",
                "baseline_conversion_pct": "Baseline %",
                "test_conversion_pct": "Test %",
                "delta_pct": "Delta %",
            }
        )
        st.dataframe(channel_display_df, use_container_width=True, hide_index=True)
