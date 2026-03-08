from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.adapters.base import PluginAdapter
from src.adapters.registry import default_adapters

# Load the full adapter list once — tests cover whatever the registry contains.
_ALL_ADAPTERS = default_adapters()

# ===========================================================================
# Property 11: Supported plugin adapter coverage
# ===========================================================================

class TestSupportedPluginAdapterCoverage:
    """Every adapter from default_adapters() implements PluginAdapter correctly."""
    # ---- registry-level invariants (deterministic, no Hypothesis needed) ----

    def test_all_adapters_are_plugin_adapter_instances(self):
        """        Every object returned by default_adapters() must be a PluginAdapter.
        """
        for adapter in _ALL_ADAPTERS:
            assert isinstance(adapter, PluginAdapter), (
                f"{type(adapter).__name__} is not a PluginAdapter subclass"
            )

    def test_adapter_count_at_least_15(self):
        """        The registry must contain at least 15 adapters covering all
        Supported_Plugin_Family entries.
        """
        assert len(_ALL_ADAPTERS) >= 15, (
            f"Expected >= 15 adapters, got {len(_ALL_ADAPTERS)}"
        )

    def test_all_plugin_family_values_are_unique(self):
        """        No two adapters may share the same plugin_family identifier.
        """
        families = [a.plugin_family() for a in _ALL_ADAPTERS]
        assert len(families) == len(set(families)), (
            f"Duplicate plugin_family values: {[f for f in families if families.count(f) > 1]}"
        )

    # ---- per-adapter contract checks via st.sampled_from() ----------------

    @given(adapter=st.sampled_from(_ALL_ADAPTERS))
    @settings(max_examples=100)
    def test_plugin_family_returns_nonempty_string(self, adapter: PluginAdapter):
        """        Each adapter must return a non-empty string for plugin_family.
        """
        family = adapter.plugin_family()
        assert isinstance(family, str)
        assert len(family) > 0

    @given(adapter=st.sampled_from(_ALL_ADAPTERS))
    @settings(max_examples=100)
    def test_required_artifacts_returns_nonempty_list(self, adapter: PluginAdapter):
        """        Each adapter must return a non-empty list for required_artifacts.
        """
        artifacts = adapter.required_artifacts()
        assert isinstance(artifacts, list)
        assert len(artifacts) > 0
        for artifact in artifacts:
            assert isinstance(artifact, str) and len(artifact) > 0

    @given(adapter=st.sampled_from(_ALL_ADAPTERS))
    @settings(max_examples=100)
    def test_supported_constructs_returns_nonempty_list(self, adapter: PluginAdapter):
        """        Each adapter must return a non-empty list for supported_constructs.
        """
        constructs = adapter.supported_constructs()
        assert isinstance(constructs, list)
        assert len(constructs) > 0
        for construct in constructs:
            assert isinstance(construct, str) and len(construct) > 0

    @given(adapter=st.sampled_from(_ALL_ADAPTERS))
    @settings(max_examples=100)
    def test_unsupported_cases_returns_nonempty_list(self, adapter: PluginAdapter):
        """        Each adapter must return a non-empty list for unsupported_cases.
        """
        cases = adapter.unsupported_cases()
        assert isinstance(cases, list)
        assert len(cases) > 0
        for case in cases:
            assert isinstance(case, str) and len(case) > 0
