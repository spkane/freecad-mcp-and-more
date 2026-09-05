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
