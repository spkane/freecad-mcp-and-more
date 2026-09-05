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
