# CreateDirectories

Creates the day's output folders under the current visit, one per module, so the
other modules have somewhere to write images.

## Files

| File | What it does |
|---|---|
| `CreateDirectories.py` | Works out the visit and creates the folders. |

No YAML and no GUI file — it runs without wizard pages.

## What it does

Builds `/dls/{ID}/data/{year}/{visit}/beamline_setup/{YYYYMMDD}/<Module>/` for
each module, and stores the result in redis under `directories`, which is what
`MOD_Base.check_folder_is_setup()` reads. A module declaring
`needs_folder_to_write: True` in the top-level config will refuse to run until
this has happened.

**So this module runs first, and everything else depends on it.** It is also the
best test of `{BEAMLINE}` substitution on real paths.

## Things that will catch you out

- It overrides its own `criteria2expire` in code rather than taking it from the
  config, because it does not follow the same expiry rules as the others. The
  comment in the source calls this a hack, and it is.
- It works the visit out from the date, so it depends on the visit directory
  following the usual naming.
