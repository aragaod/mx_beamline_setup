"""The redis report migration tool (dev/migrate_redis_reports.py).

Fourteen months of reports predate three changes to how a report is stored: keys
renamed so the shell a statistic comes from is stated, numeric PVs stored as
numbers rather than display strings, and a format_version stamp. Rather than
teach every consumer to read both shapes forever, the history is rewritten once.

Two invariants matter more than the transformation itself:

  * **Statuses are never touched.** What a report said on the day is an audit
    trail of what staff saw and acted on. Analysis recomputes from values.
  * **Nothing that is not a report is unpickled.** The *_lastrun fields hold PyQt
    objects that cannot be read outside the GUI environment. An early draft
    replaced them with None, which would have destroyed the application's own
    state; they are now copied through as raw bytes.
"""

import importlib.util
import os

import pytest

from conftest import REPO_ROOT


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location(
        "migrate_redis_reports",
        os.path.join(REPO_ROOT, "dev", "migrate_redis_reports.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_report():
    """A report in the shape used before 2026-08-31."""
    return {
        "table_title": "Test Crystal Diffraction Statistics",
        "parameters": {
            "masterfile": {"value": "/dls/i04/data/x/_SeThau2_1_master.h5"},
            "ISa": {"value": "  3.51", "status": "danger"},
            "Rmerge": {"value": "0.161", "status": "danger"},
            "Aimless_Rmeas": {"value": "0.205", "status": "danger"},
            "Aimless_Rmerge": {"value": "0.161", "status": "danger"},
        },
    }


# --------------------------------------------------------------------------
# The transformation
# --------------------------------------------------------------------------


def test_keys_are_renamed(migration, legacy_report):
    counters = __import__("collections").Counter()
    out = migration.migrate_report(
        legacy_report, {"Rmerge_low_res", "Rmerge"}, counters
    )
    assert "Rmerge_low_res" in out["parameters"]
    assert "Aimless_Rmeas_low_res" in out["parameters"]
    assert "Aimless_Rmerge_low_res" in out["parameters"]
    assert "Rmerge" not in out["parameters"]


def test_feedback_good_becomes_xbpm2_only(migration):
    """It only ever held XBPM2POSITION_OK - XBPM1 was never read, which was the
    bug. No XBPM1 history exists and none is invented."""
    assert migration.RENAMES["Feedback_good"] == "Feedback_XBPM2_good"


def test_statuses_are_preserved_exactly(migration, legacy_report):
    counters = __import__("collections").Counter()
    out = migration.migrate_report(legacy_report, {"ISa"}, counters)
    assert out["parameters"]["ISa"]["status"] == "danger"
    assert out["parameters"]["Rmerge_low_res"]["status"] == "danger"


def test_numeric_values_become_numbers(migration, legacy_report):
    counters = __import__("collections").Counter()
    out = migration.migrate_report(legacy_report, {"ISa"}, counters)
    assert out["parameters"]["ISa"]["value"] == 3.51
    assert isinstance(out["parameters"]["ISa"]["value"], float)


def test_text_values_are_left_alone(migration, legacy_report):
    """A path is not a number, and neither is an enum label."""
    counters = __import__("collections").Counter()
    out = migration.migrate_report(legacy_report, {"ISa"}, counters)
    assert out["parameters"]["masterfile"]["value"].endswith("_master.h5")


def test_only_parameters_the_yaml_calls_numeric_are_converted(migration):
    """Guards against a future module storing a numeric-looking identifier - a
    puck barcode, say - being silently turned into a float."""
    counters = __import__("collections").Counter()
    report = {"parameters": {"Puck_barcode": {"value": "0012"}}}
    out = migration.migrate_report(report, set(), counters)
    assert out["parameters"]["Puck_barcode"]["value"] == "0012"


def test_the_format_stamp_is_added(migration, legacy_report):
    counters = __import__("collections").Counter()
    out = migration.migrate_report(legacy_report, set(), counters)
    assert out["format_version"] == migration.MIGRATED_FORMAT_VERSION == 1


def test_an_already_current_report_is_left_alone(migration):
    """Reports the application wrote carry version 2 and must not be rewritten."""
    counters = __import__("collections").Counter()
    current = {"format_version": 2, "parameters": {"ISa": {"value": 3.51}}}
    out = migration.migrate_report(current, {"ISa"}, counters)
    assert out is current
    assert counters["already_current"] == 1


def test_the_original_report_is_not_modified(migration, legacy_report):
    counters = __import__("collections").Counter()
    migration.migrate_report(legacy_report, {"ISa"}, counters)
    assert legacy_report["parameters"]["ISa"]["value"] == "  3.51"
    assert "Rmerge" in legacy_report["parameters"]
    assert "format_version" not in legacy_report


# --------------------------------------------------------------------------
# Verification must actually catch things
# --------------------------------------------------------------------------


def test_verification_catches_a_lost_parameter(migration, legacy_report):
    broken = {"parameters": {"ISa": legacy_report["parameters"]["ISa"]}}
    problems = migration.verify({"r": legacy_report}, {"r": broken})
    assert any("lost parameter" in p or "became" in p for p in problems)


def test_verification_catches_a_changed_status(migration, legacy_report):
    tampered = {
        "parameters": {
            name: (dict(entry, status="good") if isinstance(entry, dict) else entry)
            for name, entry in legacy_report["parameters"].items()
        }
    }
    problems = migration.verify({"r": legacy_report}, {"r": tampered})
    assert any("status changed" in p for p in problems)


def test_verification_catches_a_lost_field(migration, legacy_report):
    problems = migration.verify(
        {"a": legacy_report, "b": legacy_report}, {"a": legacy_report}
    )
    assert any("fields lost" in p for p in problems)


def test_a_clean_migration_verifies(migration, legacy_report):
    counters = __import__("collections").Counter()
    names = migration.numeric_parameter_names()
    out = migration.migrate_report(legacy_report, names, counters)
    assert migration.verify({"r": legacy_report}, {"r": out}) == []


# --------------------------------------------------------------------------
# The numeric parameter set comes from the shipped configuration
# --------------------------------------------------------------------------


def test_numeric_names_are_read_from_the_module_yaml(migration):
    names = migration.numeric_parameter_names()
    for expected in ("ISa", "FLUX", "BEAM_SIZE_X", "STUB_X", "Aimless_Rmeas_low_res"):
        assert expected in names, f"{expected} should be treated as numeric"


def test_old_names_are_numeric_too(migration):
    """History holds the pre-rename names, so those must convert as well."""
    names = migration.numeric_parameter_names()
    assert "Aimless_Rmeas" in names
    assert "Rmerge" in names


def test_text_parameters_are_not_in_the_numeric_set(migration):
    names = migration.numeric_parameter_names()
    assert "Feedback_enable" not in names, "an enum label must never become a float"
    assert "Smargon_home" not in names, "a timestamp string must stay a string"
