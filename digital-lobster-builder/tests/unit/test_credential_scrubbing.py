import json

from src.models.deployment_report import DeploymentReport
from src.models.migration_report import (
    ContentTypeMigrationStats,
    MediaMigrationStats,
    MigrationReport,
)
from src.orchestrator.state import PipelineRunState
from src.utils.scrubbing import REDACTED, scrub_credentials


class TestScrubCredentials:
    """Tests for the scrub_credentials utility function."""

    def test_redacts_do_token(self):
        data = {"do_token": "dop_v1_abc123"}
        assert scrub_credentials(data) == {"do_token": REDACTED}

    def test_redacts_strapi_admin_password(self):
        data = {"strapi_admin_password": "supersecret"}
        assert scrub_credentials(data) == {"strapi_admin_password": REDACTED}

    def test_redacts_strapi_api_token(self):
        data = {"strapi_api_token": "tok_xyz"}
        assert scrub_credentials(data) == {"strapi_api_token": REDACTED}

    def test_redacts_ssh_private_key_by_key(self):
        data = {"ssh_private_key": "key-content"}
        assert scrub_credentials(data) == {"ssh_private_key": REDACTED}

    def test_redacts_generic_password_key(self):
        data = {"db_password": "pass123"}
        assert scrub_credentials(data) == {"db_password": REDACTED}

    def test_redacts_generic_token_key(self):
        data = {"auth_token": "bearer_abc"}
        assert scrub_credentials(data) == {"auth_token": REDACTED}

    def test_redacts_generic_secret_key(self):
        data = {"client_secret": "sec_xyz"}
        assert scrub_credentials(data) == {"client_secret": REDACTED}

    def test_case_insensitive_key_matching(self):
        data = {"DO_TOKEN": "abc", "Api_Token": "xyz"}
        result = scrub_credentials(data)
        assert result["DO_TOKEN"] == REDACTED
        assert result["Api_Token"] == REDACTED

    def test_redacts_ssh_key_in_string_value(self):
        ssh_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        data = {"some_field": ssh_key}
        assert scrub_credentials(data) == {"some_field": REDACTED}

    def test_preserves_non_sensitive_data(self):
        data = {"name": "test", "count": 42, "active": True}
        assert scrub_credentials(data) == data

    def test_recursive_nested_dict(self):
        data = {"outer": {"inner": {"api_token": "secret_val"}}}
        result = scrub_credentials(data)
        assert result["outer"]["inner"]["api_token"] == REDACTED

    def test_recursive_list(self):
        data = [{"token": "abc"}, {"safe": "value"}]
        result = scrub_credentials(data)
        assert result[0]["token"] == REDACTED
        assert result[1]["safe"] == "value"

    def test_mixed_nested_structure(self):
        data = {
            "results": [
                {"name": "ok", "password": "hidden"},
                {"data": "-----BEGIN OPENSSH PRIVATE KEY-----\nblah"},
            ],
            "count": 2,
        }
        result = scrub_credentials(data)
        assert result["results"][0]["password"] == REDACTED
        assert result["results"][1]["data"] == REDACTED
        assert result["count"] == 2

    def test_primitives_pass_through(self):
        assert scrub_credentials(42) == 42
        assert scrub_credentials(True) is True
        assert scrub_credentials(None) is None
        assert scrub_credentials("normal string") == "normal string"

    def test_empty_structures(self):
        assert scrub_credentials({}) == {}
        assert scrub_credentials([]) == []


class TestPipelineRunStateSafeDict:
    """Tests for PipelineRunState.to_safe_dict()."""

    def test_scrubs_artifacts(self):
        state = PipelineRunState(
            run_id="r1",
            bundle_key="b1",
            artifacts={"strapi_api_token": "tok_secret", "output_dir": "/tmp"},
        )
        safe = state.to_safe_dict()
        assert safe["artifacts"]["strapi_api_token"] == REDACTED
        assert safe["artifacts"]["output_dir"] == "/tmp"

    def test_scrubs_deployment_report(self):
        state = PipelineRunState(
            run_id="r1",
            bundle_key="b1",
            deployment_report={"url": "https://example.com", "api_token": "secret"},
        )
        safe = state.to_safe_dict()
        assert safe["deployment_report"]["api_token"] == REDACTED
        assert safe["deployment_report"]["url"] == "https://example.com"

    def test_scrubs_error_traceback_with_credentials(self):
        state = PipelineRunState(
            run_id="r1",
            bundle_key="b1",
            error={
                "agent": "provisioner",
                "message": "failed",
                "traceback": ["line1"],
                "do_token": "dop_v1_leaked",
            },
        )
        safe = state.to_safe_dict()
        assert safe["error"]["do_token"] == REDACTED
        assert safe["error"]["agent"] == "provisioner"

    def test_scrubs_ssh_key_in_artifacts(self):
        state = PipelineRunState(
            run_id="r1",
            bundle_key="b1",
            artifacts={"key_content": "-----BEGIN RSA PRIVATE KEY-----\ndata"},
        )
        safe = state.to_safe_dict()
        assert safe["artifacts"]["key_content"] == REDACTED

    def test_none_fields_not_scrubbed(self):
        state = PipelineRunState(run_id="r1", bundle_key="b1")
        safe = state.to_safe_dict()
        assert safe["error"] is None
        assert safe["deployment_report"] is None

    def test_safe_dict_does_not_contain_credentials_in_json(self):
        state = PipelineRunState(
            run_id="r1",
            bundle_key="b1",
            artifacts={
                "do_token": "dop_v1_abc",
                "strapi_admin_password": "admin123",
                "strapi_api_token": "tok_xyz",
                "ssh_data": "-----BEGIN EC PRIVATE KEY-----\nblob",
            },
        )
        json_output = json.dumps(state.to_safe_dict())
        assert "dop_v1_abc" not in json_output
        assert "admin123" not in json_output
        assert "tok_xyz" not in json_output
        assert "-----BEGIN" not in json_output


class TestMigrationReportSafeDict:
    """Tests for MigrationReport.to_safe_dict()."""

    def test_safe_dict_scrubs_injected_credentials(self):
        report = MigrationReport(
            content_stats=[
                ContentTypeMigrationStats(
                    content_type="post",
                    total=10,
                    succeeded=10,
                    failed=0,
                    skipped=0,
                    failed_entries=[],
                )
            ],
            media_stats=MediaMigrationStats(total=5, succeeded=5, failed=0, failed_urls=[]),
            taxonomy_terms_created=3,
            menu_entries_created=1,
            total_entries_succeeded=10,
            total_entries_failed=0,
            total_entries_skipped=0,
            warnings=["some warning"],
        )
        safe = report.to_safe_dict()
        # Normal data preserved
        assert safe["taxonomy_terms_created"] == 3
        assert safe["content_stats"][0]["content_type"] == "post"


class TestDeploymentReportSafeDict:
    """Tests for DeploymentReport.to_safe_dict()."""

    def test_safe_dict_preserves_normal_fields(self):
        report = DeploymentReport(
            live_site_url="https://example.com",
            strapi_admin_url="https://example.com/admin",
            droplet_ip="1.2.3.4",
            deployment_timestamp="2024-01-01T00:00:00Z",
            build_duration_seconds=120.5,
            files_deployed=42,
            homepage_status=200,
            sample_page_status=200,
            webhook_registered=True,
        )
        safe = report.to_safe_dict()
        assert safe["live_site_url"] == "https://example.com"
        assert safe["files_deployed"] == 42
        assert safe["webhook_registered"] is True
