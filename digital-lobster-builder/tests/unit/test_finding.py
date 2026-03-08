import pytest
from pydantic import ValidationError

from src.models.finding import Finding, FindingSeverity

class TestFindingSeverity:
    def test_severity_values(self):
        assert FindingSeverity.CRITICAL == "critical"
        assert FindingSeverity.WARNING == "warning"
        assert FindingSeverity.INFO == "info"

    def test_severity_is_str_enum(self):
        assert isinstance(FindingSeverity.CRITICAL, str)

    def test_all_severities(self):
        values = {s.value for s in FindingSeverity}
        assert values == {"critical", "warning", "info"}

class TestFinding:
    def test_create_valid_finding(self):
        f = Finding(
            severity=FindingSeverity.WARNING,
            stage="capability_resolution",
            construct="plugin:unsupported-gallery",
            message="No adapter for plugin family 'gallery'",
            recommended_action="Review plugin manually",
        )
        assert f.severity == FindingSeverity.WARNING
        assert f.stage == "capability_resolution"
        assert f.construct == "plugin:unsupported-gallery"

    def test_severity_from_string(self):
        f = Finding(
            severity="critical",
            stage="parity_qa",
            construct="overall_parity",
            message="Parity score below threshold",
            recommended_action="Review parity failures",
        )
        assert f.severity == FindingSeverity.CRITICAL

    def test_roundtrip_json(self):
        f = Finding(
            severity=FindingSeverity.INFO,
            stage="schema_compiler",
            construct="field:meta_key",
            message="Field inferred as text",
            recommended_action="Verify field type in Strapi",
        )
        data = f.model_dump()
        f2 = Finding(**data)
        assert f == f2

    def test_rejects_empty_stage(self):
        with pytest.raises(ValidationError):
            Finding(
                severity=FindingSeverity.CRITICAL,
                stage="",
                construct="some_construct",
                message="some message",
                recommended_action="do something",
            )

    def test_rejects_empty_construct(self):
        with pytest.raises(ValidationError):
            Finding(
                severity=FindingSeverity.CRITICAL,
                stage="intake",
                construct="",
                message="some message",
                recommended_action="do something",
            )

    def test_rejects_empty_message(self):
        with pytest.raises(ValidationError):
            Finding(
                severity=FindingSeverity.CRITICAL,
                stage="intake",
                construct="some_construct",
                message="",
                recommended_action="do something",
            )

    def test_rejects_empty_recommended_action(self):
        with pytest.raises(ValidationError):
            Finding(
                severity=FindingSeverity.CRITICAL,
                stage="intake",
                construct="some_construct",
                message="some message",
                recommended_action="",
            )

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValidationError):
            Finding(
                severity="fatal",
                stage="intake",
                construct="some_construct",
                message="some message",
                recommended_action="do something",
            )
