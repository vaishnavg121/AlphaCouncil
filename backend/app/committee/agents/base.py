"""Base agent class for M3 committee agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from app.committee.models import (
    AgentOpinion,
    AgentResult,
    AgentRole,
    AgentStatus,
    EvidencePacket,
)
from app.committee.prompts import REBUTTAL_PROMPT_V1
from app.core.config import Settings


class CommitteeAgent(ABC):
    """Base class for committee agents."""

    def __init__(
        self,
        settings: Settings,
        *,
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    @abstractmethod
    def role(self) -> AgentRole:
        """The role of this agent."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt for this agent."""
        ...

    @property
    @abstractmethod
    def _prompt_version(self) -> str:
        """The prompt version for this agent."""
        ...

    @property
    def rebuttal_prompt_template(self) -> str:
        """Template for rebuttal prompt."""
        return REBUTTAL_PROMPT_V1

    def _build_user_prompt(self, evidence: EvidencePacket) -> str:
        """Build the user prompt with serialized evidence."""
        from app.committee.evidence import serialize_evidence_for_prompt
        return serialize_evidence_for_prompt(evidence)

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Call the NVIDIA LLM API with structured output request."""
        if not self._settings.nvidia_credentials_configured:
            raise RuntimeError("NVIDIA_API_KEY is not configured")
        if not self._settings.llm_model:
            raise RuntimeError("LLM_MODEL is not configured")

        api_key = self._settings.nvidia_api_key.get_secret_value()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if self._client is not None:
            response = self._client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        else:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()

    def _parse_opinion(self, raw_response: str) -> AgentOpinion:
        """Parse and validate LLM response into AgentOpinion."""
        import json

        # Try to extract JSON from response
        content = raw_response.strip()

        # Try to find JSON object in response
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in LLM response: {e}")

        # Validate required fields
        required_fields = ["agent_role", "symbol", "stance", "confidence", "thesis"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        # Validate agent role matches
        if data.get("agent_role") != self.role.value:
            raise ValueError(f"Agent role mismatch: expected {self.role.value}, got {data.get('agent_role')}")

        # Parse and validate
        try:
            opinion = AgentOpinion(**data)
        except ValidationError as e:
            raise ValueError(f"Invalid opinion schema: {e}")

        return opinion

    def _validate_grounding(self, opinion: AgentOpinion, evidence: EvidencePacket) -> tuple[bool, list[str]]:
        """Validate that all cited evidence IDs exist in the evidence packet."""
        errors = []

        all_ids = set()
        for item in evidence.evidence:
            all_ids.add(item.id)

        for eid in opinion.supporting_evidence_ids:
            if eid not in all_ids:
                errors.append(f"Unknown supporting evidence ID: {eid}")

        for eid in opinion.contradicting_evidence_ids:
            if eid not in all_ids:
                errors.append(f"Unknown contradicting evidence ID: {eid}")

        return len(errors) == 0, errors

    def analyze(self, evidence: EvidencePacket) -> AgentResult:
        """Run independent analysis round."""
        from time import perf_counter

        started = perf_counter()

        try:
            user_prompt = self._build_user_prompt(evidence)
            raw_response = self._call_llm(self.system_prompt, user_prompt)

            opinion = self._parse_opinion(raw_response)
            data = opinion.model_dump()
            # Remove fields we set ourselves
            data.pop("round", None)
            data.pop("prompt_version", None)
            data.pop("model", None)
            data.pop("latency_ms", None)
            opinion = AgentOpinion(
                **data,
                round=1,
                prompt_version=self._prompt_version,
                model=self._settings.llm_model,
                latency_ms=round((perf_counter() - started) * 1000),
            )

            # Validate grounding
            valid, errors = self._validate_grounding(opinion, evidence)
            if not valid:
                return AgentResult(
                    agent_role=self.role,
                    status=AgentStatus.FAILED,
                    error=f"Grounding validation failed: {'; '.join(errors)}",
                    latency_ms=round((perf_counter() - started) * 1000),
                    attempts=1,
                )

            return AgentResult(
                agent_role=self.role,
                status=AgentStatus.SUCCESS,
                opinion=opinion,
                latency_ms=round((perf_counter() - started) * 1000),
                attempts=1,
            )

        except httpx.TimeoutException:
            return AgentResult(
                agent_role=self.role,
                status=AgentStatus.FAILED,
                error="LLM request timed out",
                latency_ms=round((perf_counter() - started) * 1000),
                attempts=1,
            )
        except Exception as e:
            return AgentResult(
                agent_role=self.role,
                status=AgentStatus.FAILED,
                error=str(e),
                latency_ms=round((perf_counter() - started) * 1000),
                attempts=1,
            )

    def rebut(
        self,
        evidence: EvidencePacket,
        challenge,
        prior_opinion,
    ) -> AgentResult:
        """Run rebuttal round."""
        from time import perf_counter

        started = perf_counter()

        try:
            # Format challenge for prompt
            opposing_stances = ", ".join(
                f"{role.value}: {stance.value}" for role, stance in challenge.opposing_stances.items()
            )
            challenged_evidence = ", ".join(challenge.challenged_evidence_ids)

            initial_opinion_json = prior_opinion.model_dump_json(indent=2)

            rebuttal_prompt = self.rebuttal_prompt_template.format(
                agent_role=self.role.value,
                agent_role_lower=self.role.value.lower(),
                challenge_summary=challenge.challenge_summary,
                opposing_stances=opposing_stances,
                challenged_evidence=challenged_evidence,
                initial_opinion=initial_opinion_json,
            )

            user_prompt = self._build_user_prompt(evidence) + "\n\n" + rebuttal_prompt

            raw_response = self._call_llm(self.system_prompt, user_prompt, temperature=0.1)
            opinion = self._parse_opinion(raw_response)
            opinion = AgentOpinion(
                **opinion.model_dump(),
                round=2,
                prompt_version=self._prompt_version,
                model=self._settings.llm_model,
                latency_ms=round((perf_counter() - started) * 1000),
            )

            valid, errors = self._validate_grounding(opinion, evidence)
            if not valid:
                return AgentResult(
                    agent_role=self.role,
                    status=AgentStatus.FAILED,
                    error=f"Grounding validation failed: {'; '.join(errors)}",
                    latency_ms=round((perf_counter() - started) * 1000),
                    attempts=1,
                )

            return AgentResult(
                agent_role=self.role,
                status=AgentStatus.SUCCESS,
                opinion=opinion,
                latency_ms=round((perf_counter() - started) * 1000),
                attempts=1,
            )

        except httpx.TimeoutException:
            return AgentResult(
                agent_role=self.role,
                status=AgentStatus.FAILED,
                error="LLM request timed out",
                latency_ms=round((perf_counter() - started) * 1000),
                attempts=1,
            )
        except Exception as e:
            return AgentResult(
                agent_role=self.role,
                status=AgentStatus.FAILED,
                error=str(e),
                latency_ms=round((perf_counter() - started) * 1000),
                attempts=1,
            )