-- PulseSQL Canonical EdTech Database Schema
-- Compatible with both SQLite and PostgreSQL

CREATE TABLE IF NOT EXISTS learners (
    learner_id VARCHAR(64) PRIMARY KEY,
    signup_timestamp TIMESTAMP NOT NULL,
    acquisition_channel VARCHAR(64) NOT NULL, -- 'Organic Search', 'YouTube Creators', 'Meta Ads', 'Campus Referral'
    device_os VARCHAR(32) NOT NULL,           -- 'Android', 'iOS', 'Web'
    city_tier VARCHAR(32) NOT NULL            -- 'Tier 1', 'Tier 2', 'Tier 3'
);

CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id VARCHAR(64) PRIMARY KEY,
    learner_id VARCHAR(64) NOT NULL,
    event_name VARCHAR(64) NOT NULL,          -- 'app_launch', 'syllabus_explored', 'mock_exam_started', 'mock_exam_submitted', 'paywall_viewed'
    app_version VARCHAR(32) NOT NULL,         -- 'v2.3.9', 'v2.4.0', 'v2.4.1'
    session_latency_ms INTEGER NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id VARCHAR(64) PRIMARY KEY,
    learner_id VARCHAR(64) NOT NULL,
    plan_tier VARCHAR(64) NOT NULL,           -- 'Monthly Pro', 'Annual Pass'
    revenue_inr NUMERIC(10, 2) NOT NULL,      -- e.g. 1499.00, 7999.00
    payment_status VARCHAR(32) NOT NULL,      -- 'completed', 'failed', 'refunded'
    activated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS ai_doubt_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    learner_id VARCHAR(64) NOT NULL,
    response_latency_ms INTEGER NOT NULL,
    resolution_rating INTEGER,                -- 1 to 5 stars
    token_consumption INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

-- Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_telemetry_learner_event ON telemetry_events(learner_id, event_name);
CREATE INDEX IF NOT EXISTS idx_telemetry_occurred_at ON telemetry_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_telemetry_app_version ON telemetry_events(app_version);
CREATE INDEX IF NOT EXISTS idx_learners_signup_timestamp ON learners(signup_timestamp);
CREATE INDEX IF NOT EXISTS idx_learners_channel ON learners(acquisition_channel);
CREATE INDEX IF NOT EXISTS idx_subscriptions_learner ON subscriptions(learner_id, payment_status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_activated ON subscriptions(activated_at);
CREATE INDEX IF NOT EXISTS idx_doubt_learner ON ai_doubt_sessions(learner_id);
