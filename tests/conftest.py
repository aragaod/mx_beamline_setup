"""Shared fixtures for the validation tests.

The application's assessment logic lives on ``base.Modules.Base``, which is a
``Config`` subclass and therefore wants a YAML config, a logger and a redis
connection at construction time. None of that is needed to exercise the
threshold arithmetic, so the tests use a stand-in that provides just the pieces
the assessment engine touches: a logger, a class name and a previous report.

This is a generalisation of the harness that used to live in
``modules/RotationAxis/test_assessments.py``, which was written by hand while
debugging one module. There is now one way of doing this rather than one per
module.
"""

import logging
import os
import sys

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MODULES_DIR = os.path.join(REPO_ROOT, "modules")


class FakeAssessor:
    """The assessment engine, unbound from Config, redis and the GUI.

    Methods are borrowed from ``Base`` rather than reimplemented, so a test
    failure here is a real failure in the shipped code.
    """

    def __init__(self, previous_report=None, class_name="Test"):
        self.log = logging.getLogger("validation-tests")
        self.class_name = class_name
        self._previous_report = previous_report or {}

    def _get_previous_report_data(self):
        return self._previous_report


def _bind_engine():
    """Attach every public assessment method from Base onto FakeAssessor."""
    from base.Modules import Base

    wanted = [
        name
        for name in dir(Base)
        if name.startswith(
            ("assess_", "check_", "validate_", "describe_", "resolve_", "format_")
        )
        or name == "_plain_value"
    ]
    for name in wanted:
        # Take the entry from the class __dict__, not getattr: getattr unwraps a
        # staticmethod into a plain function, and assigning that to a class turns
        # it back into an instance method, so `self` would be passed as the first
        # argument. Copying the descriptor keeps the binding the shipped code has.
        for owner in Base.__mro__:
            if name in owner.__dict__:
                setattr(FakeAssessor, name, owner.__dict__[name])
                break


_bind_engine()


@pytest.fixture
def assessor():
    """An assessor with no previous report."""
    return FakeAssessor()


@pytest.fixture
def assessor_with_history():
    """Build an assessor whose previous report holds the given parameters.

    Usage::

        def test_x(assessor_with_history):
            a = assessor_with_history({"FLUX": 1.0e12})
    """

    def _make(previous_parameters, class_name="Test"):
        return FakeAssessor(
            previous_report={"parameters": previous_parameters}, class_name=class_name
        )

    return _make


DEFAULT_BEAMLINE = "i04"


def load_module_yaml(module_name, yaml_name=None, beamline=DEFAULT_BEAMLINE):
    """Resolve a module's real configuration the way the application does.

    That means the shared default merged with the per-beamline override, not the
    base file alone - the base file holds only what is beamline independent, so
    on its own it has no PVs and no thresholds.
    """
    from base.GUI_Modules_Base import deep_merge, substitute_beamline

    stem = (yaml_name or f"{module_name}.yaml")[:-5]
    directory = os.path.join(MODULES_DIR, module_name)
    with open(os.path.join(directory, f"{stem}.yaml")) as handle:
        config = yaml.safe_load(handle) or {}
    override_path = os.path.join(directory, f"{stem}.{beamline}.yaml")
    if os.path.exists(override_path):
        with open(override_path) as handle:
            config = deep_merge(config, yaml.safe_load(handle) or {})
    return substitute_beamline(config, beamline)


def all_rule_blocks():
    """Every assessment_rules block in the repository, as (label, path, rules).

    Walks the YAML files as they sit on disk, including each per-beamline override
    on its own. A malformed rule must be caught in the file it was written in,
    whichever beamline it belongs to, so this deliberately does not resolve the
    layers first.
    """
    found = []
    for module_name in sorted(os.listdir(MODULES_DIR)):
        module_dir = os.path.join(MODULES_DIR, module_name)
        if not os.path.isdir(module_dir):
            continue
        for entry in sorted(os.listdir(module_dir)):
            if not entry.endswith(".yaml"):
                continue
            path = os.path.join(module_dir, entry)
            try:
                with open(path) as handle:
                    config = yaml.safe_load(handle) or {}
            except yaml.YAMLError:
                continue
            rules = (config or {}).get("assessment_rules")
            if rules:
                # An override may null a rule out; that is a removal, not a rule.
                rules = {k: v for k, v in rules.items() if v is not None}
            if rules:
                found.append((f"{module_name}/{entry}", path, rules))
    return found
