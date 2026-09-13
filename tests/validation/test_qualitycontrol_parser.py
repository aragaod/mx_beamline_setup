"""Parser tests for the TestCrystal processing logs.

The statistics used to be pulled out by fixed character slices - [-6:], [43:48],
[53:58] - so which of the three columns a value came from was invisible from the
code, and a change in fast_dp or aimless output would have produced a wrong
number rather than an error. These tests pin the shell each statistic comes from
against real log excerpts in tests/fixtures/.

The fixtures are the summary blocks from a genuine run (SeThau2, 2026-07-08).
Both logs report Overall | InnerShell | OuterShell.
"""

import logging
import os

import pytest

from conftest import REPO_ROOT

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)


class Parser:
    """The parsing methods, unbound from redis and the beamline library."""

    def __init__(self):
        self.log = logging.getLogger("parser-tests")


def _bind():
    import importlib.util

    path = os.path.join(REPO_ROOT, "modules", "TestCrystal", "QualityControl.py")
    source = open(path).read()
    # Import just the class body we care about, without the module's beamline
    # and pandas imports, which need the full runtime environment.
    namespace = {"os": os, "logging": logging}
    body = source[
        source.index("    OVERALL, INNER_SHELL, OUTER_SHELL") : source.index(
            "    def parse_xia2"
        )
    ]
    exec("class _QC:\n" + body, namespace)
    for name, value in vars(namespace["_QC"]).items():
        if not name.startswith("__"):
            setattr(Parser, name, value)


_bind()


@pytest.fixture
def parser():
    return Parser()


def test_fastdp_statistics_come_from_the_right_shell(parser):
    payload = {}
    parser._parse_shell_table(
        os.path.join(FIXTURES, "fast_dp_summary.log"), Parser.FASTDP_FIELDS, payload
    )
    assert payload["Resolution"] == 1.26  # OuterShell
    assert payload["Rmerge_low_res"] == 0.034  # InnerShell, as the wizard text says
    assert payload["Completeness"] == 99.8  # Overall
    assert payload["CChalf"] == 1.000  # Overall
    assert payload["IoverSigma"] == 24.70  # Overall


def test_aimless_statistics_come_from_the_right_shell(parser):
    payload = {}
    parser._parse_shell_table(
        os.path.join(FIXTURES, "aimless_summary.log"), Parser.AIMLESS_FIELDS, payload
    )
    assert payload["Aimless_Rmeas_low_res"] == 0.036  # InnerShell - the ISPyB number
    assert payload["Aimless_Resolution"] == 1.26  # Overall
    assert payload["Aimless_CChalf"] == 1.000
    assert payload["Aimless_Completeness"] == 99.8
    assert payload["Aimless_Rmerge_low_res"] == 0.034


def test_rmeas_is_not_confused_with_rmerge_or_rpim(parser):
    """aimless.log carries six R-factor lines whose labels share a prefix.

    'Rmeas (all I+ & I-)' must not be satisfied by 'Rmeas (within I+/I-)',
    'Rmerge (all I+ and I-)' or either Rpim line.
    """
    payload = {}
    parser._parse_shell_table(
        os.path.join(FIXTURES, "aimless_summary.log"), Parser.AIMLESS_FIELDS, payload
    )
    assert payload["Aimless_Rmeas_low_res"] == 0.036
    assert payload["Aimless_Rmeas_low_res"] != 0.009  # Rpim
    assert payload["Aimless_Rmeas_low_res"] != 0.035  # Rmerge (all I+ and I-)


def test_completeness_is_not_taken_from_the_anomalous_line(parser):
    """Both logs carry an 'Anom(alous) completeness' line with different numbers."""
    payload = {}
    parser._parse_shell_table(
        os.path.join(FIXTURES, "aimless_summary.log"), Parser.AIMLESS_FIELDS, payload
    )
    assert payload["Aimless_Completeness"] == 99.8
    payload = {}
    parser._parse_shell_table(
        os.path.join(FIXTURES, "fast_dp_summary.log"), Parser.FASTDP_FIELDS, payload
    )
    assert payload["Completeness"] == 99.8


def test_isa_is_read_from_the_line_below_its_header(parser):
    payload = {}
    parser._parse_isa(os.path.join(FIXTURES, "correct_isa.log"), payload)
    assert payload["ISa"] == 22.99


def test_missing_file_is_a_warning_not_a_crash(parser):
    payload = {}
    parser._parse_shell_table("/nonexistent/fast_dp.log", Parser.FASTDP_FIELDS, payload)
    parser._parse_isa("/nonexistent/CORRECT.LP", payload)
    assert payload == {}


def test_line_with_dashes_instead_of_numbers_is_skipped(parser):
    """'Rmerge in top intensity bin  0.039  -  -' must not yield a value."""
    assert (
        parser._trailing_numbers("Rmerge in top intensity bin  0.039     -         - ")
        is None
    )
    assert parser._trailing_numbers("      Rmerge  0.079  0.034  0.711") == [
        0.079,
        0.034,
        0.711,
    ]


SUMMARY_FIELDS = {
    "ISa",
    "Resolution",
    "Aimless_Rmeas_low_res",
    "CChalf",
    "Completeness",
}


def test_summary_statistics_are_five_distinct_measurements():
    """V10: the report used to show ten summary rows for five measurements.

    Per-image diagnostics (F10) are counted separately - they are additional
    measurements, not duplicates of these.
    """
    reported_summary = SUMMARY_FIELDS & set(Parser.REPORT_FIELDS)
    assert reported_summary == SUMMARY_FIELDS
    assert len(set(Parser.REPORT_FIELDS)) == len(Parser.REPORT_FIELDS)


def test_report_keeps_rmeas_and_drops_the_duplicate_rmerge_rows():
    """Rmeas is the ISPyB number and what the wizard text judges on."""
    assert "Aimless_Rmeas_low_res" in Parser.REPORT_FIELDS
    assert "Rmerge_low_res" not in Parser.REPORT_FIELDS
    assert "Aimless_Rmerge_low_res" not in Parser.REPORT_FIELDS


def test_report_keeps_one_resolution_not_two():
    assert "Resolution" in Parser.REPORT_FIELDS
    assert "Aimless_Resolution" not in Parser.REPORT_FIELDS
