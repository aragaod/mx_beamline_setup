# Close

Ends the session. The last button on the checklist.

## Files

| File | What it does |
|---|---|
| `Close.py` | A `MOD_Base` subclass that overrides `run()`. |

No YAML and no GUI file — there are no wizard pages.

## What it does

Almost nothing, deliberately. It records that the beamline was closed and then
quits the application. The comment in the source is honest that the date matters
less here than the eLog post and the user email, which carry the real record.

The interesting part is `update_widget`, which is attached to this module in
`beamline_setup.py` rather than inherited: for every other module updating the
widget means ticking a checkbox or setting a date, and for this one it means
killing the app.

If you ever want to capture something at the end of a session — how long the setup
took, which modules were skipped — this is where it would go.
