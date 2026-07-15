from __future__ import annotations

from typing import cast

import pytest

from ai_parametric_architect.agents import (
    ArchitecturePlannerAgent,
    PatchGeneratorAgent,
    RequirementAgent,
)
from ai_parametric_architect.llm import (
    LLMContractError,
    LLMFloorPlanPlanner,
    LLMPatchProposalGenerator,
    LLMRequirementParser,
    MockLLMProvider,
)
from ai_parametric_architect.llm.base import LLMOutput, StructuredPrompt
from ai_parametric_architect.planning import FloorPlanProposal
from ai_parametric_architect.ports import (
    FloorPlanPlanner,
    PatchProposalGenerator,
    RequirementParser,
)

from .helpers import make_intent, make_patch, make_plan, make_revision


def _requirement_port(value: RequirementParser) -> RequirementParser:
    return value


def _floor_plan_port(
    value: FloorPlanPlanner[FloorPlanProposal],
) -> FloorPlanPlanner[FloorPlanProposal]:
    return value


def _patch_port(
    value: PatchProposalGenerator[FloorPlanProposal],
) -> PatchProposalGenerator[FloorPlanProposal]:
    return value


def test_typed_adapters_compose_with_all_existing_agent_boundaries() -> None:
    intent = make_intent()
    plan = make_plan()
    patch = make_patch()
    revision = make_revision()
    provider = MockLLMProvider((intent, plan, patch))
    requirement_parser = LLMRequirementParser(provider)
    floor_plan_planner = LLMFloorPlanPlanner(provider)
    patch_generator = LLMPatchProposalGenerator(provider)

    extracted = RequirementAgent(requirement_parser).run("Design a house")
    suggested = ArchitecturePlannerAgent(floor_plan_planner).run(extracted)
    proposed = PatchGeneratorAgent(patch_generator).generate(suggested, revision)

    assert extracted is intent
    assert suggested is plan
    assert proposed is patch
    assert _requirement_port(requirement_parser) is requirement_parser
    assert _floor_plan_port(floor_plan_planner) is floor_plan_planner
    assert _patch_port(patch_generator) is patch_generator
    assert repr(requirement_parser) == "LLMRequirementParser()"
    assert repr(floor_plan_planner) == "LLMFloorPlanPlanner()"
    assert repr(patch_generator) == "LLMPatchProposalGenerator()"


class MalformedProvider:
    @property
    def name(self) -> str:
        return "malformed-provider"

    @property
    def version(self) -> str:
        return "1.0.0"

    def complete[OutputT: LLMOutput](
        self,
        prompt: StructuredPrompt[OutputT],
    ) -> OutputT:
        del prompt
        return cast(OutputT, {"unsafe": True})


def test_each_adapter_independently_rechecks_an_untrusted_provider_result() -> None:
    provider = MalformedProvider()

    with pytest.raises(LLMContractError) as requirement_error:
        LLMRequirementParser(provider).parse("Design a house")
    with pytest.raises(LLMContractError) as plan_error:
        LLMFloorPlanPlanner(provider).plan(make_intent())
    with pytest.raises(LLMContractError) as patch_error:
        LLMPatchProposalGenerator(provider).generate(make_plan(), make_revision())

    assert requirement_error.value.path == "/output"
    assert plan_error.value.path == "/output"
    assert patch_error.value.path == "/output"
