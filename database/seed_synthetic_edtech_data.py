"""
PulseSQL Synthetic EdTech Data Generator
=========================================
Generates 10,000+ realistic relational records for an EdTech test-prep platform.
Plants a deliberate multi-dimensional anomaly in the last 7 days:
- Overall mock_exam_submitted conversion drops by ~38%
- Driven specifically by device_os = 'Android' on app_version = 'v2.4.1'
- session_latency_ms spikes above 4500ms on this segment (app freezing)
"""

import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import sqlalchemy as sa
from sqlalchemy import create_engine, text

# Acquisition channels and device distributions
ACQUISITION_CHANNELS = ["Organic Search", "YouTube Creators", "Meta Ads", "Campus Referral"]
CHANNEL_WEIGHTS = [0.35, 0.30, 0.25, 0.10]

DEVICE_OPERATING_SYSTEMS = ["Android", "iOS", "Web"]
DEVICE_WEIGHTS = [0.55, 0.35, 0.10]

CITY_TIERS = ["Tier 1", "Tier 2", "Tier 3"]
CITY_TIER_WEIGHTS = [0.40, 0.40, 0.20]

APP_VERSIONS_LEGACY = ["v2.3.9", "v2.4.0"]
APP_VERSION_ANOMALOUS = "v2.4.1"


def resolve_database_url() -> str:
    """Resolves database URL from environment or defaults to local SQLite file."""
    configured_db_url = os.getenv("DATABASE_URL", "sqlite:///pulsesql_edtech.db")
    return configured_db_url


def initialize_database_schema(db_engine: sa.Engine, ddl_script_path: str) -> None:
    """Executes schema DDL statements to set up tables and indexes."""
    with open(ddl_script_path, "r", encoding="utf-8") as schema_file_handle:
        ddl_script_content = schema_file_handle.read()

    # Split statements for engines that execute one query per transaction
    individual_ddl_statements = [
        statement.strip() for statement in ddl_script_content.split(";") if statement.strip()
    ]
    with db_engine.begin() as database_connection:
        for single_statement in individual_ddl_statements:
            database_connection.execute(text(single_statement))


def generate_synthetic_dataset(
    total_learners_count: int = 1500,
    history_window_days: int = 45,
    anomaly_window_days: int = 7,
) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
    """
    Synthesizes realistic relational data across 4 tables with a planted anomaly.
    Returns: (learners, telemetry_events, subscriptions, ai_doubt_sessions)
    """
    random.seed(42)
    reference_now_timestamp = datetime.now(timezone.utc)
    baseline_cutoff_timestamp = reference_now_timestamp - timedelta(days=anomaly_window_days)
    dataset_start_timestamp = reference_now_timestamp - timedelta(days=history_window_days)

    synthetic_learners: List[Dict] = []
    synthetic_telemetry_events: List[Dict] = []
    synthetic_subscriptions: List[Dict] = []
    synthetic_doubt_sessions: List[Dict] = []

    # 1. Synthesize Learners
    for learner_sequence_index in range(1, total_learners_count + 1):
        assigned_learner_id = f"learner_{learner_sequence_index:05d}"
        random_signup_offset_seconds = random.randint(
            0, int((reference_now_timestamp - dataset_start_timestamp).total_seconds())
        )
        assigned_signup_timestamp = dataset_start_timestamp + timedelta(seconds=random_signup_offset_seconds)

        chosen_acquisition_channel = random.choices(ACQUISITION_CHANNELS, weights=CHANNEL_WEIGHTS, k=1)[0]
        chosen_device_os = random.choices(DEVICE_OPERATING_SYSTEMS, weights=DEVICE_WEIGHTS, k=1)[0]
        chosen_city_tier = random.choices(CITY_TIERS, weights=CITY_TIER_WEIGHTS, k=1)[0]

        synthetic_learners.append(
            {
                "learner_id": assigned_learner_id,
                "signup_timestamp": assigned_signup_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "acquisition_channel": chosen_acquisition_channel,
                "device_os": chosen_device_os,
                "city_tier": chosen_city_tier,
            }
        )

        # 2. Synthesize Telemetry Events & Funnel Progression
        # Learner activity sessions occur over days following signup
        active_session_days = random.randint(1, 14)
        for session_iteration in range(active_session_days):
            session_day_offset = random.randint(0, min(30, history_window_days))
            session_base_time = assigned_signup_timestamp + timedelta(
                days=session_day_offset, hours=random.randint(0, 23), minutes=random.randint(0, 59)
            )
            if session_base_time > reference_now_timestamp:
                continue

            is_within_anomaly_window = session_base_time >= baseline_cutoff_timestamp

            # App Version Allocation:
            # During the anomaly window, Android users heavily migrate to v2.4.1
            if is_within_anomaly_window:
                if chosen_device_os == "Android":
                    active_app_version = random.choices(
                        ["v2.3.9", "v2.4.0", APP_VERSION_ANOMALOUS], weights=[0.05, 0.15, 0.80], k=1
                    )[0]
                else:
                    active_app_version = random.choices(["v2.3.9", "v2.4.0", "v2.4.1"], weights=[0.10, 0.70, 0.20], k=1)[0]
            else:
                active_app_version = random.choices(APP_VERSIONS_LEGACY, weights=[0.40, 0.60], k=1)[0]

            # Standard session latency
            session_latency_ms = random.randint(180, 750)

            # Step 1: app_launch
            synthetic_telemetry_events.append(
                {
                    "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                    "learner_id": assigned_learner_id,
                    "event_name": "app_launch",
                    "app_version": active_app_version,
                    "session_latency_ms": session_latency_ms,
                    "occurred_at": session_base_time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            # Step 2: syllabus_explored (85% probability)
            if random.random() < 0.85:
                syllabus_time = session_base_time + timedelta(seconds=random.randint(15, 90))
                synthetic_telemetry_events.append(
                    {
                        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                        "learner_id": assigned_learner_id,
                        "event_name": "syllabus_explored",
                        "app_version": active_app_version,
                        "session_latency_ms": session_latency_ms + random.randint(20, 100),
                        "occurred_at": syllabus_time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            # Step 3: mock_exam_started (65% probability)
            if random.random() < 0.65:
                exam_start_time = session_base_time + timedelta(seconds=random.randint(100, 300))
                
                # CRITICAL PLANT: Check if this session triggers the Android v2.4.1 bug
                is_anomalous_session = (
                    is_within_anomaly_window
                    and chosen_device_os == "Android"
                    and active_app_version == APP_VERSION_ANOMALOUS
                )

                if is_anomalous_session:
                    # In this anomalous slice, latency blows up above 4500ms and completion crashes to ~14%
                    exam_event_latency_ms = random.randint(4650, 8900)
                    submission_probability = 0.14
                else:
                    exam_event_latency_ms = session_latency_ms + random.randint(50, 150)
                    submission_probability = 0.72

                synthetic_telemetry_events.append(
                    {
                        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                        "learner_id": assigned_learner_id,
                        "event_name": "mock_exam_started",
                        "app_version": active_app_version,
                        "session_latency_ms": exam_event_latency_ms,
                        "occurred_at": exam_start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

                # Step 4: mock_exam_submitted
                if random.random() < submission_probability:
                    exam_submit_time = exam_start_time + timedelta(minutes=random.randint(15, 60))
                    synthetic_telemetry_events.append(
                        {
                            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                            "learner_id": assigned_learner_id,
                            "event_name": "mock_exam_submitted",
                            "app_version": active_app_version,
                            "session_latency_ms": exam_event_latency_ms + random.randint(200, 800),
                            "occurred_at": exam_submit_time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                else:
                    # Record paywall_viewed for dropouts (30% view paywall after exam)
                    if random.random() < 0.30:
                        paywall_time = exam_start_time + timedelta(minutes=random.randint(5, 20))
                        synthetic_telemetry_events.append(
                            {
                                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                                "learner_id": assigned_learner_id,
                                "event_name": "paywall_viewed",
                                "app_version": active_app_version,
                                "session_latency_ms": exam_event_latency_ms,
                                "occurred_at": paywall_time.strftime("%Y-%m-%d %H:%M:%S"),
                            }
                        )

        # 3. Synthesize Subscriptions (22% paid conversion rate)
        if random.random() < 0.22:
            subscription_activation_time = assigned_signup_timestamp + timedelta(
                days=random.randint(1, 15), hours=random.randint(1, 12)
            )
            if subscription_activation_time <= reference_now_timestamp:
                chosen_plan = random.choices(["Monthly Pro", "Annual Pass"], weights=[0.65, 0.35], k=1)[0]
                plan_price_inr = 1499.00 if chosen_plan == "Monthly Pro" else 7999.00
                payment_status = random.choices(["completed", "failed", "refunded"], weights=[0.88, 0.09, 0.03], k=1)[0]

                synthetic_subscriptions.append(
                    {
                        "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
                        "learner_id": assigned_learner_id,
                        "plan_tier": chosen_plan,
                        "revenue_inr": plan_price_inr if payment_status == "completed" else 0.00,
                        "payment_status": payment_status,
                        "activated_at": subscription_activation_time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        # 4. Synthesize AI Doubt Sessions (40% of learners use AI Doubt Solver)
        if random.random() < 0.40:
            doubt_session_count = random.randint(1, 5)
            for _ in range(doubt_session_count):
                doubt_session_time = assigned_signup_timestamp + timedelta(
                    days=random.randint(1, 25), hours=random.randint(0, 23)
                )
                if doubt_session_time <= reference_now_timestamp:
                    synthetic_doubt_sessions.append(
                        {
                            "session_id": f"dbt_{uuid.uuid4().hex[:12]}",
                            "learner_id": assigned_learner_id,
                            "response_latency_ms": random.randint(450, 2400),
                            "resolution_rating": random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.08, 0.17, 0.35, 0.35], k=1)[0],
                            "token_consumption": random.randint(280, 1650),
                            "created_at": doubt_session_time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )

    return synthetic_learners, synthetic_telemetry_events, synthetic_subscriptions, synthetic_doubt_sessions


def populate_edtech_database(database_engine: sa.Engine, ddl_path: str) -> Dict[str, int]:
    """Generates synthetic data and populates relational database tables."""
    initialize_database_schema(database_engine, ddl_path)

    print("Generating 10,000+ realistic EdTech relational rows...")
    learners, events, subscriptions, doubt_sessions = generate_synthetic_dataset(
        total_learners_count=1800,
        history_window_days=45,
        anomaly_window_days=7,
    )

    with database_engine.begin() as connection:
        # Clear existing rows cleanly if rerun
        connection.execute(text("DELETE FROM ai_doubt_sessions;"))
        connection.execute(text("DELETE FROM subscriptions;"))
        connection.execute(text("DELETE FROM telemetry_events;"))
        connection.execute(text("DELETE FROM learners;"))

        # Batch insert learners
        connection.execute(
            text(
                """
                INSERT INTO learners (learner_id, signup_timestamp, acquisition_channel, device_os, city_tier)
                VALUES (:learner_id, :signup_timestamp, :acquisition_channel, :device_os, :city_tier)
                """
            ),
            learners,
        )

        # Batch insert telemetry events
        connection.execute(
            text(
                """
                INSERT INTO telemetry_events (event_id, learner_id, event_name, app_version, session_latency_ms, occurred_at)
                VALUES (:event_id, :learner_id, :event_name, :app_version, :session_latency_ms, :occurred_at)
                """
            ),
            events,
        )

        # Batch insert subscriptions
        connection.execute(
            text(
                """
                INSERT INTO subscriptions (subscription_id, learner_id, plan_tier, revenue_inr, payment_status, activated_at)
                VALUES (:subscription_id, :learner_id, :plan_tier, :revenue_inr, :payment_status, :activated_at)
                """
            ),
            subscriptions,
        )

        # Batch insert AI doubt sessions
        connection.execute(
            text(
                """
                INSERT INTO ai_doubt_sessions (session_id, learner_id, response_latency_ms, resolution_rating, token_consumption, created_at)
                VALUES (:session_id, :learner_id, :response_latency_ms, :resolution_rating, :token_consumption, :created_at)
                """
            ),
            doubt_sessions,
        )

    row_counts_summary = {
        "learners": len(learners),
        "telemetry_events": len(events),
        "subscriptions": len(subscriptions),
        "ai_doubt_sessions": len(doubt_sessions),
        "total_records": len(learners) + len(events) + len(subscriptions) + len(doubt_sessions),
    }

    return row_counts_summary


if __name__ == "__main__":
    resolved_db_url = resolve_database_url()
    schema_file_location = os.path.join(os.path.dirname(__file__), "schema.sql")

    engine_instance = create_engine(resolved_db_url)
    dataset_summary = populate_edtech_database(engine_instance, schema_file_location)

    print("\n--- PulseSQL Database Seeding Complete ---")
    print(f"Target Database URL: {resolved_db_url}")
    print(f"Learners Seeded:          {dataset_summary['learners']:,}")
    print(f"Telemetry Events Seeded:  {dataset_summary['telemetry_events']:,}")
    print(f"Subscriptions Seeded:     {dataset_summary['subscriptions']:,}")
    print(f"AI Doubt Sessions Seeded: {dataset_summary['ai_doubt_sessions']:,}")
    print(f"Total Rows Seeded:        {dataset_summary['total_records']:,}")
    print("Planted Anomaly: Android v2.4.1 mock_exam_submitted latency spike (>4500ms) and conversion dip in last 7 days.\n")
