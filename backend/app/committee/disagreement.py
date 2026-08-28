"""Disagreement detection and challenge/rebuttal mechanism for M3 committee."""

from __future__ import annotations

from app.committee.agents.base import CommitteeAgent
from app.committee.models import (
    STANCE_VALUE,
    AgentChallenge,
    AgentOpinion,
    AgentRole,
    DisagreementReport,
    DisagreementSeverity,
)

# Disagreement threshold for triggering rebuttal
REBUTTAL_THRESHOLD = DisagreementSeverity.MEDIUM


def detect_disagreement(opinions: list[AgentOpinion]) -> DisagreementReport:
    """Detect disagreement among agent opinions deterministically.

    Rules:
    - Count directional agents (exclude ABSTAIN)
    - Calculate stance spread (max - min stance values)
    - Identify conflicting agents
    - Check for conflicting evidence citations
    """
    if not opinions:
        return DisagreementReport(
            severity=DisagreementSeverity.NONE,
            stance_spread=0,
        )

    # Filter out failed/abstained agents for disagreement calc
    valid_opinions = [o for o in opinions if o.stance != "ABSTAIN"]

    if not valid_opinions:
        return DisagreementReport(
            severity=DisagreementSeverity.NONE,
            stance_spread=0,
            abstaining_agents=tuple(o.agent_role for o in opinions),
        )

    # Get numeric stance values
    stance_values = []
    bullish_agents = []
    bearish_agents = []
    neutral_agents = []

    for opinion in valid_opinions:
        val = STANCE_VALUE.get(opinion.stance)
        if val is not None:
            stance_values.append(val)
            if opinion.is_bullish:
                bullish_agents.append(opinion.agent_role)
            elif opinion.is_bearish:
                bearish_agents.append(opinion.agent_role)
            else:
                neutral_agents.append(opinion.agent_role)

    if not stance_values:
        return DisagreementReport(
            severity=DisagreementSeverity.NONE,
            stance_spread=0,
        )

    stance_spread = max(stance_values) - min(stance_values)

    # Identify conflicting agents
    conflicting = []
    if bullish_agents and bearish_agents:
        conflicting.extend(bullish_agents)
        conflicting.extend(bearish_agents)

    # Check for conflicting evidence citations
    all_supporting: set[str] = set()
    all_contradicting: set[str] = set()
    conflicting_evidence: set[str] = set()

    # We'd need access to all opinions to check this fully
    # For now, we'll note this as a limitation

    # Determine severity
    severity = _classify_severity(stance_spread, bullish_agents, bearish_agents, neutral_agents)

    challenge_required = severity in (DisagreementSeverity.MEDIUM, DisagreementSeverity.HIGH)

    return DisagreementReport(
        severity=severity,
        stance_spread=stance_spread,
        conflicting_agents=tuple(conflicting),
        conflicting_evidence_ids=tuple(conflicting_evidence),
        challenge_required=challenge_required,
        bullish_agents=tuple(bullish_agents),
        bearish_agents=tuple(bearish_agents),
        neutral_agents=tuple(neutral_agents),
        abstaining_agents=tuple(
            o.agent_role for o in opinions if o.stance == "ABSTAIN"
        ),
    )


def _classify_severity(
    stance_spread: int,
    bullish_agents: list[AgentRole],
    bearish_agents: list[AgentRole],
    neutral_agents: list[AgentRole],
) -> DisagreementSeverity:
    """Classify disagreement severity based on stance spread and agent counts."""
    total_directional = len(bullish_agents) + len(bearish_agents)

    if stance_spread >= 4:  # STRONG_LONG (+2) vs STRONG_SHORT (-2) = 4
        return DisagreementSeverity.HIGH
    elif stance_spread >= 3:  # e.g., LONG (+1) vs STRONG_SHORT (-2) = 3
        return DisagreementSeverity.HIGH
    elif stance_spread >= 2:  # e.g., LONG (+1) vs SHORT (-1) = 2, or STRONG_LONG vs NEUTRAL
        if total_directional >= 3:
            return DisagreementSeverity.MEDIUM
        return DisagreementSeverity.LOW
    elif stance_spread >= 1:
        if total_directional >= 3:
            return DisagreementSeverity.LOW
        return DisagreementSeverity.NONE
    else:
        return DisagreementSeverity.NONE


def generate_challenges(opinions: list[AgentOpinion], disagreement: DisagreementReport) -> list[AgentChallenge]:
    """Generate targeted challenges from disagreement analysis.

    Creates targeted AgentChallenge objects for agents whose views
    conflict with the majority or with strong opposing views.
    """
    challenges: list[AgentChallenge] = []

    if not disagreement.challenge_required:
        return challenges

    # Group opinions by role for easy lookup
    opinions_by_role = {o.agent_role: o for o in opinions}

    # Identify bullish and bearish agents
    bullish = [o for o in opinions if o.is_bullish]
    bearish = [o for o in opinions if o.is_bearish]

    # For each agent in the minority, generate a challenge
    if len(bullish) > len(bearish):
        # Bearish agents are minority - challenge them
        for bear_opinion in bearish:
            if bear_opinion.stance == "ABSTAIN":
                continue
            challenge = _create_challenge(
                target_agent=bear_opinion.agent_role,
                source_agents=[o.agent_role for o in bullish],
                target_opinion=bear_opinion,
                opposing_opinions=bullish,
            )
            challenges.append(challenge)
    elif len(bearish) > len(bullish):
        # Bullish agents are minority - challenge them
        for bull_opinion in bullish:
            if bull_opinion.stance == "ABSTAIN":
                continue
            challenge = _create_challenge(
                target_agent=bull_opinion.agent_role,
                source_agents=[o.agent_role for o in bearish],
                target_opinion=bull_opinion,
                opposing_opinions=bearish,
            )
            challenges.append(challenge)
    else:
        # Equal numbers - challenge both sides if strong disagreement
        if disagreement.severity == "HIGH":
            for bull_opinion in bullish:
                if bull_opinion.stance == "ABSTAIN":
                    continue
                challenge = _create_challenge(
                    target_agent=bull_opinion.agent_role,
                    source_agents=[o.agent_role for o in bearish],
                    target_opinion=bull_opinion,
                    opposing_opinions=bearish,
                )
                challenges.append(challenge)

            for bear_opinion in bearish:
                if bear_opinion.stance == "ABSTAIN":
                    continue
                challenge = _create_challenge(
                    target_agent=bear_opinion.agent_role,
                    source_agents=[o.agent_role for o in bullish],
                    target_opinion=bear_opinion,
                    opposing_opinions=bullish,
                )
                challenges.append(challenge)

    return challenges


def _create_challenge(
    target_agent: str,
    source_agents: list[AgentRole],
    target_opinion: AgentOpinion,
    opposing_opinions: list[AgentOpinion],
) -> AgentChallenge:
    """Create a targeted challenge for a specific agent."""
    from app.committee.models import AgentChallenge, AgentRole

    opposing_stances = {o.agent_role: o.stance for o in opposing_opinions}
    challenged_evidence = target_opinion.supporting_evidence_ids

    # Build concise challenge summary
    opposing_thesis_summary = "; ".join(
        f"{o.agent_role.value}: {o.thesis[:80]}" for o in opposing_opinions
    )

    challenge_summary = (
        f"{', '.join(source_agents)} strongly disagree with your {target_opinion.stance.value} stance. "
        f"Opposing views: {opposing_thesis_summary}. "
        f"Please address their key evidence: {', '.join(opposing_opinions[0].supporting_evidence_ids[:3])}."
    )

    return AgentChallenge(
        target_agent=AgentRole(target_agent),
        source_agents=tuple(AgentRole(r) for r in source_agents),
        symbol=target_opinion.symbol,
        opposing_stances=opposing_stances,
        challenged_evidence_ids=challenged_evidence,
        challenge_summary=challenge_summary,
        round=2,
    )


def run_rebuttal_round(
    agents: dict[str, CommitteeAgent],
    evidence: object,
    challenges: list[AgentChallenge],
    initial_opinions: list[AgentOpinion],
) -> list[AgentOpinion]:
    """Execute rebuttal round for all challenges.

    Returns updated opinions (initial opinions preserved separately).
    """
    updated_opinions = {o.agent_role: o for o in initial_opinions}

    for challenge in challenges:
        agent = agents.get(challenge.target_agent.value)
        if not agent:
            continue

        # Get prior opinion
        prior = updated_opinions.get(challenge.target_agent)
        if not prior:
            continue

        # Execute rebuttal
        result = agent.rebut(evidence, challenge, prior)

        if result.status == "SUCCESS" and result.opinion:
            updated_opinions[challenge.target_agent] = result.opinion
        elif result.status == "ABSTAINED":
            # Update with abstained opinion if available
            if result.opinion:
                updated_opinions[challenge.target_agent] = result.opinion

    return list(updated_opinions.values())