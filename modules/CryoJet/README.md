# CryoJet — not active

**This module is not loaded.** It is not named in `configure_blsetup.yaml`, so
the application never imports it and the GUI shows no button for it.

Checking the cryostream — temperature, flow, and whether it is where it should
be.

Never wired up. The `beamline` library has a `cryo` device on i04, so the data is
available if this is ever wanted. It would be a straightforward module: a few PVs
and a deadband against yesterday.

## If you want to bring it back

Name it in `configure_blsetup.yaml` with a `widget2update`, a
`criteria2expire` and whether it `needs_folder_to_write`, make sure the main UI
has widgets named after it, and give it a `GUI_CryoJet.py` and a `CryoJet.yaml`.
See `modules/README.md` for the anatomy.
