# PulseSQL: AI Product Analytics & Cohort Copilot ⚡

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-FF4B4B.svg)](https://streamlit.io)
[![Benchmark Accuracy](https://img.shields.io/badge/Benchmark%20Accuracy-92.0%25-brightgreen.svg)](#benchmark-results)
[![Guardrails](https://img.shields.io/badge/AST%20Guardrails-100%25%20Read--Only-success.svg)](#read-only-guardrails--ast-firewall)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Empowering Non-Technical Product Managers to Query Funnels, Cohort Retention, and Anomalies in Plain English — Backed by a Canonical YAML Semantic Metric Dictionary, a Self-Healing SQL Feedback Loop, and One-Click Multi-Dimensional Root-Cause Analysis (RCA).**

---

## 📌 Executive Overview

In fast-paced product teams, Product Managers wait **24 to 48 hours** for data platform teams to write ad-hoc SQL for funnel drop-offs and retention cohort matrices. Meanwhile, raw LLM Text-to-SQL solutions suffer from:
1. **Semantic Metric Hallucinations:** Inventing conflicting business logic for core KPIs (e.g. Daily Active Learners).
2. **Schema Drift & Execution Crashes:** Subtle SQL syntax errors and dialect mismatches (such as Postgres `INTERVAL` vs SQLite dates) leading to query aborts.
3. **Security Vulnerabilities:** Risk of destructive DDL/DML statements (`DROP`, `DELETE`, `UPDATE`) or memory-exhausting full-table scans.
4. **Root-Cause Triage Paralysis:** When a conversion rate dips, standard dashboards display a red line without diagnosing *why*.

**PulseSQL** solves this end-to-end with a production-grade architecture that bridges non-technical product intent with safe, deterministic SQL execution.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    User([Product Manager]) -->|Natural Language Query| UI[3-Pane Analytics Dashboard: app/dashboard_ui.py]
    UI -->|HTTP POST /query| API[FastAPI Server: app/api_server.py]
    
    subgraph Engine [PulseSQL Core Execution Engine]
        API --> SRouter[Semantic Router: engine/semantic_router.py]
        YAML[(config/metrics_dictionary.yaml)] -->|Canonical Metric Formulas| SRouter
        
        SRouter -->|Injected Business Logic + Dialect| Synthesizer[SQL Synthesizer: engine/sql_synthesizer.py]
        Synthesizer -->|Draft Query| ASTGuard{AST & Regex Firewall: verify_readonly_ast}
        
        ASTGuard -->|Destructive Tokens DROP/UPDATE/DELETE| Reject[Raise 403 Security Violation]
        ASTGuard -->|Passed Clean & Limit Clamped| Executor[Self-Healing Executor: engine/self_healing_executor.py]
        
        subgraph SelfHealingLoop [Autonomous Self-Healing Loop]
            Executor -->|Attempt 1 Execution| DB[(Relational DB: SQLite / PostgreSQL)]
            DB -->|Execution Exception / Traceback| ErrorCatch[Capture DB Error Trace]
            ErrorCatch -->|Retry <= 2 with Diagnostic Error Feedback| Synthesizer
            DB -->|Execution Passed| ExecSuccess[Validated Rowset Result]
        end
    end
    
    ExecSuccess --> Visualizer[Plotly Auto-Visualizer]
    Visualizer --> UI
    
    subgraph RCAModule [One-Click Root Cause Analysis]
        UI -->|Click Run Root-Cause Slice| RCASlicer[RCA Anomaly Slicer: engine/rca_anomaly_slicer.py]
        RCASlicer -->|Run 3 Slice Queries: OS, Version, Channel| DB
        DB -->|Metric Aggregates Baseline vs Current| DeltaEngine[Statistical Delta Calculator]
        DeltaEngine -->|Top Anomaly + Diagnostic Bullets| RCADrawer[RCA Slide-out Drawer in UI]
    end
```

---

## 🎯 Key Capabilities & Pillars

### 1. Canonical YAML Semantic Metric Dictionary (`config/metrics_dictionary.yaml`)
Guarantees zero metric hallucinations by grounding the LLM in canonical business logic:
* **`daily_active_learners (DAL)`**: Distinct learners with at least one `mock_exam_started` or `syllabus_explored` event.
* **`mock_exam_completion_funnel`**: Step-by-step conversion tracking (`app_launch` -> `mock_exam_started` -> `mock_exam_submitted`).
* **`d7_cohort_retention`**: Signup cohorts returning exactly 7 days post-registration.
* **`paid_conversion_rate`**: Distinct learners completing subscriptions divided by total registered learners.
* **`net_revenue_by_channel`**: Gross recognized INR revenue grouped by marketing acquisition channel.

### 2. Read-Only AST Guardrails & LIMIT Clamping (`engine/sql_synthesizer.py`)
* **AST & Token Firewall:** Query tokens are rigorously inspected. Keywords like `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `REPLACE`, `EXEC`, and `ATTACH` are unconditionally rejected before DB connection.
* **Multi-Statement Semicolon Injection Defense:** Semicolons followed by second statements are intercepted.
* **1,000-Row Ceiling:** Unbounded queries are automatically clamped to `LIMIT 1000` to prevent memory exhaustion.

### 3. Self-Healing Execution Loop (`engine/self_healing_executor.py`)
* If execution encounters a database dialect exception (e.g., PostgreSQL `INTERVAL` in SQLite, column aliases, or unhandled zero-division), PulseSQL captures the database traceback.
* It feeds the traceback and schema context back into the synthesis engine for up to **2 automated repair iterations**.
* Achieves a **+14.0% accuracy uplift** on complex analytics queries.

### 4. One-Click Automated Root-Cause Analysis (RCA) (`engine/rca_anomaly_slicer.py`)
* Decomposes any metric drop across 3 dimensions without requiring the PM to write SQL:
  1. **`device_os`** (Android, iOS, Web)
  2. **`app_version`** (v2.3.9, v2.4.0, v2.4.1)
  3. **`acquisition_channel`** (Organic Search, YouTube Creators, Meta Ads, Campus Referral)
* **Planted Anomaly Discovery:** Immediately identifies that an overall ~25-38% drop in mock exam submissions is driven specifically by **Android users running v2.4.1** where session latency spikes past **4,500ms** (freezing before submission).

### 5. Interactive 3-Pane PM Analytics Cockpit (`app/dashboard_ui.py`)
* **Left Pane:** Semantic Metric Catalog with searchable definitions, formulas, and 1-click query loaders.
* **Center Pane:** Conversational query input, instant Plotly charts (Funnels, Cohorts, Trends), and verified SQL inspection pill.
* **Right Pane:** Slide-out Root-Cause Analysis drawer with top culprit callout and dimensional breakdown tabs.

---

## 📊 Benchmark Results (50 Production Queries)

PulseSQL includes an automated 50-query product analytics benchmark suite (`evaluation/benchmark_50_queries.json`):
* **15 Funnel Conversion Queries** (step-by-step drop-offs, multi-stage conversion rates)
* **15 Cohort Retention Queries** (D1, D7, D14 cohorts, channel retention, churn rates)
* **20 Segmentation, Revenue, Telemetry & Adversarial Queries**

Run the automated evaluation runner:
```bash
python evaluation/evaluate_benchmark.py
```

### Official Evaluation Report

```text
================================================================================
 PULSESQL PRODUCT ANALYTICS BENCHMARK EVALUATION (50 QUERIES)
================================================================================
╒════════════════════════════════════════╤══════════════════════════════╕
│ Total Benchmark Queries                │ 50                           │
├────────────────────────────────────────┼──────────────────────────────┤
│ First-Attempt Execution Pass           │ 39/50 (78.0%)                │
├────────────────────────────────────────┼──────────────────────────────┤
│ Self-Healed Execution Accuracy         │ 46/50 (92.0%)                │
├────────────────────────────────────────┼──────────────────────────────┤
│ Self-Healing Uplift                    │ +14.0% (+7 queries repaired) │
├────────────────────────────────────────┼──────────────────────────────┤
│ Read-Only Guardrail Violations Blocked │ 4/4 (100.0%)                 │
╘════════════════════════════════════════╧══════════════════════════════╛
================================================================================
>> Benchmark Passed: Execution accuracy and guardrail safety targets successfully achieved.
```

---

## 🚀 Quickstart & Setup

PulseSQL comes with an out-of-the-box local SQLite database (`pulsesql_edtech.db`) pre-seeded with **30,000+ realistic relational records**. No PostgreSQL installation is required to test immediately.

### 1. Prerequisites
- Python 3.11+
- Virtual environment tool

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/100hard/PulseSQL.git
cd PulseSQL

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Seed Synthetic Database
```bash
python database/seed_synthetic_edtech_data.py
```
*Outputs:*
```text
Learners Seeded:          1,800
Telemetry Events Seeded:  26,547
Subscriptions Seeded:     330
AI Doubt Sessions Seeded: 1,451
Total Rows Seeded:        30,128
Planted Anomaly: Android v2.4.1 mock_exam_submitted latency spike (>4500ms)
```

### 4. Launch the Interactive 3-Pane UI
```bash
streamlit run app/dashboard_ui.py
```
Open your browser at `http://localhost:8501`.

### 5. Launch the FastAPI Backend (Optional)
```bash
uvicorn app.api_server:app --host 0.0.0.0 --port 8000 --reload
```
Interactive Swagger docs: `http://localhost:8000/docs`.

---

## 🐳 Docker Deployment

To launch PulseSQL in a containerized environment:

```dockerfile
# Run with Docker
docker build -t pulsesql:latest .
docker run -p 8501:8501 -p 8000:8000 pulsesql:latest
```

---

## 🔬 Live Demo Runbook: Reproducing the Planted Anomaly

1. Open the UI at `http://localhost:8501`.
2. In the **Center Pane**, ask:
   > *"Show mock exam completion funnel in the last 7 days"*
3. Observe the conversion from `mock_exam_started` to `mock_exam_submitted` hovering around ~57-61% (down from historical ~82%).
4. In the **Right Pane (One-Click RCA Drawer)**, click **"🚨 Run Root-Cause Slice"**.
5. Observe the automated diagnosis:
   - **Top Culprit:** `Android (app_version v2.4.1)`
   - **Platform Skew:** Android conversion delta: `-40.20%` (iOS & Web unaffected).
   - **Engineering Root Cause:** Build `v2.4.1` exam session latency spiked to `5,478ms` (app freezing before submission).

---

## 📁 Repository Structure

```text
pulsesql/
├── README.md                          # Executive overview, architecture, benchmark results, & setup
├── docs/
│   └── PRD_and_Wireframes.md          # Complete Product Requirements Document, User Stories, RICE table, & ASCII/Mermaid wireframes
├── config/
│   └── metrics_dictionary.yaml        # Semantic layer defining canonical product metrics & SQL formulas
├── database/
│   ├── schema.sql                     # DDL for the 4 EdTech tables
│   └── seed_synthetic_edtech_data.py  # Generates 10,000+ realistic rows + plants a specific Android v2.4.1 anomaly
├── engine/
│   ├── __init__.py
│   ├── semantic_router.py             # Matches user query to YAML metric definitions & checks ambiguity
│   ├── sql_synthesizer.py             # Generates read-only SQL with strict AST/regex guardrails
│   ├── self_healing_executor.py       # Executes SQL with up to 2 retry cycles feeding DB error traces back to LLM
│   └── rca_anomaly_slicer.py          # One-click Root-Cause Analysis across device_os, app_version, and acquisition_channel
├── evaluation/
│   ├── benchmark_50_queries.json      # 50 realistic PM analytics queries (funnels, cohorts, segmentation) + reference SQL
│   └── evaluate_benchmark.py          # Automated evaluation script reporting First-Attempt vs Self-Healed Execution Accuracy (target: 46/50 = 92%)
├── app/
│   ├── api_server.py                  # FastAPI endpoints (/query, /rca-slice, /metrics-catalog, /health)
│   └── dashboard_ui.py                # Interactive 3-pane UI (Left: Metric Dictionary, Center: Chat + Plotly Chart + Verified SQL Pill, Right: One-Click RCA Drawer)
├── .env.example
└── requirements.txt
```

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
