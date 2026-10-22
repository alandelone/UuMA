from pathlib import Path


def test_legacy_workstation_deployment_stops_before_production_mutations():
    script = (Path(__file__).parents[1] / "scripts/deploy-hermes.ps1").read_text(
        encoding="utf-8"
    )
    guard = script.index('Join-Path $DataDir "wisdom.db.remote-owner.json"')
    assert guard < script.index('$HermesExe = (Resolve-Path')
    assert guard < script.index('foreach ($profile in $profiles)')
    assert "cannot recreate production receivers" in script
