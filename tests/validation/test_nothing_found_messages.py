"""A module that finds nothing must say so.

SampleLoad wrote a report for an empty robot dewar and said nothing about it;
BeamstopAlignment stored a single consistency row with no positions and said
nothing either. In a report that lists only what it found, "nothing was there"
and "everything was fine" look identical, and the reader cannot tell which they
are looking at - or whether the check ran at all.
"""

import os
import re

import jinja2
import pytest

from conftest import MODULES_DIR, REPO_ROOT

TEMPLATE = os.path.join(
    REPO_ROOT,
    "modules",
    "CreateReport",
    "templates",
    "beamline_logbook_template.jinja2",
)


def _render(module_key, module_data):
    source = open(TEMPLATE).read()
    # Render just the branch for this module, with the surrounding loop supplied.
    env = jinja2.Environment()
    # Slice from the first branch of the chain. PATH 1 is an elif now that the
    # not-run placeholder comes before it, so starting there leaves an orphan.
    body = source[
        source.index("{% if module_data.not_run %}") : source.index(
            '{% endif %}\n\n        <tr>\n            <td colspan="8"><hr>'
        )
    ]
    wrapper = (
        "{% for module_key, module_data in payload.items() %}"
        + body
        + "{% endif %}{% endfor %}"
    )
    return env.from_string(wrapper).render(payload={module_key: module_data})


def test_an_empty_dewar_is_stated():
    rendered = _render(
        "SampleLoad_report_20260831",
        {
            "no_pucks_message": "No pucks are loaded in the robot dewar.",
            "processed_pucks": [],
            "parameters": {},
        },
    )
    assert "No pucks are loaded" in rendered


def test_a_loaded_dewar_says_nothing_about_being_empty():
    rendered = _render(
        "SampleLoad_report_20260831",
        {
            "processed_pucks": [
                {"proposal": "cm1", "locations": [1], "pucks": ["ABC"]}
            ],
            "parameters": {},
        },
    )
    assert "No pucks are loaded" not in rendered


def test_no_beamstop_collections_is_stated():
    rendered = _render(
        "BeamstopAlignment_report_20260831",
        {
            "no_data_message": "No beamstop collections were found in the last 2 hours,",
            "table_title": "Beamstop Positions",
            "parameters": {},
        },
    )
    assert "No beamstop collections were found" in rendered


# --------------------------------------------------------------------------
# The modules have to set the messages, not only the template render them
# --------------------------------------------------------------------------


def test_sampleload_sets_the_message_when_no_pucks_are_found():
    source = open(os.path.join(MODULES_DIR, "SampleLoad", "SampleLoad.py")).read()
    assert "no_pucks_message" in source
    assert re.search(
        r'if not any\(.*\.get\("pucks"\)', source
    ), "the message must be driven by there being no pucks, not by something else"


def test_beamstop_sets_the_message_when_no_collections_are_found():
    source = open(
        os.path.join(MODULES_DIR, "BeamstopAlignment", "BeamstopAlignment.py")
    ).read()
    assert "no_data_message" in source
    assert (
        "if not ordered_keys" in source
    ), "the message must be driven by the search returning nothing"


# --------------------------------------------------------------------------
# An empty table is worse than no table
# --------------------------------------------------------------------------


def _render_dewar_contents(module_data):
    source = open(TEMPLATE).read()
    start = source.index("{# Table 2: Robot Dewar Contents")
    end = source.index("{# --- PATH 2.5")
    block = source[start:end].rsplit("{% endif %}", 1)[0] + "{% endif %}"
    return jinja2.Environment().from_string(block).render(module_data=module_data)


EMPTY_DEWAR = {
    "table_title": "Robot Dewar contents",
    "parameters": {f"Puck name in location {n:02d}": "" for n in range(1, 38)},
}


def test_an_empty_dewar_renders_no_table_at_all():
    """The rows are filtered on having a value, so the heading and column headers
    would otherwise stand alone over nothing - which reads as a table that failed
    to load rather than a dewar that is empty."""
    assert _render_dewar_contents(EMPTY_DEWAR).strip() == ""


def test_one_loaded_position_brings_the_table_back():
    loaded = dict(EMPTY_DEWAR, parameters=dict(EMPTY_DEWAR["parameters"]))
    loaded["parameters"]["Puck name in location 01"] = "ABC123"
    rendered = _render_dewar_contents(loaded)
    assert "ABC123" in rendered
    assert "Robot Dewar contents" in rendered


def test_only_occupied_positions_are_listed():
    """Thirty-three blank rows around four real ones is noise, not information."""
    loaded = dict(EMPTY_DEWAR, parameters=dict(EMPTY_DEWAR["parameters"]))
    for position, puck in (("01", "AAA"), ("19", "BBB")):
        loaded["parameters"][f"Puck name in location {position}"] = puck
    rendered = _render_dewar_contents(loaded)
    assert rendered.count("<tr>") == 4, (
        "expected the title row, the header row and one row per occupied "
        "position - not one per position in the dewar"
    )


# --------------------------------------------------------------------------
# F11: the operator is told at the time, not only in the report afterwards
# --------------------------------------------------------------------------


def _handler_source(module, marker):
    source = open(os.path.join(MODULES_DIR, module, f"{module}.py")).read()
    start = source.index(marker)
    return source[start : start + 2500]


def test_sampleload_warns_but_stays_ticked():
    """An empty dewar is a legitimate state - during a shutdown it is the
    expected one - so this is worth telling the operator in case they expected
    pucks, and not worth refusing over."""
    body = _handler_source("SampleLoad", "no_pucks_message")
    assert "show_urgent_warning" in body
    assert "acceptButton" in body, "acknowledge only"
    assert (
        "set_status_false" not in body
    ), "an empty dewar does not mean the module failed to do its job"
    assert "EPICS" in body, "the operator should know where to look if pucks are loaded"


def test_beamstop_offers_cancel_and_unticks_when_cancelled():
    """A beamstop check that compared nothing has not been made, whatever the
    report says."""
    body = _handler_source("BeamstopAlignment", "no_data_message")
    assert "show_urgent_warning" in body
    assert "Proceed Anyway" in body and "Cancel" in body
    assert "set_status_false" in body, "cancelling must untick the module"
    assert (
        "file names" in body
    ), "the likely cause is worth naming, since the operator can go and fix it"


def test_both_popups_say_the_same_as_the_report():
    """The popup and the report line should not drift apart."""
    for module, key, phrase in (
        ("SampleLoad", "no_pucks_message", "no pucks"),
        ("BeamstopAlignment", "no_data_message", "beamstop"),
    ):
        source = open(os.path.join(MODULES_DIR, module, f"{module}.py")).read()
        assert phrase in source.lower()
        assert key in source
