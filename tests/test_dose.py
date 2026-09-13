"""Dose in MGy: the arming log reader and the RADDOSE-3D scaling (B2b).

Why the numbers below matter more than usual: a dose figure that is quietly wrong
does not look wrong. It is a plausible number in a column of plausible numbers,
and it gets summed into a crystal's lifetime total and used to decide when to
replace it. So these tests pin the two things that would produce a wrong number
without any visible symptom - the duplicate arming records, and the scaling
arithmetic - and the several ways the calculation can be asked for a dose it has
no business inventing.

No network. The service is stubbed; the real cross-check against it is
`verify_scaling`, run from dev/dose_history.py --verify.
"""

import json

import pytest

from base.dose import (
    DEFAULT_OSCILLATION,
    DoseCalculator,
    DoseUnavailable,
    NOMINAL_FLUX,
)
from base.eiger_log import (
    ACQUIRING_STATE_ID,
    EigerLog,
    crystal_key,
    crystal_name,
    history_for_crystal,
    is_xray_centring,
    mentions_crystal,
)

SCHEMA = [
    "unix_time",
    "state_id",
    "filepath",
    "filename",
    "master_file",
    "state_msg",
    "energy_ev",
    "flux",
    "transmission_pct",
    "acquire_time_s",
    "number_images",
    "beamsize_h_um",
    "beamsize_v_um",
    "full_visit",
    "loaded_puck",
    "loaded_pin",
]

# The real i04 test-crystal sweep of 7 August 2026: 13 keV, 30.13 x 18.68 um,
# 3600 images at 2 ms, 3.0e11 ph/s at 35.6% transmission. It came out at
# 1.25 MGy against the arming log and the live service.
BASE = {
    "unix_time": 1_786_000_000.0,
    "state_id": ACQUIRING_STATE_ID,
    "filepath": "/dls/i04/data/2026/cm44138-3/20260807/TestThaumatin/Sethau4",
    "filename": "TestThaumatin_Sethau4_1",
    "master_file": "/dls/i04/data/2026/cm44138-3/20260807/TestThaumatin/Sethau4/"
    "TestThaumatin_Sethau4_1_master.h5",
    "state_msg": "Acquire",
    "energy_ev": 12999.9,
    "flux": 2.99888e11,
    "transmission_pct": 35.6,
    "acquire_time_s": 0.002,
    "number_images": 3600,
    "beamsize_h_um": 30.13,
    "beamsize_v_um": 18.68,
    "full_visit": "cm44138-3",
    "loaded_puck": 36.0,
    "loaded_pin": 4.0,
}


def entry(**overrides):
    return {**BASE, **overrides}


class FakeRedis:
    def __init__(self, entries, schema=SCHEMA):
        self.schema = schema
        self.entries = entries

    def get(self, key):
        return json.dumps(self.schema).encode() if self.schema else None

    def lrange(self, key, start, end):
        rows = [
            json.dumps([e.get(name) for name in self.schema]).encode()
            for e in self.entries
        ]
        return rows[start : end + 1]


class FakeService:
    """Stands in for RADDOSE-3D, and records exactly what it was asked."""

    def __init__(self, rate=0.017406):
        self.rate = rate
        self.requests = []

    def __call__(self, params):
        self.requests.append(params)
        flux = float(params["flux"])
        seconds = float(params["total_exposure_time"])
        return {"Max Dose": self.rate * (flux / NOMINAL_FLUX) * seconds}


@pytest.fixture
def calculator():
    calc = DoseCalculator(api_url="http://stub")
    service = FakeService()
    calc._get = service
    calc.service = service
    return calc


# --------------------------------------------------------------------------
# Reading the arming log
# --------------------------------------------------------------------------


def test_the_aborted_duplicate_is_not_counted():
    """Every collection appears twice. Summing both doubles the dose."""
    log = EigerLog(FakeRedis([entry(), entry(state_id=10, state_msg="Aborted")]), "i04")
    assert len(log.collections()) == 1


def test_a_record_with_no_master_file_is_not_a_collection():
    log = EigerLog(FakeRedis([entry(master_file="")]), "i04")
    assert log.collections() == []


def test_one_malformed_record_does_not_cost_the_window():
    class Broken(FakeRedis):
        def lrange(self, key, start, end):
            rows = super().lrange(key, start, end)
            return [b"{not json"] + rows

    assert len(EigerLog(Broken([entry()]), "i04").collections()) == 1


def test_the_log_refuses_to_be_read_without_its_schema():
    """Positional access is what the schema exists to prevent."""
    with pytest.raises(LookupError):
        EigerLog(FakeRedis([entry()], schema=None), "i04").collections()


def test_a_column_added_upstream_shifts_nothing():
    """The schema is published with the list precisely so this is safe."""
    schema = ["new_column_first"] + SCHEMA
    rows = [{"new_column_first": "x", **entry()}]
    log = EigerLog(FakeRedis(rows, schema=schema), "i04")
    assert log.collections()[0]["flux"] == BASE["flux"]


def test_the_scan_stops_at_the_time_boundary():
    log = EigerLog(
        FakeRedis([entry(unix_time=2000), entry(unix_time=1000), entry(unix_time=500)]),
        "i04",
    )
    assert len(log.collections(since=900)) == 2


def test_xray_centring_is_recognised_by_its_directory():
    shot = entry(filepath="/dls/i04/data/2026/cm44138-3/xraycentring/Sethau4")
    assert is_xray_centring(shot)
    assert not is_xray_centring(entry())


def test_a_crystal_is_keyed_by_visit_as_well_as_name():
    """Sample names are only unique within a visit; across visits they collide."""
    other_visit = entry(
        full_visit="cm12345-1",
        master_file="/dls/i04/data/2026/cm12345-1/20260807/TestThaumatin/Sethau4/x.h5",
    )
    assert crystal_key(entry()) != crystal_key(other_visit)
    assert crystal_key(entry())[0] == "cm44138-3"


def test_a_dewar_clean_does_not_break_the_crystal_key():
    """Sethau4 moved from puck 33 to puck 36 when the dewar was cleaned. The pin
    number stayed 4, and the name did not change - so neither must the key."""
    moved = entry(loaded_puck=33.0)
    assert crystal_key(moved) == crystal_key(entry())


# --------------------------------------------------------------------------
# Naming the crystal, which has no single convention
# --------------------------------------------------------------------------

# All four of these are the same crystal, taken from the real arming log.
SAMPLE_DIRECTORY = (
    "/dls/i04/data/2026/cm44138-3/20260710/TestThaumatin/Sethau4/"
    "TestThaumatin_Sethau4_1_master.h5"
)
SHARED_BUCKET = "/dls/i04/data/2026/cm44138-3/20260731/test-shots/Sethau4_1_master.h5"
CENTRING = (
    "/dls/i04/data/2026/cm44138-3/xraycentring/20260710/TestThaumatin/Sethau4/"
    "TestThaumatin_Sethau4_2_master.h5"
)
BUCKET_CENTRING = (
    "/dls/i04/data/2026/cm44138-3/xraycentring/20260731/test-shots/Sethau4_1_master.h5"
)


@pytest.mark.parametrize(
    "master", [SAMPLE_DIRECTORY, SHARED_BUCKET, CENTRING, BUCKET_CENTRING]
)
def test_the_same_crystal_is_named_the_same_however_it_was_filed(master):
    assert crystal_name(entry(master_file=master)) == "Sethau4"


def test_the_shared_bucket_days_are_the_ones_that_matter():
    """31 July and 2 August 2026 - the two mornings that delivered double the
    intended dose - are filed under test-shots/, not under a sample directory.
    Naming from the directory alone would lose exactly those."""
    assert crystal_name(entry(master_file=SHARED_BUCKET)) == "Sethau4"


def test_a_crystal_name_is_not_a_prefix_of_another():
    """Sethau1 and Sethau13 were both real crystals on i04 in 2026, so a plain
    substring match would silently merge two crystals' lifetime doses."""
    thirteen = entry(
        master_file="/dls/i04/data/2026/cm44138-3/20260710/TestThaumatin/Sethau13/"
        "TestThaumatin_Sethau13_1_master.h5"
    )
    assert mentions_crystal(thirteen, "Sethau13")
    assert not mentions_crystal(thirteen, "Sethau1")


def test_matching_a_crystal_ignores_case():
    """The same crystal appears as both `_SeThau2` and `Sethau2`."""
    assert mentions_crystal(entry(master_file=SHARED_BUCKET), "sethau4")


def test_a_history_gathers_every_spelling_and_stays_in_time_order():
    entries = [
        entry(master_file=SHARED_BUCKET, unix_time=300),
        entry(master_file=SAMPLE_DIRECTORY, unix_time=100),
        entry(master_file=CENTRING, unix_time=200),
    ]
    history = history_for_crystal(entries, "Sethau4", visit="cm44138-3")
    assert [e["unix_time"] for e in history] == [100, 200, 300]


def test_a_history_stops_at_the_collection_being_reported():
    """The lifetime figure must be what the crystal had absorbed by then, not
    what it went on to absorb afterwards."""
    entries = [entry(unix_time=t) for t in (100, 200, 300)]
    assert len(history_for_crystal(entries, "Sethau4", until=200)) == 2


def test_a_history_does_not_cross_a_visit():
    entries = [entry(), entry(full_visit="cm12345-1")]
    assert len(history_for_crystal(entries, "Sethau4", visit="cm44138-3")) == 1


def test_the_centring_shots_are_gathered_with_their_dataset():
    shot = entry(
        unix_time=BASE["unix_time"] - 300,
        filepath="/dls/i04/data/2026/cm44138-3/xraycentring/Sethau4",
        master_file="/dls/i04/data/2026/cm44138-3/xraycentring/Sethau4/xrc_1_master.h5",
    )
    log = EigerLog(FakeRedis([entry(), shot]), "i04")
    assert len(log.around(BASE["master_file"])) == 2


def test_another_crystal_nearby_in_time_is_not_gathered_with_it():
    neighbour = entry(unix_time=BASE["unix_time"] - 300, loaded_pin=7.0)
    log = EigerLog(FakeRedis([entry(), neighbour]), "i04")
    assert len(log.around(BASE["master_file"])) == 1


# --------------------------------------------------------------------------
# The scaling, which is the whole point
# --------------------------------------------------------------------------


def test_dose_scales_with_flux_and_exposure(calculator):
    """dose = rate * (flux/nominal) * exposure. Everything rests on this."""
    one = calculator.dose(entry())
    twice_the_flux = calculator.dose(entry(flux=2 * BASE["flux"]))
    twice_the_time = calculator.dose(entry(acquire_time_s=0.004))
    assert twice_the_flux == pytest.approx(2 * one)
    assert twice_the_time == pytest.approx(2 * one)


def test_the_reference_collection_gives_the_expected_dose(calculator):
    """3600 x 2 ms at 3e10 and 0.017406 MGy/s -> about 1.25 MGy, which is what
    the real Sethau4 collection of 7 August 2026 came out at."""
    assert calculator.dose(entry()) == pytest.approx(1.253, abs=0.01)


def test_the_service_is_asked_once_per_beam_configuration(calculator):
    for _ in range(20):
        calculator.dose(entry(flux=3.1e11))
    assert calculator.calls == 1


def test_a_wobbling_beam_size_readback_does_not_become_a_new_api_call(calculator):
    """The readback moves in the third decimal between identical collections."""
    calculator.dose(entry(beamsize_h_um=30.130))
    calculator.dose(entry(beamsize_h_um=30.1304))
    calculator.dose(entry(beamsize_h_um=30.1298))
    assert calculator.calls == 1


def test_a_different_energy_is_a_different_configuration(calculator):
    calculator.dose(entry())
    calculator.dose(entry(energy_ev=12400.0))
    assert calculator.calls == 2


def test_the_service_is_asked_at_nominal_flux_for_one_second(calculator):
    calculator.dose(entry())
    asked = calculator.service.requests[0]
    assert float(asked["flux"]) == NOMINAL_FLUX
    assert asked["total_exposure_time"] == 1.0


def test_the_oscillation_never_starts_at_zero(calculator):
    """oscillation_start=0 makes the service return HTTP 500, undocumented."""
    assert DEFAULT_OSCILLATION[0] == 1.0
    calculator.dose(entry())
    assert float(calculator.service.requests[0]["oscillation_start"]) != 0


def test_energy_is_sent_in_kev_not_ev(calculator):
    calculator.dose(entry())
    assert calculator.service.requests[0]["energy_kev"] == pytest.approx(13.0, abs=0.01)


def test_exposure_is_the_acquire_time_not_the_period(calculator):
    """The period includes detector dead time, during which no photons land."""
    assert calculator.exposure_seconds(entry()) == pytest.approx(7.2)


# --------------------------------------------------------------------------
# Refusing to invent a number
# --------------------------------------------------------------------------


def test_a_collection_with_no_flux_is_refused_not_scored_zero(calculator):
    """A silent zero would be summed into a lifetime total and lower it."""
    with pytest.raises(DoseUnavailable):
        calculator.dose(entry(flux=0))


def test_a_collection_with_no_exposure_is_refused(calculator):
    with pytest.raises(DoseUnavailable):
        calculator.dose(entry(number_images=0))


def test_an_unusable_record_is_reported_rather_than_dropped(calculator):
    rows, total, skipped = calculator.dose_for_collections(
        [entry(), entry(flux=0), entry()]
    )
    assert len(rows) == 2
    assert len(skipped) == 1
    assert total == pytest.approx(2 * calculator.dose(entry()))


def test_a_reply_without_the_dose_field_is_an_error(calculator):
    calculator._get = lambda params: {"something else": 1}
    with pytest.raises(DoseUnavailable):
        DoseCalculator(api_url="http://stub").rate(13.0, 30.0, 19.0)


def test_the_dose_field_is_the_one_gda_uses():
    """The 30 MGy Garman limit is quoted on the same basis."""
    from base.dose import DOSE_FIELD

    assert DOSE_FIELD == "Max Dose"


# --------------------------------------------------------------------------
# The trends tool's own filtering (F5)
# --------------------------------------------------------------------------


def _trends():
    """dev/trends.py, imported by path since dev/ is not a package."""
    import importlib.util
    import os

    from conftest import REPO_ROOT

    path = os.path.join(REPO_ROOT, "dev", "trends.py")
    spec = importlib.util.spec_from_file_location("trends", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_users_sample_is_not_reported_as_a_test_crystal():
    """`Ins_14` on a user visit matches the `insulin` alias. Without the visit
    test it would be listed as though we had been burning it every morning."""
    trends = _trends()
    aliases = trends.test_sample_aliases()
    user = entry(
        full_visit="mx23694-165",
        master_file="/dls/i04/data/2026/mx23694-165/Ins/Ins_14/Ins_14_1_master.h5",
    )
    assert not trends.looks_like_a_test_crystal(user, aliases)
    assert trends.looks_like_a_test_crystal(entry(), aliases)


def test_the_aliases_come_from_the_registry_the_module_already_uses():
    """One list, maintained in one place - a crystal added to TestCrystal.yaml
    shows up here without anyone remembering to edit the tool."""
    aliases = _trends().test_sample_aliases()
    assert {"thaumatin", "thau", "sethau", "lysozyme", "insulin"} <= aliases


def test_a_beamstop_shot_does_not_become_a_crystal_called_100():
    """`low_res_100_100` in a shared bucket yields a last token of `100`."""
    trends = _trends()
    shot = entry(
        master_file="/dls/i04/data/2026/cm44138-3/20260731/test_shots/"
        "low_res_100_100_master.h5"
    )
    assert not trends.is_a_real_name(crystal_name(shot))
    assert trends.is_a_real_name("Sethau4")


# --------------------------------------------------------------------------
# Telling the operator the crystal is spent (B2b)
# --------------------------------------------------------------------------


def _test_crystal_module():
    from modules.TestCrystal.TestCrystal import TestCrystal

    return TestCrystal


class FakeUI:
    """Records what the popup was asked to say."""

    def __init__(self):
        self.warnings = []

    def show_urgent_warning(self, parent, title, text, informative_text, buttons):
        self.warnings.append((title, text, informative_text))


def _spent_crystal_harness():
    import logging
    import types

    module = _test_crystal_module()

    class Fake:
        log = logging.getLogger("dose-popup-tests")

        def __init__(self):
            self.ui = FakeUI()
            self.TestCrystal_WZ = None

    Fake.warn_if_crystal_is_spent = module.__dict__["warn_if_crystal_is_spent"]
    return Fake()


def test_a_crystal_past_the_limit_interrupts_the_operator():
    """A red row read after the fact is too late - they can swap it now."""
    harness = _spent_crystal_harness()
    harness.warn_if_crystal_is_spent({"Dose_crystal_lifetime_MGy": 33.2})
    assert len(harness.ui.warnings) == 1
    title, text, informative = harness.ui.warnings[0]
    assert "33.2" in text
    assert "3.2 MGy past" in informative
    assert "fresh test crystal" in informative


def test_a_crystal_within_its_life_is_not_interrupted():
    harness = _spent_crystal_harness()
    harness.warn_if_crystal_is_spent({"Dose_crystal_lifetime_MGy": 12.0})
    assert harness.ui.warnings == []


def test_no_dose_column_means_no_popup():
    """The service being down must not produce a warning about nothing."""
    harness = _spent_crystal_harness()
    harness.warn_if_crystal_is_spent({"Dose_note": "service unavailable"})
    assert harness.ui.warnings == []


def test_the_popup_says_the_data_is_still_recorded():
    """It is a prompt to fetch a new crystal, not a refusal to record this one."""
    harness = _spent_crystal_harness()
    harness.warn_if_crystal_is_spent({"Dose_crystal_lifetime_MGy": 40.0})
    assert "still recorded" in harness.ui.warnings[0][2]


def test_a_broken_popup_never_costs_the_report():
    harness = _spent_crystal_harness()

    def explode(*args, **kwargs):
        raise RuntimeError("no display")

    harness.ui.show_urgent_warning = explode
    harness.warn_if_crystal_is_spent({"Dose_crystal_lifetime_MGy": 40.0})  # no raise


def test_the_module_imports_everything_its_popups_use():
    """QtWidgets.QMessageBox is reached at runtime, so py_compile cannot see a
    missing import. This module used QtWidgets without importing it."""
    import modules.TestCrystal.TestCrystal as module

    assert hasattr(module, "QtWidgets")
    assert hasattr(module.QtWidgets, "QMessageBox")


# --------------------------------------------------------------------------
# How far back the log is read
# --------------------------------------------------------------------------


def test_around_honours_the_window_it_is_given():
    """A collection outside the window is not found; inside it, it is.

    The default depth is about a day of arming records - 5000 entries reached
    only back to 6 August when measured on 2026-08-31. Selecting a 30 July master
    file therefore reported "no arming record found for this collection" while
    the record was plainly in redis, because `around()` was called without a
    window and fell back to that default.
    """
    old = entry(unix_time=1_000_000.0)
    log = EigerLog(FakeRedis([old]), "i04")

    assert log.around(BASE["master_file"], since=2_000_000.0) == []
    assert len(log.around(BASE["master_file"], since=500_000.0)) == 1


def test_the_module_reads_the_same_window_for_both_dose_figures():
    """`this collection` and `crystal lifetime` must come from one window.

    They were read separately - the lifetime with an explicit 60-day lookback and
    the anchor with the default - so a master file could be too old for one and
    not the other, which is precisely how it failed.
    """
    import os

    from conftest import REPO_ROOT

    source = open(
        os.path.join(REPO_ROOT, "modules", "TestCrystal", "TestCrystal.py")
    ).read()
    body = source[
        source.index("def collect_dose") : source.index("def make_image_montage")
    ]
    assert (
        body.count("since=since") == 2
    ), "both the anchor and the history reads must use the same computed window"
    assert "eiger.around(\n                masterfile, depth=200000" in body or (
        "eiger.around(masterfile, depth=200000" in body
    ), "around() is being called without a depth again"


def test_the_default_depth_is_documented_as_about_a_day():
    """So the next person does not assume it covers a run."""
    import base.eiger_log as module

    assert module.DEFAULT_DEPTH == 5000
    assert (
        "day, not a week" in module.__doc__
        or "It is a day" in open(module.__file__).read()
    )


# --------------------------------------------------------------------------
# The log has four schema generations, and old records are narrower
# --------------------------------------------------------------------------


def test_an_old_narrow_record_is_named_correctly_as_far_as_it_goes():
    """Fields have only ever been appended, so zipping the current schema onto
    an 18-field record names those 18 correctly and simply runs out."""
    # A generation that stops before the beam conditions were recorded.
    early = SCHEMA[: SCHEMA.index("transmission_pct")]
    narrow = {name: BASE.get(name) for name in early}
    log = EigerLog(FakeRedis([narrow], schema=early), "i04")
    entry = log.collections()[0]
    assert entry["master_file"] == BASE["master_file"]
    assert "transmission_pct" not in entry


def test_records_missing_a_needed_field_can_be_excluded():
    """Before 6 August 2025 there is no transmission or exposure at all, so a
    consumer that needs them must be able to drop those records rather than
    crash on a KeyError."""
    schema = SCHEMA[: SCHEMA.index("transmission_pct")]
    old = {name: BASE.get(name) for name in schema}

    class Mixed(FakeRedis):
        def lrange(self, key, start, end):
            import json as _json

            rows = [
                _json.dumps([BASE.get(n) for n in SCHEMA]).encode(),
                _json.dumps([old.get(n) for n in schema]).encode(),
            ]
            return rows[start : end + 1]

    log = EigerLog(Mixed([], schema=SCHEMA), "i04")
    assert len(log.collections()) == 2
    assert len(log.collections(needs=("transmission_pct",))) == 1


def test_the_schema_generations_are_written_down():
    """So the next person does not lose an afternoon to a KeyError."""
    import base.eiger_log as module

    text = open(module.__file__).read()
    assert "2025-08-05" in text and "2025-12-16" in text
    assert module.EigerLog.ORIGINAL_FIELDS == 18
