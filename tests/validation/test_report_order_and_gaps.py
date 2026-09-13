"""The report reads in checklist order and says what was skipped (F1).

Both problems came from building the report out of whatever redis returned. The
sections appeared in arbitrary order, so the report did not read like the
checklist staff had just worked through; and a module that was skipped simply had
no section, which looks identical to a module that does not exist. Staff have
forgotten to run modules and nothing in the report said so.
"""

import logging
import os
from datetime import datetime

import jinja2
import pytest

from conftest import REPO_ROOT

TODAY = datetime.now().strftime("%Y%m%d")


@pytest.fixture
def reporter():
    from modules.CreateReport.CreateReport import CreateReport

    class Fake:
        config = {
            "modules": {
                "InitialChecks": {},
                "RemoteAccess": {},
                "SampleLoad": {},
                "AlignBeam": {},
                "TestCrystal": {},
                "CreateReport": {},
            }
        }

        def __init__(self):
            self.log = logging.getLogger("report-order-tests")

    Fake.order_and_fill_gaps = CreateReport.__dict__["order_and_fill_gaps"]
    # It reads each skipped module's own YAML for the text that module owns.
    Fake.module_wording = CreateReport.__dict__["module_wording"]
    Fake.module_config_path = CreateReport.__dict__["module_config_path"]
    return Fake()


def report(module):
    return f"{module}_report_{TODAY}"


def test_sections_follow_the_checklist_order(reporter):
    """Redis returns them in no particular order."""
    jumbled = {
        report("TestCrystal"): {"parameters": {}},
        report("AlignBeam"): {"parameters": {}},
        report("RemoteAccess"): {"parameters": {}},
    }
    everything = list(jumbled)
    ordered = reporter.order_and_fill_gaps(jumbled, everything)
    assert [k.split("_report_")[0] for k in ordered] == [
        "RemoteAccess",
        "AlignBeam",
        "TestCrystal",
    ]


def test_a_module_that_did_not_run_is_named(reporter):
    """It has reported before, so it should have reported today."""
    todays = {report("AlignBeam"): {"parameters": {}}}
    everything = list(todays) + ["TestCrystal_report_20260807"]
    ordered = reporter.order_and_fill_gaps(todays, everything)
    assert ordered[report("TestCrystal")]["not_run"] is True
    assert ordered[report("AlignBeam")].get("not_run") is None


def test_a_module_that_has_never_reported_is_not_asked_about(reporter):
    """InitialChecks and CreateDirectories write no report; demanding a section
    from them would put permanent false negatives in every report."""
    ordered = reporter.order_and_fill_gaps(
        {report("AlignBeam"): {}}, [report("AlignBeam")]
    )
    assert report("InitialChecks") not in ordered


def test_a_module_reported_but_not_declared_is_still_included(reporter):
    """Better an out-of-order section than a lost one."""
    todays = {report("Mystery"): {"parameters": {}}}
    ordered = reporter.order_and_fill_gaps(todays, list(todays))
    assert report("Mystery") in ordered


def test_the_placeholder_renders():
    source = open(
        os.path.join(
            REPO_ROOT,
            "modules",
            "CreateReport",
            "templates",
            "beamline_logbook_template.jinja2",
        )
    ).read()
    start = source.index("{% if module_data.not_run %}")
    end = source.index("{# --- PATH 1", start)
    rendered = jinja2.Template(source[start:end] + "{% endif %}").render(
        module_data={"not_run": True, "table_title": "TestCrystal"}
    )
    assert "TestCrystal" in rendered
    assert "was not run today" in rendered


# --------------------------------------------------------------------------
# Not every skipped module is equally serious
# --------------------------------------------------------------------------


def _module_config(module):
    """A module's own YAML, whichever of the two names it uses.

    Most are `<Module>/<Module>.yaml`; BeamstopAlignment and RemoteAccess keep
    theirs as `GUI_<Module>.yaml`.
    """
    import os

    import yaml

    from conftest import REPO_ROOT

    for name in (f"{module}.yaml", f"GUI_{module}.yaml"):
        path = os.path.join(REPO_ROOT, "modules", module, name)
        if os.path.exists(path):
            with open(path) as handle:
                return yaml.safe_load(handle) or {}
    return {}


def _not_run(module):
    return _module_config(module).get("not_run", {})


def _reporting_modules():
    """The modules that write a report, and so can be marked 'not run'."""
    import os

    import yaml

    from conftest import REPO_ROOT

    with open(os.path.join(REPO_ROOT, "configure_blsetup.yaml")) as handle:
        live = set(yaml.safe_load(handle)["modules"])
    found = set()
    modules_dir = os.path.join(REPO_ROOT, "modules")
    for name in os.listdir(modules_dir):
        path = os.path.join(modules_dir, name, f"{name}.py")
        if os.path.exists(path) and "store_report(" in open(path).read():
            found.add(name)
    return sorted(found & live)


def test_the_two_critical_modules_are_marked_critical():
    """Align Beam and Rotation Axis are the two a beamline should not be handed
    over without. Samples can be loaded days ahead and an email can wait."""
    assert _not_run("AlignBeam")["severity"] == "critical"
    assert _not_run("RotationAxis")["severity"] == "critical"
    assert _not_run("BeamstopAlignment")["severity"] == "warning"


def test_rotation_axis_is_two_words_in_the_report():
    assert _not_run("RotationAxis")["title"] == "Rotation Axis"


def test_the_beamstop_message_asks_about_file_names():
    """The usual reason it is missing is not that someone forgot."""
    message = _not_run("BeamstopAlignment")["message"]
    assert "name" in message.lower()
    # ...and it must not read as blaming whoever ran it.
    assert "has happened before" not in message.lower()


def test_a_critical_skip_renders_as_a_red_attention_line():
    """The wording is only worth having if the template actually shows it. It
    did not, first time round: the message was read from the application config
    instead of the module's own, so nothing reached the page."""
    import os
    import re

    import jinja2

    from conftest import REPO_ROOT

    path = os.path.join(
        REPO_ROOT,
        "modules",
        "CreateReport",
        "templates",
        "beamline_logbook_template.jinja2",
    )
    text = open(path).read()
    block = text[text.index("{% if module_data.not_run %}") :]
    block = block[: block.index("{# --- PATH 1")]

    template = jinja2.Template(
        "{% for module_key, module_data in modules.items() %}"
        + block
        + "{% endif %}{% endfor %}"
    )
    rendered = template.render(
        modules={
            "RotationAxis_report_20260831": {
                "not_run": True,
                "table_title": "Rotation Axis",
                "not_run_severity": "critical",
                "not_run_message": "The rotation axis was not checked today.",
            },
            "SampleLoad_report_20260831": {
                "not_run": True,
                "table_title": "Sample Load",
                "not_run_severity": "warning",
                "not_run_message": None,
            },
        }
    )
    assert "ATTENTION" in rendered
    # Two skipped modules, one of each kind: the critical one must not fall back
    # to the quiet style, which is small, italic and dark yellow - unreadable on
    # a red ground and wrong in tone besides.
    assert rendered.count("not-run-critical") == 1
    assert rendered.count("not-run-warning") == 1
    # Both share the legible base; the amber note must not fall back to
    # `.nothing-found`, which is small, italic and dark yellow on pale yellow.
    assert "nothing-found" not in rendered
    assert rendered.count('class="not-run ') == 2
    assert "Rotation Axis" in rendered
    assert "The rotation axis was not checked today." in rendered
    # ...and the ordinary skip stays quiet: one ATTENTION for two skipped
    # modules, not two.
    assert rendered.count("ATTENTION") == 1
    assert "Sample Load" in rendered


def test_no_message_ranks_one_check_above_the_others():
    """ "One of the two checks that matter most" reads as permission to skip the
    rest. Each message must justify its own check and stop there."""
    for module in _reporting_modules():
        message = (_not_run(module).get("message") or "").lower()
        for phrase in ("matters most", "two checks", "most important", "matter most"):
            assert phrase not in message, f"{module} ranks itself above the others"


def test_the_report_has_one_visual_language_for_missing_data():
    """A module that found nothing and a module that was not run are the same
    kind of statement, and looked like different reports.

    `.nothing-found` was small, italic and dark yellow on pale yellow while the
    not-run blocks had been given proper type. Four sections still used it - the
    empty dewar, no NX sessions, no beamstop data, no beam images - so the two
    styles appeared in the same report.
    """
    import os
    import re

    from conftest import REPO_ROOT

    css = open(
        os.path.join(
            REPO_ROOT,
            "modules",
            "CreateReport",
            "templates",
            "beamline_logbook_template.jinja2",
        )
    ).read()

    def rule(name):
        match = re.search(re.escape(name) + r"\s*\{([^}]*)\}", css)
        assert match, f"{name} is not defined"
        return match.group(1)

    quiet, note = rule(".nothing-found"), rule(".not-run")
    for prop in ("color: #212529", "font-style: normal", "font-size: 100%"):
        assert prop in quiet, f".nothing-found lost `{prop}`"
        assert prop in note, f".not-run lost `{prop}`"
    assert "italic" not in quiet, "the quiet note is italic again"


def test_every_module_that_reports_can_explain_its_own_absence():
    """The template a new module has to fill in, enforced rather than remembered.

    Only a module that has written a report can be marked "not run" - the F1 code
    requires it to be in `ever_reported` - so those are exactly the modules that
    need wording. The other six declared in configure_blsetup.yaml never write
    one and can never appear.

    The text lives in each module's own YAML, so that a person working on one
    module owns its wording without touching the reporting module.
    """
    for module in _reporting_modules():
        spoken = _not_run(module)
        assert spoken, (
            f"{module} writes a report, so it can be marked 'not run', but its "
            f"YAML has no `not_run:` block. Add one with a title, a severity and "
            f"a message saying why that check matters."
        )
        assert spoken.get("message"), (
            f"{module}'s not_run block has no message, so the report will say "
            f"only that it was not run. Say why it matters."
        )
        assert spoken.get("severity") in ("critical", "warning"), module


def test_the_reporting_module_does_not_hold_other_modules_text():
    """The point of the move: CreateReport must not accumulate knowledge about
    modules it only renders."""
    assert "not_run" not in _module_config("CreateReport")


def test_both_yaml_naming_conventions_are_found():
    """BeamstopAlignment and RemoteAccess use GUI_<Module>.yaml. A reader that
    only looks for <Module>.yaml silently finds nothing for those two."""
    assert _not_run("BeamstopAlignment")
    assert _not_run("RemoteAccess")


# --------------------------------------------------------------------------
# A broken module config must not take the report down with it
# --------------------------------------------------------------------------


def test_every_module_config_parses():
    """The cheapest possible guard: all of them load.

    CreateReport reads other modules' YAML at render time, so a syntax error in
    any one of them is a fault in the reporting module as far as the operator can
    see.
    """
    import glob
    import os

    import yaml

    from conftest import REPO_ROOT

    broken = []
    for path in glob.glob(os.path.join(REPO_ROOT, "modules", "*", "*.yaml")):
        try:
            yaml.safe_load(open(path))
        except yaml.YAMLError as error:
            broken.append((os.path.relpath(path, REPO_ROOT), str(error)[:120]))
    assert not broken, broken


def test_the_report_survives_a_module_config_that_will_not_parse(tmp_path):
    """A module owning its own text means a module can break the report. It must
    not be able to.

    This is the risk that came with moving the wording out of CreateReport: the
    reporting module now reads six other files it does not control.
    """
    import os

    from modules.CreateReport.CreateReport import CreateReport

    class Fake:
        ID = "i04"

        def __init__(self):
            import logging

            self.log = logging.getLogger("broken-config-tests")

    Fake.module_wording = CreateReport.__dict__["module_wording"]
    Fake.module_config_path = CreateReport.__dict__["module_config_path"]
    fake = Fake()

    # A module whose YAML is unparseable, by pointing the lookup at one.
    bad = tmp_path / "AlignBeam.yaml"
    bad.write_text("not_run:\n  message: [unclosed\n")
    Fake.module_config_path = staticmethod(lambda module: str(bad))

    assert fake.module_wording("AlignBeam") == {}, "a bad config must read as empty"


def test_the_report_survives_a_module_with_no_config_at_all():
    from modules.CreateReport.CreateReport import CreateReport

    class Fake:
        ID = "i04"

        def __init__(self):
            import logging

            self.log = logging.getLogger("missing-config-tests")

    Fake.module_wording = CreateReport.__dict__["module_wording"]
    Fake.module_config_path = CreateReport.__dict__["module_config_path"]
    assert Fake().module_wording("NoSuchModule") == {}


def test_a_module_config_that_is_not_a_mapping_is_ignored(tmp_path):
    """`yaml.safe_load` of an empty or list-shaped file does not give a dict, and
    `.get()` on the result would raise inside the report."""
    from modules.CreateReport.CreateReport import CreateReport

    class Fake:
        ID = "i04"

        def __init__(self):
            import logging

            self.log = logging.getLogger("odd-config-tests")

    Fake.module_wording = CreateReport.__dict__["module_wording"]
    for content in ("", "- a\n- b\n", "just a string\n"):
        path = tmp_path / "X.yaml"
        path.write_text(content)
        Fake.module_config_path = staticmethod(lambda module, p=str(path): p)
        wording = Fake().module_wording("X")
        assert isinstance(wording, dict), f"{content!r} produced {type(wording)}"
        assert wording.get("not_run", {}) == {}


def test_every_module_config_has_the_right_shape_where_the_report_reads_it():
    """Parsing is not enough - the shapes have to be right too.

    CreateReport reads two things out of other modules' YAML: `parameter_notes`
    and `not_run`. A file that parses but holds the wrong shape there fails at
    render time, which is the worst moment: the setup itself went fine, the
    operator is finished, and the only thing that breaks is the report they need
    to post.
    """
    import glob
    import os

    import yaml

    from conftest import REPO_ROOT

    problems = []
    for path in glob.glob(os.path.join(REPO_ROOT, "modules", "*", "*.yaml")):
        name = os.path.relpath(path, REPO_ROOT)
        config = yaml.safe_load(open(path))
        if config is None:
            continue
        if not isinstance(config, dict):
            problems.append(
                f"{name}: top level is {type(config).__name__}, not a mapping"
            )
            continue

        notes = config.get("parameter_notes")
        if notes is not None:
            if not isinstance(notes, dict):
                problems.append(f"{name}: parameter_notes is not a mapping")
            else:
                for key, text in notes.items():
                    if not isinstance(text, str) or not text.strip():
                        problems.append(f"{name}: parameter_notes[{key}] is not text")

        spoken = config.get("not_run")
        if spoken is not None:
            if not isinstance(spoken, dict):
                problems.append(f"{name}: not_run is not a mapping")
            else:
                if spoken.get("severity") not in ("critical", "warning"):
                    problems.append(
                        f"{name}: not_run.severity is "
                        f"{spoken.get('severity')!r}, must be critical or warning"
                    )
                for field in ("title", "message"):
                    value = spoken.get(field)
                    if not isinstance(value, str) or not value.strip():
                        problems.append(f"{name}: not_run.{field} is missing or empty")

    assert not problems, "\n".join(problems)
