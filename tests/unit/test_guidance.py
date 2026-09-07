"""Tests for guidance loading."""

import pytest

from freecad_mcp.guidance import GUIDE_TOPICS, load_guide


class TestGuideTopics:
    """Tests for the progressive guide topic set."""

    def test_topics_are_the_seven_documented_ones(self):
        """The topic set matches the design document exactly."""
        assert GUIDE_TOPICS == (
            "brief",
            "visual-evidence",
            "parameters",
            "features",
            "variants",
            "repair",
            "delivery",
        )

    @pytest.mark.parametrize("topic", GUIDE_TOPICS)
    def test_every_topic_loads_non_empty_markdown(self, topic):
        """Each advertised topic resolves to a real document."""
        content = load_guide(topic)
        assert content.startswith("# ")
        assert len(content) > 200

    def test_unknown_topic_raises_key_error(self):
        """An unregistered topic name is a programming error, not a fallback."""
        with pytest.raises(KeyError, match="unknown guide topic"):
            load_guide("nonexistent")


class TestGuideContent:
    """Each topic document must carry the rules the core file promises."""

    @pytest.mark.parametrize(
        ("topic", "required"),
        [
            ("brief", "assumption"),
            ("visual-evidence", "capture_feature_view"),
            ("parameters", "App::VarSet"),
            ("features", "datum"),
            ("variants", "one governing"),
            ("repair", "STALE_REVISION"),
            ("delivery", "manifest"),
        ],
    )
    def test_topic_carries_its_defining_rule(self, topic, required):
        """A topic document without its defining rule is not the document."""
        assert required in load_guide(topic)

    def test_visual_evidence_forbids_describing_unseen_images(self):
        """The Stage C failure mode is named explicitly."""
        content = load_guide("visual-evidence")
        assert "did not receive" in content

    def test_repair_names_both_error_codes(self):
        """Both observed rejection codes are covered."""
        content = load_guide("repair")
        assert "VALIDATION_FAILED" in content
        assert "STALE_REVISION" in content


class TestCoreGuide:
    """The core is what every session receives as MCP instructions."""

    def test_core_points_at_every_topic(self):
        """A topic nobody is told about will never be read."""
        from freecad_mcp.guidance import GUIDE_TOPICS, PARAMETRIC_PARTS_GUIDANCE

        for topic in GUIDE_TOPICS:
            assert f"freecad://guide/{topic}" in PARAMETRIC_PARTS_GUIDANCE

    def test_core_points_at_no_unregistered_topic(self):
        """Every pointer in the core resolves to a real topic."""
        import re

        from freecad_mcp.guidance import GUIDE_TOPICS, PARAMETRIC_PARTS_GUIDANCE

        referenced = set(
            re.findall(r"freecad://guide/([a-z-]+)", PARAMETRIC_PARTS_GUIDANCE)
        )
        assert referenced == set(GUIDE_TOPICS)

    def test_core_states_the_floors(self):
        """The rules that never scale down are stated in the always-on text."""
        from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE

        for rule in [
            "FullyConstrained",
            "require_single_solid=true",
            "before any refinement",
            "capture_feature_view",
            "warnings",
        ]:
            assert rule in PARAMETRIC_PARTS_GUIDANCE

    def test_core_stays_compact(self):
        """The core is a spine, not the whole methodology."""
        from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE

        assert len(PARAMETRIC_PARTS_GUIDANCE.splitlines()) <= 130


class TestRequiredWorkflowParsing:
    """The workflow served to clients is read from the guide, not restated."""

    def test_steps_match_the_guides_ordered_list(self):
        """Every parsed step is text that actually appears in the guide."""
        import re

        from freecad_mcp.guidance import (
            PARAMETRIC_PARTS_GUIDANCE,
            REQUIRED_WORKFLOW_STEPS,
        )

        collapsed = re.sub(r"\s+", " ", PARAMETRIC_PARTS_GUIDANCE)
        assert len(REQUIRED_WORKFLOW_STEPS) == 12
        for step in REQUIRED_WORKFLOW_STEPS:
            assert step in collapsed

    def test_first_step_classifies_the_request(self):
        """Ordering is part of the contract, so the first step is pinned."""
        from freecad_mcp.guidance import REQUIRED_WORKFLOW_STEPS

        assert REQUIRED_WORKFLOW_STEPS[0].startswith("Classify the request")

    def test_scaling_rule_opens_the_section(self):
        """The rule that governs how far to scale the protocol is captured."""
        from freecad_mcp.guidance import REQUIRED_WORKFLOW_SCALING_RULE

        assert REQUIRED_WORKFLOW_SCALING_RULE.startswith("Scale depth to the task.")
        assert "floors below apply either way" in REQUIRED_WORKFLOW_SCALING_RULE

    def test_wrapped_lines_join_into_one_step(self):
        """A step wrapped across source lines is one step, not several."""
        from freecad_mcp.guidance import parse_required_workflow

        _rule, steps = parse_required_workflow(
            "## Required Workflow\n"
            "\n"
            "Scale depth to the task.\n"
            "\n"
            "1. First step that runs\n"
            "   onto a second line.\n"
            "1. Second step.\n"
            "\n"
            "## Handoff\n"
            "\n"
            "1. Not a workflow step.\n"
        )
        assert steps == ("First step that runs onto a second line.", "Second step.")

    def test_missing_section_raises_rather_than_serving_nothing(self):
        """A renamed heading must fail loudly, not advertise an empty list."""
        from freecad_mcp.guidance import parse_required_workflow

        with pytest.raises(ValueError, match="no ordered steps found"):
            parse_required_workflow("# Title\n\n## Handoff\n\nNothing ordered here.\n")


class TestDeliveryIsNotOptional:
    """Proving a model is parametric must not depend on being asked.

    A request normally arrives as a sentence of prose refined by conversation,
    not a specification, so guidance gated on "when the brief asks for it"
    never fires. Stage G delivered a model whose `window_count` variable drove
    nothing, and nothing in the workflow would have caught that.
    """

    def test_delivery_does_not_wait_to_be_asked(self):
        delivery = " ".join(load_guide("delivery").split())

        assert "not optional and do not wait to be asked for" in delivery
        assert "only when the brief asks for them" not in delivery

    def test_delivery_requires_flexing_validating_and_looking(self):
        delivery = load_guide("delivery")

        assert "freecad://guide/variants" in delivery
        assert "validate_document(require_single_solid=true)" in delivery
        assert "unused_variables" in delivery
        assert "freecad://guide/visual-evidence" in delivery

    def test_variants_guide_leads_with_the_proof_not_the_task(self):
        """It applies whether or not a request named any variants."""
        variants = " ".join(load_guide("variants").split())

        assert variants.startswith("# Proving The Model Is Parametric")
        assert "whether or not anyone asked for variants" in variants

    def test_variants_guide_names_the_inert_parameter_failure(self):
        """A parameter that recomputes to identical geometry drives nothing.

        `unused_variables` cannot see this one: something does reference it.
        """
        variants = " ".join(load_guide("variants").split())

        assert "Nothing changing at all" in variants

    def test_the_workflow_step_no_longer_defers_to_a_brief(self):
        from freecad_mcp.guidance import (
            PARAMETRIC_PARTS_GUIDANCE,
            parse_required_workflow,
        )

        _rule, steps = parse_required_workflow(PARAMETRIC_PARTS_GUIDANCE)
        proof = [step for step in steps if "Prove the model is parametric" in step]

        assert len(proof) == 1
        assert "do not wait to be asked" in " ".join(proof[0].split())
