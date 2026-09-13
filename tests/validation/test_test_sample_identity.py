"""Test sample identification and the space group / unit cell checks.

Why this exists: the report used to present ISa and Rmeas as beamline quality
with no indication of whether the indexing had succeeded. On 2026-08-11 the
reported dataset indexed as space group 3 instead of 89 with a 52% cell
deviation, and the report showed ISa 3.51 and Rmeas 0.161 - which describe a
failed indexing, not a degraded beamline.
"""

import glob
import json
import logging
import os
import re
import statistics

import pytest

from conftest import REPO_ROOT, load_module_yaml


class Sampler:
    def __init__(self):
        self.log = logging.getLogger("sample-tests")


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
            setattr(Sampler, name, value)


_bind()


@pytest.fixture
def sampler():
    return Sampler()


@pytest.fixture(scope="module")
def registry():
    return load_module_yaml("TestCrystal")["test_samples"]


@pytest.fixture(scope="module")
def rules():
    return load_module_yaml("TestCrystal")["assessment_rules"]


# --------------------------------------------------------------------------
# Identification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "masterfile,expected",
    [
        # The name lives in a directory ...
        (
            "/dls/i04/data/2026/cm44138-3/20260811/SeThau2/_SeThau2_1_master.h5",
            "thaumatin",
        ),
        (
            "/dls/i04/data/2026/cm/20260729/TestThaumatin/Sethau4/TestThaumatin_Sethau4_1_master.h5",
            "thaumatin",
        ),
        # ... or in the filename, with a trailing number.
        (
            "/dls/i04/data/2026/cm/processed/TestInsulin/TestInsulin_6_1_master.h5",
            "insulin",
        ),
        ("/dls/i04/data/2026/cm/TestLysozyme/lyso3_1_master.h5", "lysozyme"),
        (
            "/dls/i04/data/2026/cm/testCarbonicAnhydrase/ca_1_master.h5",
            "carbonic_anhydrase",
        ),
        ("/dls/i04/data/2026/cm/TestThermolysin/th_1_master.h5", "thermolysin"),
        (
            "/dls/i04/data/2026/cm/testGlucoseIsomerase/gi_1_master.h5",
            "glucose_isomerase",
        ),
    ],
)
def test_sample_identified_from_the_path(sampler, registry, masterfile, expected):
    assert sampler.identify_test_sample(masterfile, registry) == expected


def test_an_unrecognised_sample_is_not_guessed(sampler, registry):
    """Better to report nothing than to check against the wrong protein."""
    assert (
        sampler.identify_test_sample(
            "/dls/i04/data/x/high_res_100_1_3_master.h5", registry
        )
        is None
    )
    assert sampler.identify_test_sample(None, registry) is None


def test_identification_is_case_insensitive(sampler, registry):
    for variant in ("SeThau2", "sethau2", "SETHAU2"):
        path = f"/dls/i04/data/2026/cm/{variant}/_{variant}_1_master.h5"
        assert sampler.identify_test_sample(path, registry) == "thaumatin"


# --------------------------------------------------------------------------
# Space group and cell
# --------------------------------------------------------------------------


THAUMATIN = "/dls/i04/data/2026/cm/20260811/SeThau2/_SeThau2_1_master.h5"


def test_the_expected_space_group_is_reported_alongside_the_observed(sampler, registry):
    got = sampler.check_test_sample(
        THAUMATIN, registry, 89, [57.9, 57.9, 150.2, 90, 90, 90]
    )
    assert got["Test_sample"] == "Thaumatin"
    assert got["Space_group"] == 89
    assert got["Space_group_expected"] == 89
    assert got["Space_group_match"] == "yes"
    assert got["Unit_cell_deviation_pct"] < 0.5


def test_the_2026_08_11_misindexing_is_caught(sampler, registry, assessor, rules):
    """The real case. That day's report showed ISa 3.51 and Rmeas 0.161, which
    read as a dead crystal or a bad beamline. The dataset had in fact indexed as
    space group 3 with a cell half the size, so the statistics were describing a
    failed indexing.
    """
    got = sampler.check_test_sample(
        THAUMATIN, registry, 3, [49.6, 50.2, 75.4, 90, 96.8, 90]
    )
    assert got["Space_group_match"] == "no"
    assert got["Unit_cell_deviation_pct"] > 20

    assessed = assessor.assess_parameters(got, rules, None, where="TestCrystal")
    assert assessed["Space_group_match"]["status"] == "danger"
    assert assessed["Unit_cell_deviation_pct"]["status"] == "danger"


def test_ordinary_crystal_to_crystal_cell_variation_passes(assessor, rules):
    """A percent or two between crystals of the same protein is normal."""
    assert (
        assessor.assess_less_than(0.5, rules["Unit_cell_deviation_pct"]["limits"])
        == "good"
    )
    assert (
        assessor.assess_less_than(2.0, rules["Unit_cell_deviation_pct"]["limits"])
        == "good"
    )
    assert (
        assessor.assess_less_than(3.0, rules["Unit_cell_deviation_pct"]["limits"])
        == "warning"
    )
    assert (
        assessor.assess_less_than(50.0, rules["Unit_cell_deviation_pct"]["limits"])
        == "danger"
    )


def test_an_unknown_sample_is_recorded_but_not_judged(sampler, registry):
    """Not recognised is not the same as not reported.

    The space group and cell are exactly what someone needs in order to add the
    sample to the registry, so they are kept. What is not kept is any verdict,
    because there is nothing to judge them against.
    """
    got = sampler.check_test_sample(
        "/dls/i04/data/x/somethingnew_1_master.h5", registry, 96, [80.0, 80.0, 40.0]
    )
    assert got["Test_sample_identified"] == "no"
    assert got["Test_sample"] == "not recognised"
    assert got["Space_group"] == 96, "the observation is kept"
    assert "80.0" in got["Unit_cell"]
    assert "Space_group_match" not in got, "nothing to check it against"
    assert "Unit_cell_deviation_pct" not in got


def test_an_unrecognised_sample_warns_rather_than_alarms(
    assessor, rules, sampler, registry
):
    """A gap in configuration, not a fault on the beamline - but it stays visible
    in every report until someone adds the sample or fixes the naming."""
    got = sampler.check_test_sample(
        "/dls/i04/data/x/newthing_1_master.h5", registry, 96, [80.0, 80.0, 40.0]
    )
    assessed = assessor.assess_parameters(got, rules, None, where="TestCrystal")
    assert assessed["Test_sample_identified"]["status"] == "warning"


def test_a_recognised_sample_ticks(assessor, rules, sampler, registry):
    got = sampler.check_test_sample(
        THAUMATIN, registry, 89, [57.9, 57.9, 150.2, 90, 90, 90]
    )
    assessed = assessor.assess_parameters(got, rules, None, where="TestCrystal")
    assert assessed["Test_sample_identified"]["status"] == "good"


# --------------------------------------------------------------------------
# The fingerprint cross-check: right sample, or was it mislabelled?
# --------------------------------------------------------------------------


def test_a_mislabelled_sample_is_flagged(sampler, registry):
    """The path says thaumatin, but the cell is insulin's.

    Someone mounted the wrong crystal or labelled it wrongly. The data itself is
    fine, so users still get their normal email - this is for staff.
    """
    got = sampler.check_test_sample(
        THAUMATIN, registry, 197, [77.9, 77.9, 77.9, 90, 90, 90]
    )
    assert got["Sample_looks_like"] == "Insulin"
    assert got["Space_group_match"] == "no"


def test_the_right_sample_is_not_flagged_as_mislabelled(sampler, registry):
    got = sampler.check_test_sample(
        THAUMATIN, registry, 89, [57.9, 57.9, 150.2, 90, 90, 90]
    )
    assert "Sample_looks_like" not in got


def test_a_misindexing_is_not_reported_as_a_mislabelling(sampler, registry):
    """A cell matching nothing is a failed indexing, which the space group check
    already covers. It must not be dressed up as the wrong sample."""
    got = sampler.check_test_sample(
        THAUMATIN, registry, 3, [49.6, 50.2, 75.4, 90, 96.8, 90]
    )
    assert got["Space_group_match"] == "no"
    assert "Sample_looks_like" not in got


def test_identity_is_never_inferred_from_the_fingerprint_alone(sampler, registry):
    """Inferring identity from the space group would be circular: a thaumatin
    that indexed as P 1 would read as "unknown sample" rather than "thaumatin
    indexed wrong", losing the signal on exactly the days it matters. The path
    stays the primary key because it is independent of the processing."""
    got = sampler.check_test_sample(
        "/dls/i04/data/x/unlabelled_1_master.h5", registry, 197, [77.9, 77.9, 77.9]
    )
    assert (
        got["Test_sample"] == "not recognised"
    ), "a perfect insulin fingerprint must not silently become an identification"


# --------------------------------------------------------------------------
# The registry itself
# --------------------------------------------------------------------------


def test_registry_covers_the_proteins_actually_in_use(registry):
    """Measured over the processing archive: six proteins in rotation."""
    assert set(registry) >= {
        "thaumatin",
        "insulin",
        "lysozyme",
        "carbonic_anhydrase",
        "thermolysin",
        "glucose_isomerase",
    }


@pytest.mark.parametrize(
    "name",
    [
        "thaumatin",
        "insulin",
        "lysozyme",
        "carbonic_anhydrase",
        "thermolysin",
        "glucose_isomerase",
    ],
)
def test_every_entry_is_complete(registry, name):
    entry = registry[name]
    assert entry["protein"], f"{name} needs a display name for the report and email"
    assert entry["aliases"], f"{name} needs at least one alias to be identifiable"
    assert entry["space_group_number"]
    assert len(entry["unit_cell"]) == 6


def test_no_two_samples_share_an_alias(registry):
    """An ambiguous alias would identify the wrong protein, silently."""
    seen = {}
    for name, entry in registry.items():
        for alias in entry["aliases"]:
            assert (
                alias not in seen
            ), f"{alias!r} claimed by both {seen.get(alias)} and {name}"
            seen[alias] = name


def test_the_registry_is_beamline_independent():
    """The proteins are the same anywhere, so this must not be in the i04 file."""
    shared = os.path.join(REPO_ROOT, "modules", "TestCrystal", "TestCrystal.yaml")
    override = os.path.join(REPO_ROOT, "modules", "TestCrystal", "TestCrystal.i04.yaml")
    assert "test_samples:" in open(shared).read()
    assert "test_samples:" not in open(override).read()


# --------------------------------------------------------------------------
# Space groups come in two forms, and the check must handle both
# --------------------------------------------------------------------------


def test_fast_dp_reports_a_point_group_number(sampler, registry):
    """fast_dp assigns 89 for thaumatin, not the 92 of P41212."""
    entry = registry["thaumatin"]
    assert sampler.check_space_group(89, entry) == "yes"
    assert sampler.check_space_group(3, entry) == "no"


def test_xia2_reports_a_full_space_group_name(sampler, registry):
    entry = registry["thaumatin"]
    assert sampler.check_space_group("P 41 21 2", entry, source="dials") == "yes"
    assert sampler.check_space_group("C 2 2 2", entry, source="dials") == "no"


def test_the_point_group_variant_is_accepted(sampler, registry):
    """dials assigns thaumatin P 41 21 2 on some runs and P 4 21 2 on others.

    The second is the point group with the screw axis unresolved - incomplete,
    not wrong - so it must not be flagged. Measured over the archive: 24 runs
    gave P 41 21 2 and 13 gave P 4 21 2.
    """
    assert sampler.check_space_group("P 4 21 2", registry["thaumatin"]) == "yes"
    assert sampler.check_space_group("P 4 2 2", registry["lysozyme"]) == "yes"
    assert sampler.check_space_group("P 1 2 1", registry["carbonic_anhydrase"]) == "yes"


def test_a_failed_indexing_is_still_caught(sampler, registry):
    """P 1 means indexing gave up; it must not be accepted for anything."""
    for name in ("thaumatin", "carbonic_anhydrase", "lysozyme"):
        assert sampler.check_space_group("P 1", registry[name]) == "no"


def test_spacing_does_not_matter(sampler, registry):
    for spelling in ("P 41 21 2", "P41212", "p 41 21 2"):
        assert sampler.check_space_group(spelling, registry["thaumatin"]) == "yes"


def test_a_numeric_string_is_treated_as_a_point_group(sampler, registry):
    """fast_dp's number may arrive as text depending on the parse route."""
    assert sampler.check_space_group("89", registry["thaumatin"]) == "yes"


def test_nothing_is_claimed_without_an_assignment(sampler, registry):
    assert sampler.check_space_group(None, registry["thaumatin"]) is None


def test_every_sample_has_both_forms(registry):
    """Without both, one pipeline's assignment cannot be checked at all."""
    for name, entry in registry.items():
        assert entry.get("space_group_number"), f"{name} has no point group number"
        assert entry.get("space_group"), f"{name} has no full space group"
        assert isinstance(entry.get("accepted_space_groups", []), list)


# --------------------------------------------------------------------------
# The identity check has to be reachable from the module, not just callable
# --------------------------------------------------------------------------


def test_extract_quality_parameters_runs_the_identity_check():
    """The wiring, which is what was missing.

    check_test_sample was built and tested in isolation and never called, so the
    report carried no sample identity and the user email fell back to "reference"
    even for a dataset whose path plainly said thaumatin.

    A second bug sat behind it: parse_fastdp filters its harvest down to the
    reported subset before returning, and Space_group_number and
    Unit_cell_constants are working values rather than report rows - so they were
    parsed and then dropped before the identity check could read them.
    """
    import inspect

    from modules.TestCrystal import QualityControl as qc_module

    source = inspect.getsource(qc_module.QualityControl.extract_quality_parameters)
    assert "check_test_sample" in source, (
        "extract_quality_parameters must run the identity check - it is the only "
        "place that has both the master file path and the registry"
    )
    assert "all_fields=True" in source, (
        "the identity check needs the unfiltered harvest, because "
        "Space_group_number and Unit_cell_constants are not reported rows"
    )


def test_the_module_passes_its_registry_down():
    """TestCrystal holds the registry in its config; the parser needs it."""
    import inspect

    from modules.TestCrystal import TestCrystal as module

    source = inspect.getsource(module.TestCrystal.extract_processing_data)
    assert "test_samples" in source, (
        "TestCrystal must pass its test_samples registry to TestCrystalResults, "
        "or nothing downstream can identify the sample"
    )
