"""Committee module for M3 adversarial investment committee."""

from __future__ import annotations

from app.committee.agents import (
    CommitteeAgent,
    QuantAgent,
    BullAgent,
    BearAgent,
    RegimeAgent,
)
from app.committee.aggregation import CommitteeAggregator
from app.committee.disagreement import detect_disagreement, generate_challenges, run_rebuttal_round
from app.committee.evidence import build_evidence_packet, serialize_evidence_for_prompt
from app.committee.llm import NvidiaCommitteeLLMProvider
from app.committee.models import (
    AgentChallenge,
    AgentOpinion,
    AgentResult,
    AgentRole,
    SignalDirection,
    AgentStance,
    AgentStatus,
    CommitteeDecision,
    CommitteeDecisionModel,
    CommitteeResult,
    DisagreementReport,
    DisagreementSeverity,
    EvidenceItem,
    EvidencePacket,
    EvidenceCategory,
    EvidenceSource,
    TradeThesis,
    NoTradeReason,
)
from app.committee.evidence import EvidenceId
from app.committee.prompts import (
    QUANT_PROMPT_V1,
    BULL_PROMPT_V1,
    BEAR_PROMPT_V1,
    REGIME_PROMPT_V1,
    REBUTTAL_PROMPT_V1,
)
from app.committee.service import InvestmentCommitteeService, create_committee_service

__all__ = [
    # Agents
    "CommitteeAgent",
    "QuantAgent",
    "BullAgent",
    "BearAgent",
    "RegimeAgent",
    # Aggregation
    "CommitteeAggregator",
    # Disagreement
    "detect_disagreement",
    "generate_challenges",
    "run_rebuttal_round",
    # Evidence
    "build_evidence_packet",
    "serialize_evidence_for_prompt",
    "EvidenceId",
    # LLM
    "NvidiaCommitteeLLMProvider",
    # Models
    "AgentChallenge",
    "AgentOpinion",
    "AgentResult",
    "AgentRole",
    "SignalDirection",
    "AgentStance",
    "AgentStatus",
    "CommitteeDecision",
    "CommitteeDecisionModel",
    "CommitteeResult",
    "DisagreementReport",
    "DisagreementSeverity",
    "EvidenceItem",
    "EvidencePacket",
    "EvidenceCategory",
    "EvidenceSource",
    "EvidenceId",
    "TradeThesis",
    "NoTradeReason",
    # Prompts
    "QUANT_PROMPT_V1",
    "BULL_PROMPT_V1",
    "BEAR_PROMPT_V1",
    "REGIME_PROMPT_V1",
    "REBUTTAL_PROMPT_V1",
    # Service
    "InvestmentCommitteeService",
    "create_committee_service",
]