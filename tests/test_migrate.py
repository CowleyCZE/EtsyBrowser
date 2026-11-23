"""Testy migrace starých produktů (bez sítě, v dočasných složkách)."""

import json

import pytest

from automation import migrate_products as mp


@pytest.fixture
def setup(tmp_path, monkeypatch):
    source = tmp_path / "old"
    single = source / "SeAForest"
    single.mkdir(parents=True)
    (single / "Art.png").write_bytes(b"png")
    (single / "Art_mockup1.jpg").write_bytes(b"jpg")
    (single / "x_16x20.jpg").write_bytes(b"jpg")
    (single / "ignored.txt").write_text("x")
    bundle = source / "Bundle_Boho"
    (bundle / "Art_1_Files").mkdir(parents=True)
    (bundle / "Art_1_Files" / "p.jpg").write_bytes(b"jpg")
    (bundle / "Art_1_source.png").write_bytes(b"png")
    (bundle / "showcase_1.jpg").write_bytes(b"jpg")
    (source / "soubor.txt").write_text("není složka")

    monkeypatch.setattr(mp, "_next_sku", lambda kind: f"SP-TEST-01-{kind}")
    return source, tmp_path / "warehouse", tmp_path / "state.json"


def test_plan_detects_kinds_and_skips_plain_files(setup):
    source, _target, state = setup
    plan = {p["folder"]: p for p in mp.plan_migration(str(source), str(state))}
    assert set(plan) == {"SeAForest", "Bundle_Boho"}
    assert plan["SeAForest"]["kind"] == "single" and plan["SeAForest"]["keyword"] == "Forest"
    assert plan["Bundle_Boho"]["kind"] == "bundle" and plan["Bundle_Boho"]["keyword"] == "Boho"
    assert not any(p["already_migrated"] for p in plan.values())


def test_dry_run_changes_nothing(setup):
    source, target, state = setup
    result = mp.run_migration(str(source), str(target), dry_run=True, state_path=str(state))
    assert result["to_migrate"] == 2 and result["dry_run"] is True
    assert not target.exists() and not state.exists()


def test_apply_migrates_once_and_remembers(setup):
    source, target, state = setup
    result = mp.run_migration(str(source), str(target), dry_run=False, state_path=str(state))
    assert (result["singles"], result["bundles"], result["failed"]) == (1, 1, 0)

    single = target / "Singles" / "SP-TEST-01-S_Forest"  # SKU se přiděluje podle typu
    assert (single / "00_Master_Source.png").is_file()
    assert (single / "02_Marketing_Assets" / "01_Mockup.jpg").is_file()
    assert (single / "01_Print_Files" / "x_16x20.jpg").is_file()
    meta = json.loads((single / "03_Metadata" / "listing_data.json").read_text(encoding="utf-8"))
    assert meta["sku"] == "SP-TEST-01-S" and meta["pricing"]["amount"] > 0

    bundle = target / "Bundles" / "SP-TEST-01-B_Boho"
    assert (bundle / "00_Masters" / "Art_A.png").is_file()
    assert (bundle / "01_Print_Files_Ready" / "Art_A" / "p.jpg").is_file()
    assert (bundle / "02_Marketing_Assets" / "01_showcase_1.jpg").is_file()

    assert (source / "SeAForest" / "Art.png").is_file()  # zdroj zůstává nedotčený

    again = mp.run_migration(str(source), str(target), dry_run=False, state_path=str(state))
    assert again["to_migrate"] == 0 and again["skipped"] == 2  # podruhé se nic nekopíruje
    assert len(list((target / "Singles").iterdir())) == 1
