# EmailReady

Drafts the email that goes to the users starting on the beamline: what state it
is in, what was loaded for them, and how the morning's test crystal performed.

## Files

| File | What it does |
|---|---|
| `EmailReady.py` | Builds the context and picks a template. |
| `GUI_EmailReady.py` | Wizard pages, template chooser, editable preview. |
| `EmailReady.yaml` | Wizard text and template selection. |
| `templates/*.jinja2` | Thirty-three of them. |

## Why there are thirty-three templates

**They carry the same information in different words.** Users see this mail every
visit, and an identical email each time stops being read. The variety is the
point, so a template is not redundant just because another says the same thing.

That also means every template must carry the full content. If you add a fact to
one, it belongs in all of them.

## The sample name

All thirty-three name the test protein that was actually mounted. Three variables
let each keep its voice:

| Variable | Use | Example |
|---|---|---|
| `{{ test_sample }}` | mid-sentence | "a tasty **thaumatin** crystal grub" |
| `{{ test_sample_title }}` | starting a sentence or a label | "**Test Data:** Thaumatin crystal" |
| `{{ a_test_sample }}` | where an article is needed | "**an** insulin", "**a** thaumatin" |

The third exists because eleven templates said "an insulin", and of the six
registered proteins only insulin takes "an".

**When the sample is not recognised the value is "reference"** — "on a reference
crystal", "our reference test data". That is the one word that reads correctly in
all thirty-three; "test" was the obvious choice and collides eleven times,
producing "our test test data". Users get their normal mail either way; an
unrecognised sample is for staff to fix in the TestCrystal registry.

## Editing a template

- **Render it before committing.** A Jinja syntax error is invisible until the day
  that template comes up in the rotation. Two templates carried markdown-style
  escaping (`test\_data\_available`) and would crash when selected; the tests now
  catch that.
- **Everything inside `{% if test_data_available %}`** only appears when the test
  crystal ran. The `{% else %}` branch must still read as a complete sentence.
- **Do not hardcode a protein name.** A test enforces it.
- Run `python3 -m pytest tests/validation/test_email_templates.py` — it renders
  every template with and without test data, with each protein, and with the
  fallback.

## Where the numbers come from

Today's TestCrystal report: `Aimless_Rmeas_low_res`, `ISa`, `Test_sample`. Only
today's, which is why the current key names are used directly rather than
accommodating old ones.
