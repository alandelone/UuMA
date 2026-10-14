from uuma.honc.life_models import SettingsUpdateRequest
from uuma.honc.life_service import LifeService
from uuma.honc.life_setup import configure, initialize_settings
from uuma.honc.life_store import LifeStore
from uuma.honc.store import HoncStore


def settings_change(service, *, revision, event, patch):
    from datetime import UTC, datetime

    receipt = service.receive_user_message(
        adapter_id="fixture-human",
        source_event_id=event,
        raw_content="修改生活设置",
        received_at=datetime.now(UTC),
        granted_operations=("update_settings",),
    )
    result = service.bind_source(receipt["source_ref"]).update_settings(
        SettingsUpdateRequest(
            request_ref=receipt["request_refs"]["update_settings"],
            source_quote="修改生活设置",
            expected_revision=revision,
            patch=patch,
        )
    )
    assert result.status == "APPLIED"


def service_at(tmp_path):
    return LifeService(
        LifeStore(HoncStore(tmp_path / "honc.db")),
        owner_id="owner",
        profile="honc",
        session_id="authorized-local-setup",
    )


def test_reinstallation_preserves_user_changes_and_original_defaults_receipt(tmp_path):
    service = service_at(tmp_path)
    original = initialize_settings(service)
    assert original["state"] == "INITIALIZED"
    context = service.get_context()
    assert context.data["settings_revision"] == 1
    assert context.data["settings"]["bedtime_fallback_time"] == "21:30"
    settings_change(
        service, revision=1, event="change-after-setup", patch={"bedtime_fallback_time": "22:00"}
    )
    replayed = initialize_settings(service)
    assert replayed["operation_id"] == original["operation_id"]
    assert service.get_context().data["settings_revision"] == 2
    assert service.get_context().data["settings"]["bedtime_fallback_time"] == "22:00"
    with service.store.ledger.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM life_objects WHERE kind IN ('body','habit','diary')"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM life_sources WHERE source_origin='configuration_import'"
            ).fetchone()[0]
            == 1
        )


def test_initial_setup_keeps_already_configured_user_settings(tmp_path):
    service = service_at(tmp_path)
    settings_change(
        service, revision=0, event="before-setup", patch={"wake_fallback_time": "07:30"}
    )
    assert initialize_settings(service)["state"] == "EXISTING_USER_SETTINGS_PRESERVED"
    assert service.get_context().data["settings"]["wake_fallback_time"] == "07:30"


def test_live_permissions_preserve_model_and_exclude_legacy_write_route(tmp_path):
    config = {
        "model": {"default": "fixture-model", "provider": "fixture-provider"},
        "mcp_servers": {"uuma-worker": {}, "honc-execution": {"args": ["-m", "uuma.honc.mcp"]}},
        "platform_toolsets": {
            "cli": ["skills", "file", "cronjob", "terminal"],
            "telegram": ["skills", "kanban", "connections"],
        },
    }
    configure(config, tmp_path / "runtime.json")
    assert config["model"] == {"default": "fixture-model", "provider": "fixture-provider"}
    assert config["platform_toolsets"] == {"cli": ["skills"], "telegram": ["skills"]}
    tools = config["mcp_servers"]["honc-execution"]["tools"]["include"]
    assert "honc_check_habit" not in tools
    assert "honc_record_habit" in tools and "honc_get_life_history" in tools
