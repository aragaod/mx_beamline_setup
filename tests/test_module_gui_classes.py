"""Every module's GUI class can actually load its configuration.

This is the gap that let a real break through. The suite tested the resolver, the
merge and every module's rules, but nothing ever imported a `GUI` class - so when
`read_config` moved onto `BaseGUI` and the per-module copies were deleted, the
seven classes that had never inherited `BaseMGUI` lost the method entirely and
every one of them failed at the moment the operator pressed its button:

    CRITICAL Failed with error 'GUI' object has no attribute 'read_config'

Only RotationAxis and SampleLoad inherited it. The tests all passed.
"""

import importlib
import os

import pytest

from conftest import MODULES_DIR

GUI_MODULES = sorted(
    name
    for name in os.listdir(MODULES_DIR)
    if os.path.isdir(os.path.join(MODULES_DIR, name))
    and os.path.exists(os.path.join(MODULES_DIR, name, f"GUI_{name}.py"))
)


def _gui_class(module):
    imported = importlib.import_module(f"modules.{module}.GUI_{module}")
    return getattr(imported, "GUI", None)


def test_some_gui_modules_were_found():
    assert len(GUI_MODULES) > 5


@pytest.mark.parametrize("module", GUI_MODULES)
def test_the_gui_class_can_read_its_config(module):
    """The method has to be reachable, not merely defined somewhere."""
    gui = _gui_class(module)
    if gui is None:
        pytest.skip(f"{module} has no GUI class")
    assert hasattr(gui, "read_config"), (
        f"{module}'s GUI class cannot load its configuration. It needs to inherit "
        f"BaseMGUI, which is where read_config lives."
    )


@pytest.mark.parametrize("module", GUI_MODULES)
def test_the_gui_class_can_find_its_config_files(module):
    """config_paths must name files that exist, including the module whose YAML
    is named after the GUI file rather than the module."""
    gui = _gui_class(module)
    if gui is None:
        pytest.skip(f"{module} has no GUI class")
    if not hasattr(gui, "config_paths"):
        pytest.fail(f"{module}'s GUI class does not inherit BaseMGUI")

    instance = gui.__new__(gui)
    base_path, _ = gui.config_paths(instance, beamline="i04")
    assert os.path.exists(base_path), (
        f"{module}'s GUI would look for {os.path.basename(base_path)}, which is "
        f"not there. A module whose YAML is named differently sets config_basename."
    )


@pytest.mark.parametrize("module", GUI_MODULES)
def test_the_gui_class_actually_loads_the_config(module):
    """End to end: resolve the layers and substitute, as the application does."""
    gui = _gui_class(module)
    if gui is None:
        pytest.skip(f"{module} has no GUI class")
    instance = gui.__new__(gui)
    config = gui.read_config(instance, beamline="i04")
    assert config, f"{module}'s configuration resolved to nothing"
    assert "{BEAMLINE}" not in repr(config)
