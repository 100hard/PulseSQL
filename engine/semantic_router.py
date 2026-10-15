"""
PulseSQL Semantic Metric Router
===============================
Parses natural language PM queries, maps user intent against the canonical
YAML Semantic Metric Dictionary, extracts dimensions/temporal filters,
and identifies semantic ambiguities before SQL generation.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class SemanticRoutingResult:
    """Encapsulates the decision outcome of the semantic routing pipeline."""
    canonical_metric_name: str
    display_title: str
    category: str
    matched_synonym_phrase: str
    confidence_score: float
    dimensions_requested: List[str] = field(default_factory=list)
    temporal_filter_description: str = "all_time"
    is_ambiguous: bool = False
    ambiguity_clarification_prompt: Optional[str] = None
    canonical_sql_template: str = ""
    metric_metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticMetricRouter:
    """
    Evaluates product queries against the YAML Semantic Metric Dictionary.
    Matches canonical definitions and guards against business logic hallucinations.
    """

    def __init__(self, metrics_catalog_path: Optional[str] = None):
        if metrics_catalog_path is None:
            base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            metrics_catalog_path = os.path.join(base_directory, "config", "metrics_dictionary.yaml")

        self.metrics_catalog_path = metrics_catalog_path
        self.semantic_metric_catalog = self._load_semantic_dictionary(metrics_catalog_path)
        self.registered_metrics: Dict[str, Dict[str, Any]] = self.semantic_metric_catalog.get("metrics", {})

    def _load_semantic_dictionary(self, dictionary_path: str) -> Dict[str, Any]:
        """Loads and parses the YAML metric catalog."""
        if not os.path.exists(dictionary_path):
            raise FileNotFoundError(f"Semantic metric catalog not found at: {dictionary_path}")
        with open(dictionary_path, "r", encoding="utf-8") as dictionary_file_handle:
            loaded_catalog = yaml.safe_load(dictionary_file_handle)
        return loaded_catalog or {}

    def extract_temporal_constraints(self, user_natural_query: str) -> Tuple[str, Optional[int]]:
        """Extracts relative time windows like 'last 7 days', 'last 30 days'."""
        normalized_query_text = user_natural_query.lower()

        seven_day_match = re.search(r"\b(last|past)\s+(7|seven)\s+days?\b", normalized_query_text)
        if seven_day_match:
            return "last_7_days", 7

        fourteen_day_match = re.search(r"\b(last|past)\s+(14|fourteen)\s+days?\b", normalized_query_text)
        if fourteen_day_match:
            return "last_14_days", 14

        thirty_day_match = re.search(r"\b(last|past)\s+(30|thirty)\s+days?\b", normalized_query_text)
        if thirty_day_match:
            return "last_30_days", 30

        yesterday_match = re.search(r"\byesterday\b", normalized_query_text)
        if yesterday_match:
            return "yesterday", 1

        today_match = re.search(r"\b(today|now)\b", normalized_query_text)
        if today_match:
            return "today", 0

        return "all_time", None

    def extract_requested_dimensions(self, user_natural_query: str) -> List[str]:
        """Identifies dimensional breakdown groupings mentioned in the query."""
        normalized_query_text = user_natural_query.lower()
        detected_dimensions: List[str] = []

        dimension_keywords_map = {
            "device_os": ["device", "os", "android", "ios", "platform", "mobile", "web"],
            "acquisition_channel": ["channel", "acquisition", "source", "campaign", "youtube", "meta", "organic", "referral"],
            "app_version": ["version", "build", "release", "v2.3.9", "v2.4.0", "v2.4.1"],
            "city_tier": ["tier", "city", "tier 1", "tier 2", "tier 3", "geography"],
            "plan_tier": ["plan", "monthly", "annual", "pro", "pass", "subscription tier"],
        }

        for dimension_identifier, trigger_tokens in dimension_keywords_map.items():
            for trigger_token in trigger_tokens:
                if re.search(rf"\b{re.escape(trigger_token)}\b", normalized_query_text):
                    if dimension_identifier not in detected_dimensions:
                        detected_dimensions.append(dimension_identifier)
                    break

        return detected_dimensions

    def route_query_to_metric(self, user_natural_query: str) -> SemanticRoutingResult:
        """
        Matches user query to the most relevant canonical metric in the YAML catalog.
        Evaluates synonym matches, title matches, and ambiguity triggers.
        """
        normalized_query_text = user_natural_query.lower().strip()
        extracted_temporal_filter, _ = self.extract_temporal_constraints(user_natural_query)
        extracted_dimensions = self.extract_requested_dimensions(user_natural_query)

        # Check for ambiguous query triggers
        # Case A: User asks generic "conversion" without qualifying mock exam funnel vs paid conversion
        if re.search(r"\bconversion\b", normalized_query_text) and not (
            "exam" in normalized_query_text
            or "mock" in normalized_query_text
            or "funnel" in normalized_query_text
            or "paid" in normalized_query_text
            or "subscription" in normalized_query_text
            or "revenue" in normalized_query_text
        ):
            return SemanticRoutingResult(
                canonical_metric_name="ambiguous_conversion_inquiry",
                display_title="Ambiguous Conversion Intent",
                category="ambiguity",
                matched_synonym_phrase="conversion",
                confidence_score=0.40,
                dimensions_requested=extracted_dimensions,
                temporal_filter_description=extracted_temporal_filter,
                is_ambiguous=True,
                ambiguity_clarification_prompt=(
                    "Your query mentions 'conversion' without specifying the domain. "
                    "Did you mean: (A) 'Mock Exam Completion Funnel' (app_launch -> exam_started -> exam_submitted) "
                    "or (B) 'Paid Subscription Conversion Rate' (learners completing payment)?"
                ),
                canonical_sql_template="",
            )

        # Scoring candidate metrics
        best_scoring_metric_name: Optional[str] = None
        highest_match_score: float = 0.0
        best_matched_synonym: str = ""

        for candidate_metric_key, candidate_metric_spec in self.registered_metrics.items():
            current_metric_score = 0.0
            current_matched_phrase = ""

            canonical_title = candidate_metric_spec.get("display_title", "").lower()
            canonical_name = candidate_metric_spec.get("canonical_name", "").lower()
            synonyms_list = [syn.lower() for syn in candidate_metric_spec.get("synonyms", [])]

            # Direct canonical name or title match
            if canonical_name in normalized_query_text or canonical_title in normalized_query_text:
                current_metric_score = max(current_metric_score, 0.95)
                current_matched_phrase = canonical_title

            # Synonym evaluation
            for candidate_synonym in synonyms_list:
                if candidate_synonym in normalized_query_text:
                    synonym_length_bonus = min(0.35, len(candidate_synonym.split()) * 0.10)
                    calculated_score = 0.70 + synonym_length_bonus
                    if calculated_score > current_metric_score:
                        current_metric_score = calculated_score
                        current_matched_phrase = candidate_synonym

            # Domain keyword heuristics
            if candidate_metric_key == "daily_active_learners":
                if any(k in normalized_query_text for k in ["active users", "active learners", "dal", "daily active"]):
                    current_metric_score = max(current_metric_score, 0.92)
                    current_matched_phrase = "daily_active_learners"

            elif candidate_metric_key == "mock_exam_completion_funnel":
                if any(k in normalized_query_text for k in ["funnel", "exam drop", "exam completion", "mock exam", "test completion"]):
                    current_metric_score = max(current_metric_score, 0.92)
                    current_matched_phrase = "mock_exam_completion_funnel"

            elif candidate_metric_key == "d7_cohort_retention":
                if any(k in normalized_query_text for k in ["retention", "cohort", "d7", "day 7", "returning"]):
                    current_metric_score = max(current_metric_score, 0.92)
                    current_matched_phrase = "d7_cohort_retention"

            elif candidate_metric_key == "paid_conversion_rate":
                if any(k in normalized_query_text for k in ["paid", "paywall", "subscription conversion", "paying learners", "conversion rate"]):
                    current_metric_score = max(current_metric_score, 0.90)
                    current_matched_phrase = "paid_conversion_rate"

            elif candidate_metric_key == "net_revenue_by_channel":
                if any(k in normalized_query_text for k in ["revenue", "inr", "sales", "earnings", "channel revenue", "cac return"]):
                    current_metric_score = max(current_metric_score, 0.91)
                    current_matched_phrase = "net_revenue_by_channel"

            elif candidate_metric_key == "ai_doubt_resolution_rate":
                if any(k in normalized_query_text for k in ["doubt", "ai latency", "token", "satisfaction", "doubt sessions"]):
                    current_metric_score = max(current_metric_score, 0.91)
                    current_matched_phrase = "ai_doubt_resolution_rate"

            if current_metric_score > highest_match_score:
                highest_match_score = current_metric_score
                best_scoring_metric_name = candidate_metric_key
                best_matched_synonym = current_matched_phrase

        # Fallback if no specific metric crossed threshold
        if not best_scoring_metric_name or highest_match_score < 0.35:
            # Check if query asks for a general table or telemetry metric
            return SemanticRoutingResult(
                canonical_metric_name="custom_exploratory_query",
                display_title="Ad-Hoc Product Analytics Query",
                category="exploratory",
                matched_synonym_phrase="ad_hoc",
                confidence_score=0.50,
                dimensions_requested=extracted_dimensions,
                temporal_filter_description=extracted_temporal_filter,
                is_ambiguous=False,
                canonical_sql_template="",
                metric_metadata={},
            )

        matched_metric_record = self.registered_metrics[best_scoring_metric_name]

        return SemanticRoutingResult(
            canonical_metric_name=best_scoring_metric_name,
            display_title=matched_metric_record.get("display_title", best_scoring_metric_name),
            category=matched_metric_record.get("category", "general"),
            matched_synonym_phrase=best_matched_synonym,
            confidence_score=highest_match_score,
            dimensions_requested=extracted_dimensions,
            temporal_filter_description=extracted_temporal_filter,
            is_ambiguous=False,
            canonical_sql_template=matched_metric_record.get("sql_formula", "").strip(),
            metric_metadata=matched_metric_record,
        )

    def list_all_canonical_metrics(self) -> List[Dict[str, Any]]:
        """Returns clean list of all defined canonical metrics in catalog."""
        metric_summaries_list: List[Dict[str, Any]] = []
        for metric_identifier, metric_properties in self.registered_metrics.items():
            metric_summaries_list.append(
                {
                    "metric_id": metric_identifier,
                    "title": metric_properties.get("display_title", metric_identifier),
                    "category": metric_properties.get("category", "uncategorized"),
                    "description": metric_properties.get("description", ""),
                    "synonyms": metric_properties.get("synonyms", []),
                    "sql_formula": metric_properties.get("sql_formula", "").strip(),
                }
            )
        return metric_summaries_list
