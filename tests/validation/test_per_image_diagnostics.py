"""Per-image diagnostics from INTEGRATE.LP (F10).

The design decision these tests protect: the metric for the per-image scale is
the *step* between adjacent windows, not the deviation from the median.

Measured across 55 real datasets spanning many dates and crystals, the median
dataset already has a maximum scale deviation of 16% and a fifth of its images
sit more than 10% off the median, because the scale swings as absorption changes
with the crystal's rotation. Deviation therefore does not discriminate. Absorption
is smooth, so it produces large excursions out of small steps; a beam dump or a
shutter glitch is a discontinuity and produces a large step. Median step across
those 55 datasets is 2.4%, p90 4.0%.
"""

import logging
import os
import re
import statistics

import pytest

from conftest import REPO_ROOT, load_module_yaml

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)


class Diagnostics:
    def __init__(self):
        self.log = logging.getLogger("f10-tests")


def _bind():
    source = open(
        os.path.join(REPO_ROOT, "modules", "TestCrystal", "QualityControl.py")
    ).read()
    namespace = {"os": os, "re": re, "statistics": statistics, "logging": logging}
    body = source[
        source.index("    # ---- per-image diagnostics") : source.index(
            "    def parse_fastdp"
        )
    ]
    exec("class _QC:\n" + body, namespace)
    for name, value in vars(namespace["_QC"]).items():
        if not name.startswith("__"):
            setattr(Diagnostics, name, value)


_bind()

SYNTHETIC = os.path.join(FIXTURES, "integrate_synthetic.log")


@pytest.fixture
def diagnostics():
    return Diagnostics()


def test_one_row_per_image_is_parsed(diagnostics):
    rows = diagnostics._parse_per_image(SYNTHETIC)
    assert len(rows) == 720
    assert [r[0] for r in rows] == list(range(1, 721))


def test_a_decoy_ten_column_table_is_not_read_as_images(diagnostics):
    """INTEGRATE.LP holds other ten-column tables; only the image block counts."""
    rows = diagnostics._parse_per_image(SYNTHETIC)
    assert all(1 <= row[0] <= 720 for row in rows)
    assert len(rows) == len(set(row[0] for row in rows))


def test_a_smooth_absorption_swing_is_not_flagged(diagnostics):
    """The whole point: a large excursion made of small steps must stay quiet."""
    import math

    # One full absorption cycle across a 720-image sweep, which is the rate a
    # real rotation shows. A cycle compressed into far fewer images would step
    # steeply between windows and rightly be flagged.
    smooth = [1.0 + 0.12 * math.sin(2 * math.pi * i / 720) for i in range(720)]
    deviation = (
        max(abs(v - statistics.median(smooth)) for v in smooth)
        / statistics.median(smooth)
        * 100
    )
    step, _ = diagnostics._scale_step(smooth)
    assert deviation > 10, "the fixture must actually contain a large excursion"
    assert step < 4.0, "a smooth swing must not look like an event"


def test_a_discontinuity_is_flagged_and_located(diagnostics):
    rows = diagnostics._parse_per_image(SYNTHETIC)
    step, index = diagnostics._scale_step([r[1] for r in rows])
    assert step > 10, "a 20% step must be reported"
    assert index is not None
    assert 460 <= rows[index][0] <= 540, "and reported near where it happened"


def test_step_is_none_when_there_are_too_few_images(diagnostics):
    step, index = diagnostics._scale_step([1.0] * 10)
    assert step is None and index is None


def test_block_deviations_are_parsed(diagnostics):
    spot, spindle = diagnostics._parse_block_deviations(SYNTHETIC)
    assert max(spot) == 0.91
    assert max(spindle) == 0.22


def test_missing_file_yields_no_diagnostics(diagnostics):
    assert diagnostics.parse_per_image_diagnostics("/nonexistent") == {}


def test_where_string_names_images_and_phi(diagnostics, tmp_path):
    import shutil

    fast_dp = tmp_path / "fast_dp"
    fast_dp.mkdir()
    shutil.copy(SYNTHETIC, fast_dp / "INTEGRATE.LP")
    payload = diagnostics.parse_per_image_diagnostics(str(tmp_path), oscillation=0.1)
    assert "images" in payload["Scale_step_at"]
    assert "phi" in payload["Scale_step_at"]


# --------------------------------------------------------------------------
# The thresholds, against the shipped YAML
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rules():
    return load_module_yaml("TestCrystal")["assessment_rules"]


@pytest.mark.parametrize(
    "name,typical,bad",
    [
        ("Scale_step_pct", 2.4, 12.0),
        ("Rmerge_worst_batch_ratio", 1.27, 6.0),
        ("Spot_prediction_sd_px", 0.60, 1.50),
        ("Goniometer_speed_sd_deg", 0.11, 0.60),
    ],
)
def test_thresholds_pass_typical_and_fail_bad(assessor, rules, name, typical, bad):
    """`typical` is the measured median across 55 real datasets."""
    assert assessor.assess_less_than(typical, rules[name]["limits"]) == "good"
    assert assessor.assess_less_than(bad, rules[name]["limits"]) == "danger"


# --------------------------------------------------------------------------
# The location is only shown when it points at something
# --------------------------------------------------------------------------


def _assess(assessor, rules, raw):
    from modules.TestCrystal.TestCrystal import TestCrystal

    assessed = assessor.assess_parameters(raw, rules, None, where="TestCrystal")
    TestCrystal._hide_locations_that_point_at_nothing(assessed)
    return assessed


def test_the_location_is_hidden_when_the_step_is_unremarkable(assessor, rules):
    """A green step with an image range beside it invites the operator to go and
    look at nothing."""
    assessed = _assess(
        assessor,
        rules,
        {"Scale_step_pct": 2.94, "Scale_step_at": "images 3051-3076"},
    )
    assert assessed["Scale_step_pct"]["status"] == "good"
    assert assessed["Scale_step_at"].get("hidden") is True


@pytest.mark.parametrize("step,expected", [(5.0, "warning"), (12.0, "danger")])
def test_the_location_is_shown_when_there_is_something_to_look_at(
    assessor, rules, step, expected
):
    assessed = _assess(
        assessor, rules, {"Scale_step_pct": step, "Scale_step_at": "images 1336-1361"}
    )
    assert assessed["Scale_step_pct"]["status"] == expected
    assert not assessed["Scale_step_at"].get("hidden")


def test_the_location_is_still_stored_when_hidden(assessor, rules):
    """Hidden means kept out of the report, not dropped - the trend analysis
    wants it either way, and it costs nothing in redis."""
    assessed = _assess(
        assessor,
        rules,
        {"Scale_step_pct": 2.94, "Scale_step_at": "images 3051-3076"},
    )
    assert assessed["Scale_step_at"]["value"] == "images 3051-3076"
