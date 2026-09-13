# TestStream — not active

**This module is not loaded.** It is not named in `configure_blsetup.yaml`, so
the application never imports it and the GUI shows no button for it.

Testing the detector data stream.

Never wired up.

## If you want to bring it back

Name it in `configure_blsetup.yaml` with a `widget2update`, a
`criteria2expire` and whether it `needs_folder_to_write`, make sure the main UI
has widgets named after it, and give it a `GUI_TestStream.py` and a `TestStream.yaml`.
See `modules/README.md` for the anatomy.
