"""Every `self.something()` a class makes must exist on that class.

Three separate crashes in one day on 2026-08-31, all the same shape and none
caught by the suite:

  * `'BL_MainWindow' object has no attribute 'record_oncall'` - the method went on
    the module Base, the main window inherits the application Base.
  * `'AlignBeam' object has no attribute 'what_to_do_about'` - the helper went on
    `OpticsChecks`, the caller is `AlignBeam`, same file.
  * `QtWidgets` used in `TestCrystal.py` without being imported.

`python -m py_compile` cannot see any of them, because an attribute is only
resolved when the line runs - and these lines run on a Tuesday morning in front
of an operator, not in a test.

This walks the AST of every module, finds each `self.name(...)` call inside a
class body, and asserts the class really has `name`. It is deliberately narrow:
only direct `self.x()` calls, so `self.ui.show_warning()` and `self.log.info()`
are not its business.
"""

import ast
import importlib
import os

import pytest

from conftest import MODULES_DIR, REPO_ROOT

# Attributes that genuinely arrive at runtime. Each is listed with its reason,
# so the list stays a set of known facts rather than a place to silence failures.
RUNTIME_ATTRIBUTES = {
    # Bound onto every module instance by
    # `Base.add_update_widget_to_module_instances()` after construction, so it
    # cannot be found on the class.
    "update_widget",
    # `APP_GUI` is a mixin. It is only ever used as
    # `BL_MainWindow(APP_GUI, APP_Base)`, where `get`/`set` come from Config
    # through the other parent - the class alone is not meant to resolve them.
    "get",
    "set",
}


def python_files():
    found = [os.path.join(REPO_ROOT, "beamline_setup.py")]
    for root, _, names in os.walk(MODULES_DIR):
        if "__pycache__" in root or ".mypy_cache" in root:
            continue
        found += [
            os.path.join(root, n)
            for n in names
            if n.endswith(".py") and n != "__init__.py"
        ]
    for root, _, names in os.walk(os.path.join(REPO_ROOT, "base")):
        if "__pycache__" in root:
            continue
        found += [
            os.path.join(root, n)
            for n in names
            if n.endswith(".py") and n != "__init__.py"
        ]
    return sorted(found)


def import_path(path):
    """Dotted module name for a file inside the repository."""
    relative = os.path.relpath(path, REPO_ROOT)
    return relative[:-3].replace(os.sep, ".")


def self_calls(class_node):
    """Names called directly as `self.name(...)`, minus those it assigns itself.

    A class that does `self.deserialise = deserialise` in `__init__` and later
    calls `self.deserialise(...)` is fine - the attribute exists on the instance
    even though it is not on the class. Those are subtracted rather than
    exempted by name, so the check stays strict about everything else.
    """
    called, assigned = set(), set()
    for node in ast.walk(class_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            called.add(node.func.attr)
        for target in getattr(node, "targets", []):
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                assigned.add(target.attr)
    return called - assigned


CASES = []
for path in python_files():
    try:
        tree = ast.parse(open(path).read())
    except SyntaxError:
        continue
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            CASES.append((path, node.name, sorted(self_calls(node))))


@pytest.mark.parametrize(
    "path,class_name,called",
    CASES,
    ids=[f"{os.path.basename(p)}::{c}" for p, c, _ in CASES],
)
def test_every_self_call_resolves(path, class_name, called):
    if not called:
        return
    try:
        module = importlib.import_module(import_path(path))
    except Exception as error:
        pytest.skip(f"{path} cannot be imported here: {error}")
    owner = getattr(module, class_name, None)
    if owner is None:
        pytest.skip(f"{class_name} is not exported from {path}")

    missing = [
        name
        for name in called
        if name not in RUNTIME_ATTRIBUTES and not hasattr(owner, name)
    ]
    assert not missing, (
        f"{class_name} in {os.path.relpath(path, REPO_ROOT)} calls "
        f"self.{{{', '.join(missing)}}}() but has no such attribute - this is the "
        f"crash that only appears when that line runs"
    )
