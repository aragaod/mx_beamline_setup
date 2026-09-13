"""Every module directory has a README, and its claims stay true.

These exist because documentation rots silently. The checks are deliberately
narrow: they test statements that would become wrong if the code moved on, not
prose quality.
"""

import os
import re

import pytest
import yaml

from conftest import MODULES_DIR, REPO_ROOT

MODULES = sorted(
    name
    for name in os.listdir(MODULES_DIR)
    if os.path.isdir(os.path.join(MODULES_DIR, name))
    and not name.startswith((".", "__"))
)

with open(os.path.join(REPO_ROOT, "configure_blsetup.yaml")) as handle:
    LIVE = set(yaml.safe_load(handle)["modules"])


def test_the_modules_directory_has_an_overview():
    assert os.path.exists(os.path.join(MODULES_DIR, "README.md"))


@pytest.mark.parametrize("module", MODULES)
def test_every_module_has_a_readme(module):
    assert os.path.exists(
        os.path.join(MODULES_DIR, module, "README.md")
    ), f"{module} has no README.md - see modules/README.md for the shape"


@pytest.mark.parametrize("module", MODULES)
def test_a_readme_names_the_files_that_exist(module):
    """A README listing a file that has been deleted is worse than no README."""
    directory = os.path.join(MODULES_DIR, module)
    text = open(os.path.join(directory, "README.md")).read()
    present = {
        entry
        for entry in os.listdir(directory)
        if entry.endswith((".py", ".yaml")) and entry != "__init__.py"
    }
    # Only the Files table makes claims about what is there. Prose elsewhere may
    # name a file that ought to be created, or one in a different directory.
    table = re.search(r"## Files\n(.*?)(?=\n## |\Z)", text, re.S)
    if not table:
        return
    named = set(re.findall(r"`([\w./-]+\.(?:py|yaml))`", table.group(1)))
    stale = {n for n in named if "/" not in n and n not in present}
    assert (
        not stale
    ), f"{module}/README.md names files that are not there: {sorted(stale)}"


@pytest.mark.parametrize("module", sorted(set(MODULES) - LIVE))
def test_an_inactive_module_says_so(module):
    """Someone opening one of these should learn immediately that it is not run."""
    text = open(os.path.join(MODULES_DIR, module, "README.md")).read()
    assert (
        "not active" in text.lower() or "not loaded" in text.lower()
    ), f"{module} is not in configure_blsetup.yaml but its README does not say so"


@pytest.mark.parametrize("module", sorted(LIVE & set(MODULES)))
def test_a_live_module_is_not_described_as_inactive(module):
    text = open(os.path.join(MODULES_DIR, module, "README.md")).read()
    assert (
        "— not active" not in text
    ), f"{module} is live but its README calls it inactive"


@pytest.mark.parametrize("module", sorted(LIVE & set(MODULES)))
def test_a_readme_that_mentions_an_override_has_one(module):
    """The per-beamline file is the thing people will look for first."""
    directory = os.path.join(MODULES_DIR, module, "")
    text = open(os.path.join(directory, "README.md")).read()
    for name in re.findall(r"`([\w.]+\.i04\.yaml)`", text):
        assert os.path.exists(
            os.path.join(directory, name)
        ), f"{module}/README.md names {name}, which does not exist"


def test_the_tests_readme_names_every_test_file():
    """The table is the index. A file missing from it is a file nobody knows runs.

    Six files had accumulated outside the table before this check existed.
    """
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    present = set()
    for root, _, names in os.walk(tests_dir):
        if "__pycache__" in root:
            continue
        for name in names:
            if name.startswith("test_") and name.endswith(".py"):
                present.add(
                    os.path.relpath(os.path.join(root, name), tests_dir).replace(
                        os.sep, "/"
                    )
                )

    text = open(os.path.join(tests_dir, "README.md")).read()
    named = set(re.findall(r"`(test_[\w./]+\.py|validation/test_[\w.]+\.py)`", text))
    missing = present - named
    assert not missing, f"tests/README.md does not mention: {sorted(missing)}"
