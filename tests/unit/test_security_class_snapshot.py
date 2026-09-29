"""Unit tests for the TEMPORARY _security_class_snapshot enrichment
scaffolding (see that module's docstring for the full removal checklist)."""

from __future__ import annotations

import json

import pytest

from younit import _security_class_snapshot as mod


@pytest.fixture(autouse=True)
def _clear_snapshot_cache():
    mod._load_snapshot.cache_clear()
    yield
    mod._load_snapshot.cache_clear()


def _write_snapshot(tmp_path, monkeypatch, payload):
    path = tmp_path / "security_classes_snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(mod, "_SNAPSHOT_PATH", path)


class TestGetSecurityClass:
    def test_known_stock_id_resolves_id_and_name(self, tmp_path, monkeypatch):
        _write_snapshot(
            tmp_path,
            monkeypatch,
            {
                "captured_at_utc": "2026-09-29T00:00:00+00:00",
                "stocks": {
                    "101": {"security_class_id": 1, "security_class_name": "LocalSecurity_IN"}
                },
            },
        )

        class_id, class_name = mod.get_security_class(101)

        assert class_id == 1
        assert class_name == "LocalSecurity_IN"

    def test_unknown_stock_id_returns_none_none(self, tmp_path, monkeypatch):
        _write_snapshot(
            tmp_path,
            monkeypatch,
            {"captured_at_utc": "2026-09-29T00:00:00+00:00", "stocks": {}},
        )

        assert mod.get_security_class(999999) == (None, None)

    def test_none_stock_id_returns_none_none(self, tmp_path, monkeypatch):
        _write_snapshot(tmp_path, monkeypatch, {"captured_at_utc": None, "stocks": {}})

        assert mod.get_security_class(None) == (None, None)

    def test_missing_snapshot_file_falls_back_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "_SNAPSHOT_PATH", tmp_path / "does_not_exist.json")

        assert mod.get_security_class(101) == (None, None)
        assert mod.snapshot_captured_at() is None


class TestSnapshotCapturedAt:
    def test_returns_timestamp_from_file(self, tmp_path, monkeypatch):
        _write_snapshot(
            tmp_path,
            monkeypatch,
            {"captured_at_utc": "2026-09-29T12:00:00+00:00", "stocks": {}},
        )

        assert mod.snapshot_captured_at() == "2026-09-29T12:00:00+00:00"
