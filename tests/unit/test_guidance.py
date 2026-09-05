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
