"""Opportunity Discovery module for AlphaCouncil (M2).

Deterministic candidate generation pipeline with two-stage funnel:
1. Cheap bulk screening of universe -> preliminary candidates
2. Deep M1 MarketState analysis of top-K -> final candidates
"""

from __future__ import annotations

from app.discovery.diversification import (
    apply_directional_balance,
    apply_diversification,
    apply_final_diversification,
)
from app.discovery.filters import apply_hard_filters
from app.discovery.models import (
    AssetCategory,
    Candidate,
    CandidateRejection,
    CandidateSet,
    OpportunityScore,
    PreliminaryCandidate,
    RejectionReason,
    ScreeningObservation,
    SignalDirection,
    UniverseMode,
)
from app.discovery.scoring import compute_opportunity_score, rank_candidates, select_top_k
from app.discovery.screening import BulkScreener
from app.discovery.service import OpportunityDiscoveryService, create_discovery_service
from app.discovery.signals import SignalWeights, compute_all_signals
from app.discovery.universe import (
    AlpacaUniverseProvider,
    CuratedUniverseProvider,
    create_universe_provider,
)

__all__ = [
    # Models
    "UniverseMode",
    "AssetCategory",
    "SignalDirection",
    "RejectionReason",
    "ScreeningObservation",
    "OpportunityScore",
    "PreliminaryCandidate",
    "Candidate",
    "CandidateRejection",
    "CandidateSet",
    # Universe
    "UniverseProvider",
    "CuratedUniverseProvider",
    "AlpacaUniverseProvider",
    "create_universe_provider",
    # Filters
    "apply_hard_filters",
    # Signals
    "SignalWeights",
    "compute_all_signals",
    # Scoring
    "compute_opportunity_score",
    "rank_candidates",
    "select_top_k",
    # Diversification
    "apply_diversification",
    "apply_directional_balance",
    "apply_final_diversification",
    # Screening
    "BulkScreener",
    # Service
    "OpportunityDiscoveryService",
    "create_discovery_service",
]