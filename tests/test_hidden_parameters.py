"""Hidden parameters and the report format stamp (V13).

Everything written to redis used to be rendered into the report table and posted
to the eLog, so there was no way to record a value for later analysis without
putting it in front of staff every morning. That blocked storing the crosshair
position, and it blocks trend analysis generally, which wants more history than
anyone wants to read daily.

A hidden parameter is still stored, still assessed and still logged. It is only
kept out of the rendered table.
"""

import os
import re

import jinja2
import pytest

from conftest import REPO_ROOT

TEMPLATE_DIR = os.path.join(REPO_ROOT, "modules", "CreateReport", "templates")


RULES = {"Crosshair_X": {"check_type": "deadband_absolute", "limits": [0, 5]}}


def test_a_hidden_parameter_is_marked(assessor):
    result = assessor.assess_parameters(
        {"Crosshair_X": 512.0, "FLUX": 1.0e12}, {}, {}, hidden=["Crosshair_X"]
    )
    assert result["Crosshair_X"]["hidden"] is True
    assert "hidden" not in result["FLUX"], "only the named parameters are hidden"


def test_a_hidden_parameter_keeps_its_value(assessor):
    """Hidden means not shown, not not stored - the whole point is to record it."""
    result = assessor.assess_parameters(
        {"Crosshair_X": 512.0}, {}, {}, hidden=["Crosshair_X"]
    )
    assert result["Crosshair_X"]["value"] == 512.0


def test_a_hidden_parameter_is_still_assessed(assessor):
    """A hidden value can still be worth a status in the logs and in redis."""
    result = assessor.assess_parameters(
        {"Crosshair_X": 512.0}, RULES, {"Crosshair_X": 511.0}, hidden=["Crosshair_X"]
    )
    assert result["Crosshair_X"]["hidden"] is True
    assert result["Crosshair_X"]["status"] == "warning"


def test_hiding_something_the_module_does_not_produce_warns(assessor, caplog):
    """A stale name in hidden_parameters would otherwise be silent."""
    with caplog.at_level("WARNING"):
        result = assessor.assess_parameters(
            {"FLUX": 1.0}, {}, {}, hidden=["Nonexistent"]
        )
    assert "Nonexistent" in caplog.text
    assert "FLUX" in result, "the rest of the report is unaffected"


def test_no_hidden_list_means_nothing_is_hidden(assessor):
    result = assessor.assess_parameters({"FLUX": 1.0}, {}, {})
    assert "hidden" not in result["FLUX"]


# --------------------------------------------------------------------------
# The report template must not render hidden rows
# --------------------------------------------------------------------------


def _render_parameter_rows(parameters):
    """Render just the parameter loop, with the same filter the template uses."""
    source = open(os.path.join(TEMPLATE_DIR, "beamline_logbook_template.jinja2")).read()
    # Every loop over the parameters has to filter hidden rows - the table bodies
    # and the notes underneath alike. A new loop that forgets is how a hidden
    # value would quietly reach the eLog.
    # Both spellings: module_data['parameters'] and module_data.parameters. The
    # first version of this test only matched the brackets, and missed the
    # SampleLoad loop entirely.
    loops = re.findall(
        r"\{% for [^%]*module_data(?:\['parameters'\]|\.parameters)[^%]*%\}", source
    )
    assert loops, "no parameter loops found - has the template changed shape?"
    for loop in loops:
        assert "hidden" in loop, f"this loop does not filter hidden rows: {loop!r}"

    fragment = (
        "{% for p_key, p_val in module_data['parameters'].items()"
        " if not (p_val is mapping and p_val.hidden) %}{{ p_key }} {% endfor %}"
    )
    return jinja2.Template(fragment).render(module_data={"parameters": parameters})


def test_hidden_rows_do_not_reach_the_report():
    rendered = _render_parameter_rows(
        {
            "FLUX": {"value": 1.0e12, "status": "good"},
            "Crosshair_X": {"value": 512.0, "hidden": True},
        }
    )
    assert "FLUX" in rendered
    assert (
        "Crosshair_X" not in rendered
    ), "a hidden parameter must not be posted to the eLog"


def test_plain_values_still_render():
    """Older reports store bare values rather than dicts; those have no .hidden."""
    rendered = _render_parameter_rows({"masterfile": "/dls/i04/x_master.h5"})
    assert "masterfile" in rendered


# --------------------------------------------------------------------------
# The format stamp
# --------------------------------------------------------------------------


def test_the_format_version_is_a_positive_integer():
    from base.Modules import REPORT_FORMAT_VERSION

    assert isinstance(REPORT_FORMAT_VERSION, int)
    assert REPORT_FORMAT_VERSION >= 2, (
        "1 is reserved for reports the migration tool rewrites; legacy reports "
        "carry no stamp at all"
    )


def test_store_report_stamps_and_keys_by_today():
    """Modules used to build this key by hand, and disagreed about whether
    self.now was a string or a datetime."""
    from datetime import datetime

    from base.Modules import Base, REPORT_FORMAT_VERSION

    written = {}

    class Fake:
        class_name = "AlignBeam"

        def __init__(self):
            import logging

            self.log = logging.getLogger("store-report-test")

        def set(self, key, value):
            written[key] = value

    Fake.store_report = Base.__dict__["store_report"]
    module = Fake()
    key = module.store_report({"parameters": {"FLUX": {"value": 1.0}}})

    today = datetime.now().strftime("%Y%m%d")
    assert key == f"AlignBeam_report_{today}"
    assert written[key]["format_version"] == REPORT_FORMAT_VERSION
    assert written[key]["parameters"]["FLUX"]["value"] == 1.0


def test_store_report_does_not_mutate_the_callers_payload():
    from base.Modules import Base

    class Fake:
        class_name = "T"

        def __init__(self):
            import logging

            self.log = logging.getLogger("t")

        def set(self, key, value):
            pass

    Fake.store_report = Base.__dict__["store_report"]
    payload = {"parameters": {}}
    Fake().store_report(payload)
    assert "format_version" not in payload


# --------------------------------------------------------------------------
# Every module that writes a report goes through store_report
# --------------------------------------------------------------------------


def test_no_module_builds_its_own_report_key():
    """A hand-built key skips the format stamp.

    RemoteAccess was missed when the other five were converted, so its reports
    went out with no format_version and the migration tool would have treated
    them as legacy.
    """
    import glob
    import re

    from conftest import MODULES_DIR

    offenders = []
    for path in glob.glob(os.path.join(MODULES_DIR, "*", "*.py")):
        if os.path.basename(path).startswith(("GUI_", "test_")):
            continue
        source = open(path).read()
        if re.search(r'f"\{self\.class_name\}_report_', source):
            offenders.append(os.path.relpath(path, MODULES_DIR))
    assert not offenders, (
        f"these build their own report key instead of calling store_report, so "
        f"their reports carry no format_version: {offenders}"
    )


# --------------------------------------------------------------------------
# Notes under the table, for parameters whose names do not explain themselves
# --------------------------------------------------------------------------


def _render_notes(module_data):
    source = open(os.path.join(TEMPLATE_DIR, "beamline_logbook_template.jinja2")).read()
    start = source.index("{% set shown = [] %}")
    end = source.index("{% endif %}", source.index("</td>", start)) + len("{% endif %}")
    return jinja2.Template(source[start:end]).render(module_data=module_data)


def test_a_note_appears_for_a_parameter_that_has_one():
    rendered = _render_notes(
        {
            "parameters": {"Scale_step_pct": {"value": 2.94}},
            "parameter_notes": {"Scale_step_pct": "Largest jump in per-image scale."},
        }
    )
    assert "Scale_step_pct" in rendered
    assert "Largest jump" in rendered


def test_notes_are_only_written_for_parameters_the_report_contains():
    """A report should not carry footnotes about checks that did not run."""
    rendered = _render_notes(
        {
            "parameters": {"ISa": {"value": 39.6}},
            "parameter_notes": {
                "Scale_step_pct": "should not appear",
                "Goniometer_speed_sd_deg": "nor this",
            },
        }
    )
    assert "should not appear" not in rendered
    assert "nor this" not in rendered


def test_nothing_is_written_when_there_is_nothing_to_say():
    rendered = _render_notes({"parameters": {"ISa": {"value": 39.6}}})
    assert rendered.strip() == ""


def test_the_familiar_statistics_have_no_notes():
    """A note on every row would bury the ones that need it."""
    from conftest import load_module_yaml

    notes = load_module_yaml("TestCrystal")["parameter_notes"]
    for familiar in ("ISa", "Resolution", "CChalf", "Completeness", "Multiplicity"):
        assert (
            familiar not in notes
        ), f"{familiar} is standard in any MX report and does not need explaining"


def test_every_note_names_a_parameter_that_can_be_reported():
    """A note for a parameter nothing produces would never be seen."""
    import re

    from conftest import load_module_yaml, REPO_ROOT

    notes = load_module_yaml("TestCrystal")["parameter_notes"]
    # Most parameters are produced by the parser. Dose is joined on by the module
    # itself from the arming log and the RADDOSE-3D service, so both files count.
    source = ""
    for name in ("QualityControl.py", "TestCrystal.py"):
        source += open(os.path.join(REPO_ROOT, "modules", "TestCrystal", name)).read()
    produced = set(re.findall(r'"(\w+)"', source))
    unknown = sorted(set(notes) - produced)
    assert not unknown, f"notes for parameters TestCrystal never produces: {unknown}"


# --------------------------------------------------------------------------
# CreateReport reads other modules' YAML. That must never be able to break it.
# --------------------------------------------------------------------------


def _note_attacher():
    """The real method, unbound from redis and the GUI."""
    import logging

    from modules.CreateReport.CreateReport import CreateReport

    class Fake:
        ID = "i04"
        log = logging.getLogger("notes-tests")

    Fake.attach_parameter_notes = CreateReport.__dict__["attach_parameter_notes"]
    return Fake()


@pytest.mark.parametrize(
    "label,payload",
    [
        ("a module that was deleted", {"Deleted_report_20260831": {"parameters": {}}}),
        ("a module with no notes", {"SampleLoad_report_20260831": {"parameters": {}}}),
        ("a report that is not a dict", {"Odd_report_20260831": "a string"}),
        ("nothing at all", {}),
    ],
)
def test_attaching_notes_never_raises(label, payload):
    """The report must render even if a module's configuration has gone.

    CreateReport reads each module's YAML to find its notes, which couples it to
    the other modules' files. That coupling is only acceptable while a missing or
    unreadable file costs nothing - so this pins it. A module removed from
    configure_blsetup.yaml never runs and writes no report, so the question does
    not arise; this covers the messier cases where a report exists but the module
    does not.
    """
    _note_attacher().attach_parameter_notes(payload)


def test_notes_are_found_for_a_module_that_has_them():
    payload = {"TestCrystal_report_20260831": {"parameters": {"ISa": 1}}}
    _note_attacher().attach_parameter_notes(payload)
    assert payload["TestCrystal_report_20260831"]["parameter_notes"]


def test_the_lookup_is_generic_not_a_list_of_modules():
    """Naming modules here would be the coupling worth objecting to. The module
    name comes from the report key, so a new module gets notes for free."""
    import inspect

    from modules.CreateReport.CreateReport import CreateReport

    source = inspect.getsource(CreateReport.attach_parameter_notes)
    for module in ("TestCrystal", "AlignBeam", "RotationAxis", "SampleLoad"):
        assert module not in source, f"{module} is named explicitly in the lookup"


def test_notes_do_not_refer_to_where_they_are_written():
    """The notes are read in the eLog, not in the YAML.

    "the registry below" and "in this file" make sense to whoever edits
    TestCrystal.yaml and none at all to someone reading the posted report, who
    cannot see either.
    """
    from conftest import load_module_yaml

    for name, note in load_module_yaml("TestCrystal")["parameter_notes"].items():
        lowered = note.lower()
        for phrase in ("below", "above in this file", "in this file", "this yaml"):
            assert phrase not in lowered, (
                f"the note for {name} says {phrase!r}, which means nothing to a "
                f"reader of the report"
            )
