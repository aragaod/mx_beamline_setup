"""Every email template must render.

There are 33 of them and the variety is deliberate: they carry the same
information in different words so that users who see the mail every visit do not
stop reading it. That only works if every one of them actually renders - a broken
template is invisible until the day it is chosen.

Two were broken until 2026-08-31. They had been written with markdown-style
escaping (`test\\_data\\_available`, `beauty\\!`) which is meaningless inside a
Jinja expression, so selecting either raised TemplateSyntaxError.
"""

import glob
import os

import jinja2
import pytest

from conftest import REPO_ROOT

TEMPLATE_DIR = os.path.join(REPO_ROOT, "modules", "EmailReady", "templates")
TEMPLATES = sorted(
    os.path.basename(p) for p in glob.glob(os.path.join(TEMPLATE_DIR, "*.jinja2"))
)

CONTEXT = dict(
    human_date="Sunday, 31 August 2026",
    beamline="i04",
    i04_staff_member="A Beamline Scientist",
    optional_tip="Remember to credit the beamline in publications.",
    puck_info=None,
    rmeas_lowres="3.6",
    ISa="31.65",
    test_sample="thaumatin",
    test_sample_title="Thaumatin",
    a_test_sample="a thaumatin",
)

# What EmailReady supplies when the master file path matches nothing in the
# registry. "reference" is the one word that reads correctly in all thirty-three
# templates - "on a reference crystal", "our reference test data" - which is why
# it was chosen over "test", which collides eleven times ("our test test data").
UNRECOGNISED = dict(
    test_sample="reference", test_sample_title="Reference", a_test_sample="a reference"
)


@pytest.fixture(scope="module")
def environment():
    return jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR))


def test_there_are_templates_to_check():
    assert len(TEMPLATES) > 25, "the template set has shrunk unexpectedly"


@pytest.mark.parametrize("name", TEMPLATES)
def test_renders_with_test_data(environment, name):
    rendered = environment.get_template(name).render(
        test_data_available=True, **CONTEXT
    )
    assert rendered.strip()


@pytest.mark.parametrize("name", TEMPLATES)
def test_renders_without_test_data(environment, name):
    """The else branch runs whenever the test crystal was not collected."""
    rendered = environment.get_template(name).render(
        test_data_available=False, **CONTEXT
    )
    assert rendered.strip()


@pytest.mark.parametrize("name", TEMPLATES)
def test_quotes_the_statistics_when_they_are_available(environment, name):
    """Every template is supposed to carry the same information."""
    rendered = environment.get_template(name).render(
        test_data_available=True, **CONTEXT
    )
    assert "3.6" in rendered, f"{name} does not quote Rmeas"
    assert "31.65" in rendered, f"{name} does not quote ISa"


@pytest.mark.parametrize("name", TEMPLATES)
def test_no_markdown_escaping_leaks_into_jinja(environment, name):
    r"""`\_` and `\!` are markdown, not Jinja, and break the parser."""
    source = open(os.path.join(TEMPLATE_DIR, name)).read()
    assert "\\_" not in source, f"{name} has markdown-escaped underscores"
    assert "\\!" not in source, f"{name} has markdown-escaped exclamation marks"


# --------------------------------------------------------------------------
# Every template names the sample that was mounted
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", TEMPLATES)
def test_names_the_sample(environment, name):
    """All thirty-three, not just the seventeen that used to say "insulin".

    The variety is in the wording, not the content: every template is supposed to
    tell the user the same things.
    """
    rendered = environment.get_template(name).render(
        test_data_available=True, **CONTEXT
    )
    assert "thaumatin" in rendered.lower(), f"{name} does not name the test sample"


@pytest.mark.parametrize("name", TEMPLATES)
def test_reads_correctly_when_the_sample_is_not_recognised(environment, name):
    """The fallback must not produce "our test test data" or "a crystal"."""
    context = dict(CONTEXT)
    context.update(UNRECOGNISED)
    rendered = environment.get_template(name).render(
        test_data_available=True, **context
    )
    assert "reference" in rendered.lower()
    assert "reference reference" not in rendered.lower()
    assert "test test" not in rendered.lower()


@pytest.mark.parametrize("name", TEMPLATES)
def test_no_protein_name_is_left_hardcoded(environment, name):
    """Seventeen templates said "insulin" regardless of what was mounted."""
    source = open(os.path.join(TEMPLATE_DIR, name)).read().lower()
    for protein in ("insulin", "thaumatin", "lysozyme", "thermolysin"):
        assert protein not in source, f"{name} still hardcodes {protein}"


@pytest.mark.parametrize("name", TEMPLATES)
def test_article_agreement(environment, name):
    """`an insulin` but `a thaumatin` - eleven templates needed the article."""
    for context_extra, wrong in (
        (
            dict(
                test_sample="insulin",
                test_sample_title="Insulin",
                a_test_sample="an insulin",
            ),
            "a insulin",
        ),
        (CONTEXT, "an thaumatin"),
    ):
        context = dict(CONTEXT)
        context.update(context_extra)
        rendered = environment.get_template(name).render(
            test_data_available=True, **context
        )
        assert wrong not in rendered.lower(), f"{name} produces {wrong!r}"
