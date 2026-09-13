"""The xia2 pipeline parsers (V3b).

These results are deliberately NOT in the daily report. fast_dp is named for
being the fast one and the module runs the moment staff see it finish, so the
xia2 results usually do not exist yet. A missing pipeline is normal here.

They are worth parsing because the pipelines genuinely disagree, and each needs
its own limits: on the 2026-07-08 SeThau2 dataset the high resolution limit was
1.26 A from fast_dp, 1.18 from 3dii and 1.08 from dials, because fast_dp stops
while I/sigma is still high and dials cuts on CC(1/2).
"""

import glob
import json
import logging
import os
import re
import statistics

import pytest

from conftest import REPO_ROOT

FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"
)


class Xia2Parser:
    def __init__(self):
        self.log = logging.getLogger("xia2-tests")


def _bind():
    source = open(
        os.path.join(REPO_ROOT, "modules", "TestCrystal", "QualityControl.py")
    ).read()
    namespace = {
        "os": os,
        "re": re,
        "glob": glob,
        "json": json,
        "statistics": statistics,
        "logging": logging,
    }
    body = source[
        source.index("    OVERALL, INNER_SHELL, OUTER_SHELL") : source.index(
            "    def logging(self, message):"
        )
    ]
    exec("class _QC:\n" + body, namespace)
    for name, value in vars(namespace["_QC"]).items():
        if not name.startswith("__"):
            setattr(Xia2Parser, name, value)


_bind()


@pytest.fixture
def parser():
    return Xia2Parser()


@pytest.mark.parametrize(
    "pipeline,expected_resolution", [("dials", 1.08), ("3dii", 1.18)]
)
def test_resolution_matches_the_published_summary(
    parser, pipeline, expected_resolution
):
    """The value must equal what xia2-summary.dat quotes for the same dataset."""
    got = parser.parse_xia2_pipeline(FIXTURES, pipeline)
    assert got[f"{pipeline}_Resolution"] == expected_resolution


def test_resolution_is_not_the_low_resolution_limit(parser):
    """The trap this pins: in the JSON's "overall" block the min/max names refer
    to *d*, not to d*, so they read inverted against the binned arrays of the
    same names. d_star_sq_min is 0.857769, which is 1.08 A - the HIGH resolution
    limit - while d_star_sq_max is 0.000343, which is 53.99 A. Taking the
    obvious-looking key reports the low resolution limit as the resolution, and
    nothing about the number looks wrong until someone checks it against the
    summary file.
    """
    for pipeline in ("dials", "3dii"):
        resolution = parser.parse_xia2_pipeline(FIXTURES, pipeline)[
            f"{pipeline}_Resolution"
        ]
        assert (
            resolution < 5.0
        ), "a resolution near 54 A is the low limit, not the high one"


def test_the_pipelines_disagree_and_both_are_reported(parser):
    both = parser.parse_xia2(FIXTURES)
    assert both["dials_Resolution"] != both["3dii_Resolution"]
    assert both["dials_Rmeas"] != both["3dii_Rmeas"]


def test_keys_are_prefixed_so_they_cannot_be_confused_with_fast_dp(parser):
    """A dials resolution judged against a fast_dp threshold would be wrong."""
    both = parser.parse_xia2(FIXTURES)
    assert all(key.startswith(("dials_", "3dii_")) for key in both)


def test_spacegroup_is_read_from_the_summary(parser):
    both = parser.parse_xia2(FIXTURES)
    assert both["dials_Spacegroup"] == "P 41 21 2"
    assert both["3dii_Spacegroup"] == "P 1 21 1"


def test_a_pipeline_that_has_not_run_is_not_an_error(parser, tmp_path):
    """The normal case at setup time: fast_dp is done, xia2 is not."""
    assert parser.parse_xia2_pipeline(str(tmp_path), "dials") == {}
    assert parser.parse_xia2(str(tmp_path)) == {}


def test_an_unknown_pipeline_name_is_refused(parser):
    assert parser.parse_xia2_pipeline(FIXTURES, "nonsense") == {}


def test_statistics_come_through_at_full_precision(parser):
    """No column slicing, unlike the fast_dp and aimless log parsers."""
    got = parser.parse_xia2_pipeline(FIXTURES, "dials")
    assert isinstance(got["dials_Rmeas"], float)
    assert len(repr(got["dials_Rmeas"])) > 6, "should not be rounded to three figures"
