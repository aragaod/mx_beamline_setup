# BeamCentre — not active

**This module is not loaded.** It is not named in `configure_blsetup.yaml`, so
the application never imports it and the GUI shows no button for it.

Determining the beam centre on the detector.

`BeamCentre.py` is an 808-byte stub from 2019. The substantial version was
`BeamCentre_AS.py`, 672 lines carried over from the Australian Synchrotron, which
**moved out of this repository on 2026-08-31** to:

```
/dls/science/groups/i04/Python/applications/auto_beamcentre_development/
```

It holds the working method for driving **fit2d**, which is wanted back. Work to
make it read our HDF5 files and run under Python 3 is happening in that tree. Git
history here still has it if needed.

Only referenced from the unused `configure_blsetup_devel_2024.yaml`.

## If you want to bring it back

Name it in `configure_blsetup.yaml` with a `widget2update`, a
`criteria2expire` and whether it `needs_folder_to_write`, make sure the main UI
has widgets named after it, and give it a `GUI_BeamCentre.py` and a `BeamCentre.yaml`.
See `modules/README.md` for the anatomy.
