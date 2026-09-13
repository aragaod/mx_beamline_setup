"""Reading fourteen months of stored reports back as a table (F8).

The archive is the only long-baseline measurement of the beamline this group
has, and it accumulated by accident - one report a morning for over a year.
Reading it back is where the questions get answered, so the failure mode that
matters is a quiet one: a parameter that silently drops out of a series, or a
value that is compared against another that means something different.

The correlation and fit are written out rather than imported, so they are tested
against cases with known answers.
"""

import pickle

import pytest

from base.report_archive import (
    ReportArchive,
    linear_fit,
    numeric,
    parse_key,
    pearson,
)


def report(**parameters):
    return {
        "parameters": {
            name: {"value": value, "status": "good"}
            for name, value in parameters.items()
        }
    }


class FakeRedis:
    def __init__(self, fields):
        self.fields = fields

    def hgetall(self, key):
        return {
            name.encode(): (value if isinstance(value, bytes) else pickle.dumps(value))
            for name, value in self.fields.items()
        }


def archive(fields):
    return ReportArchive(FakeRedis(fields), "i04:BeamlineSetup:hash", pickle.loads)


# --------------------------------------------------------------------------
# What is and is not a report
# --------------------------------------------------------------------------


def test_a_report_key_is_recognised():
    assert parse_key("AlignBeam_report_20260831") == ("AlignBeam", "20260831")


@pytest.mark.parametrize(
    "name",
    [
        "AlignBeam_status",
        "AlignBeam_lastrun",
        "directories",
        "AlignBeam_report_2026",  # truncated date
        "AlignBeam_report_20260831_extra",
    ],
)
def test_everything_else_in_the_hash_is_left_alone(name):
    """The hash holds statuses, timestamps and PyQt objects as well as reports."""
    assert parse_key(name) is None


def test_a_report_that_will_not_deserialise_costs_only_itself():
    """One bad report is not a reason to abandon fourteen months of them."""
    store = archive(
        {
            "AlignBeam_report_20260830": b"\x80\x04 not a pickle",
            "AlignBeam_report_20260831": report(FLUX=1.0),
        }
    )
    assert len(store.reports()) == 1


# --------------------------------------------------------------------------
# Reading values back
# --------------------------------------------------------------------------


def test_a_series_comes_back_in_date_order():
    store = archive(
        {
            "AlignBeam_report_20260803": report(FLUX=3.0),
            "AlignBeam_report_20260801": report(FLUX=1.0),
            "AlignBeam_report_20260802": report(FLUX=2.0),
        }
    )
    assert list(store.series("AlignBeam", "FLUX").values()) == [1.0, 2.0, 3.0]


def test_a_value_stored_as_a_display_string_is_still_readable():
    """Reports written before the migration hold '1.234 mm', not 1.234."""
    store = archive({"AlignBeam_report_20260801": report(S4_slits_X="0.834 mm")})
    assert store.series("AlignBeam", "S4_slits_X")["20260801"] == 0.834


def test_an_older_report_holding_the_bare_value_still_reads():
    store = archive({"AlignBeam_report_20260801": {"parameters": {"FLUX": 1.5}}})
    assert store.series("AlignBeam", "FLUX")["20260801"] == 1.5


def test_a_true_or_false_is_not_turned_into_a_number():
    """A feedback loop being on is not a quantity; averaging it means nothing."""
    assert numeric(True) is None
    assert numeric(False) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2.5", 2.5),
        ("-0.449", -0.449),
        ("3.0e10", 3.0e10),
        ("1.234 mm", 1.234),
        ("Open", None),
        ("", None),
        (None, None),
    ],
)
def test_what_counts_as_a_number(raw, expected):
    assert numeric(raw) == expected


def test_a_parameter_missing_on_some_days_just_has_fewer_points():
    store = archive(
        {
            "AlignBeam_report_20260801": report(FLUX=1.0),
            "AlignBeam_report_20260802": report(TRANSMISSION=35.0),
        }
    )
    assert len(store.series("AlignBeam", "FLUX")) == 1


def test_modules_are_not_mixed_up():
    store = archive(
        {
            "AlignBeam_report_20260801": report(FLUX=1.0),
            "TestCrystal_report_20260801": report(FLUX=99.0),
        }
    )
    assert store.series("AlignBeam", "FLUX")["20260801"] == 1.0
    assert store.modules() == ["AlignBeam", "TestCrystal"]


def test_only_parameters_with_enough_history_are_offered_for_plotting():
    store = archive(
        {
            f"AlignBeam_report_2026080{n}": (
                report(FLUX=float(n), ONE_OFF=1.0) if n == 1 else report(FLUX=float(n))
            )
            for n in (1, 2, 3)
        }
    )
    assert store.numeric_parameters("AlignBeam") == ["FLUX"]


# --------------------------------------------------------------------------
# Pairing, which is what the steering question needed
# --------------------------------------------------------------------------


def test_pairing_uses_only_the_days_that_have_both():
    """AlignBeam ran on 201 days and BeamstopAlignment on 110. Comparing them
    without making the overlap explicit is how the question stayed open."""
    store = archive(
        {
            "AlignBeam_report_20260801": report(Machine_X_STEER=1.0),
            "AlignBeam_report_20260802": report(Machine_X_STEER=2.0),
            "AlignBeam_report_20260803": report(Machine_X_STEER=3.0),
            "BeamstopAlignment_report_20260802": report(BS_X_standard=0.5),
            "BeamstopAlignment_report_20260803": report(BS_X_standard=0.6),
        }
    )
    dates, xs, ys = store.paired(
        "AlignBeam", "Machine_X_STEER", "BeamstopAlignment", "BS_X_standard"
    )
    assert dates == ["20260802", "20260803"]
    assert xs == [2.0, 3.0]
    assert ys == [0.5, 0.6]


# --------------------------------------------------------------------------
# The statistics
# --------------------------------------------------------------------------


def test_a_perfect_straight_line_correlates_at_one():
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_a_perfect_inverse_correlates_at_minus_one():
    assert pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_a_flat_series_has_no_correlation_rather_than_a_wrong_one():
    """Division by zero here would otherwise raise in the middle of a scan."""
    assert pearson([1, 2, 3], [5, 5, 5]) is None


def test_too_few_points_is_not_a_correlation():
    assert pearson([1, 2], [1, 2]) is None


def test_a_fit_recovers_a_known_slope_and_intercept():
    slope, intercept = linear_fit([0, 1, 2, 3], [10, 12, 14, 16])
    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(10.0)


def test_a_fit_through_one_x_value_is_refused():
    assert linear_fit([5, 5, 5], [1, 2, 3]) is None


def test_the_known_dose_result_is_reproduced():
    """The hand analysis of Sethau4 gave r = -0.84 and about -0.26 ISa per MGy
    over 17 setups. Same numbers, same answer."""
    dose = [3.2, 9.6, 16.2, 24.2, 30.5, 32.1]
    isa = [41.2, 37.9, 41.0, 38.8, 33.4, 31.3]
    r = pearson(dose, isa)
    slope, _ = linear_fit(dose, isa)
    assert r < -0.8
    assert slope == pytest.approx(-0.26, abs=0.06)
