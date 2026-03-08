from src.orchestrator.state import PipelineRunState
from src.orchestrator.errors import AgentError, PipelineError


class TestPipelineRunStateCreation:
    def test_create_factory(self):
        state = PipelineRunState.create(run_id="run-001", bundle_key="bundles/test.zip")
        assert state.run_id == "run-001"
        assert state.bundle_key == "bundles/test.zip"
        assert state.status == "pending"
        assert state.kb_id is None
        assert state.current_agent is None
        assert state.artifacts == {}
        assert state.warnings == []
        assert state.error is None
        assert state.started_at != ""
        assert state.completed_at is None
        assert state.agent_durations == {}


class TestStatusTransitions:
    def test_pending_to_running_to_completed(self):
        state = PipelineRunState.create("run-002", "b/test.zip")
        assert state.status == "pending"

        state.mark_running()
        assert state.status == "running"

        state.mark_completed()
        assert state.status == "completed"
        assert state.completed_at is not None

    def test_pending_to_running_to_failed(self):
        state = PipelineRunState.create("run-003", "b/test.zip")
        state.mark_running()

        err = RuntimeError("LLM timeout")
        state.mark_failed("prd_lite", err)
        assert state.status == "failed"
        assert state.completed_at is not None
        assert state.current_agent is None


class TestAgentTracking:
    def test_mark_agent_started(self):
        state = PipelineRunState.create("run-004", "b/test.zip")
        state.mark_running()
        state.mark_agent_started("blueprint_intake")
        assert state.current_agent == "blueprint_intake"

    def test_mark_agent_completed(self):
        state = PipelineRunState.create("run-005", "b/test.zip")
        state.mark_running()
        state.mark_agent_started("blueprint_intake")
        state.mark_agent_completed("blueprint_intake", 12.5, {"inventory": {"site": "example.com"}})

        assert state.current_agent is None
        assert state.agent_durations["blueprint_intake"] == 12.5
        assert "inventory" in state.artifacts

    def test_multiple_agents_accumulate_artifacts(self):
        state = PipelineRunState.create("run-006", "b/test.zip")
        state.mark_running()

        state.mark_agent_started("blueprint_intake")
        state.mark_agent_completed("blueprint_intake", 10.0, {"inventory": "inv_data"})

        state.mark_agent_started("prd_lite")
        state.mark_agent_completed("prd_lite", 5.0, {"prd_md": "# PRD"})

        assert state.artifacts == {"inventory": "inv_data", "prd_md": "# PRD"}
        assert state.agent_durations == {"blueprint_intake": 10.0, "prd_lite": 5.0}


class TestWarningAccumulation:
    def test_warnings_accumulate(self):
        state = PipelineRunState.create("run-007", "b/test.zip")
        state.warnings.append("Missing asset: logo.png")
        state.warnings.append("Unsupported block: custom/widget")
        assert len(state.warnings) == 2
        assert "Missing asset: logo.png" in state.warnings


class TestErrorRecording:
    def test_mark_failed_records_error_dict(self):
        state = PipelineRunState.create("run-008", "b/test.zip")
        state.mark_running()
        state.mark_agent_started("modeling")

        err = ValueError("Invalid block mapping")
        state.mark_failed("modeling", err)

        assert state.error is not None
        assert state.error["agent"] == "modeling"
        assert "Invalid block mapping" in state.error["message"]
        assert isinstance(state.error["traceback"], list)

    def test_mark_failed_clears_current_agent(self):
        state = PipelineRunState.create("run-009", "b/test.zip")
        state.mark_running()
        state.mark_agent_started("theming")
        state.mark_failed("theming", RuntimeError("CSS parse error"))
        assert state.current_agent is None


class TestDurationTracking:
    def test_agent_durations_recorded(self):
        state = PipelineRunState.create("run-010", "b/test.zip")
        state.mark_running()

        state.mark_agent_started("blueprint_intake")
        state.mark_agent_completed("blueprint_intake", 8.2, {})

        state.mark_agent_started("prd_lite")
        state.mark_agent_completed("prd_lite", 3.7, {})

        state.mark_agent_started("modeling")
        state.mark_agent_completed("modeling", 15.1, {})

        assert state.agent_durations == {
            "blueprint_intake": 8.2,
            "prd_lite": 3.7,
            "modeling": 15.1,
        }


class TestAgentError:
    def test_agent_error_attributes(self):
        original = ValueError("bad input")
        err = AgentError(agent_name="importer", message="Content parse failed", original_error=original)
        assert err.agent_name == "importer"
        assert err.message == "Content parse failed"
        assert err.original_error is original
        assert "importer" in str(err)

    def test_agent_error_without_original(self):
        err = AgentError(agent_name="qa", message="Build failed")
        assert err.agent_name == "qa"
        assert err.original_error is None

    def test_agent_error_is_exception(self):
        err = AgentError(agent_name="scaffold", message="Missing manifest")
        assert isinstance(err, Exception)


class TestPipelineError:
    def test_pipeline_error_attributes(self):
        err = PipelineError(message="Bundle not found in Spaces")
        assert err.message == "Bundle not found in Spaces"
        assert "Bundle not found" in str(err)

    def test_pipeline_error_is_exception(self):
        err = PipelineError(message="Invalid config")
        assert isinstance(err, Exception)
