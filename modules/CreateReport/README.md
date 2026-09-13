# CreateReport

Collects every module's stored result for today, renders the HTML report, and
posts it to the electronic logbook.

## Files

| File | What it does |
|---|---|
| `CreateReport.py` | Gathers today's reports and drives the render and post. |
| `posters.py` | Posts to the eLog. A fork of the `beamline` library's `ElogPoster` that has diverged. |
| `submit_logbook.py` | The logbook submission itself. |
| `GUI_CreateReport.py` | Wizard pages and the preview dialog. |
| `templates/beamline_logbook_template.jinja2` | The report itself. |
| `GUI_CreateReport.yaml` | Wizard text. |

## How it finds what to report

It reads every redis field whose name ends in today's date, so a module that was
not run today simply does not appear. That is why the report has no fixed section
order and no indication that a module was skipped — backlog item **F1**, and it
matters because staff have forgotten to run modules and nothing said so.

## The report table

Four columns: Parameter, Value, **Criterion**, Status.

- **Value** shows `display`, a formatted copy. The raw `value` stays in redis at
  full precision so tomorrow's comparison is made against the real number.
- **Criterion** says *why* a row is the colour it is — `>= 9e+11`,
  `Δ ≤10% vs yest`, `= yesterday` — so the reader does not need the YAML. It comes
  from the assessment engine, which knows the check type and limits at the moment
  it decides the status.
- Rows marked `hidden` are skipped entirely. Rows that could not be assessed show
  "not checked" with the reason on hover, rather than a blank cell that looks like
  a pass.

## Which logbook

`BLrelease` selects it: `development` posts to the `devl` server, `production` to
the real one. **Test against development** — it is the only way to see the
rendered report end to end, and nothing else exercises the post.

## Things that will catch you out

- `posters.py` is a fork of the library's version and the two have diverged; the
  library takes the entry type as a parameter, this hardcodes it.
- Images are uploaded twice, once at low quality for the inline view and once at
  full quality behind a link.
- The template is rendered with Jinja, so a syntax error in it is invisible until
  the day it runs. `tests/validation/test_email_templates.py` does that for the
  email templates; the report template is checked by the hidden-parameter tests.
