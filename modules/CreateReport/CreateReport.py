from base import MOD_Base

from .submit_logbook import Submit_Logbook

from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore

from modules.CreateReport.GUI_CreateReport import GUI

from base import MOD_Base
from .submit_logbook import Submit_Logbook
from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore
from modules.CreateReport.GUI_CreateReport import GUI
import os  # Make sure os is imported

from base import MOD_Base
from .submit_logbook import Submit_Logbook
from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore
from modules.CreateReport.GUI_CreateReport import GUI
import os
import yaml as config_loader

from base import MOD_Base
from .submit_logbook import Submit_Logbook
from datetime import datetime
from PyQt5.QtWidgets import QWizard
from PyQt5 import QtCore
from modules.CreateReport.GUI_CreateReport import GUI
import os


class CreateReport(MOD_Base):
    def order_and_fill_gaps(self, payload_modules, everything):
        """Put the sections in checklist order and say which modules did not run.

        Two problems, both from the report being built out of whatever redis
        happened to return. The sections came out in arbitrary order, so the
        report did not read like the checklist staff had just worked through. And
        a module that was skipped simply had no section, which is indistinguishable
        from one that has never existed - staff have forgotten to run modules and
        nothing in the report said so.

        Which modules are expected is not hardcoded: any module that has ever
        written a report is one that should have a section. That way a new module
        is covered the day after its first run, and a retired one stops being
        asked about once its reports age out of redis.
        """
        import re

        today = datetime.now().strftime("%Y%m%d")
        ever_reported = {
            match.group(1)
            for key in everything
            if (match := re.match(r"([A-Za-z]+)_report_\d{8}$", key))
        }

        declared = list(self.config.get("modules", {}))
        ordered = {}
        missing = []

        for module in declared:
            key = f"{module}_report_{today}"
            if key in payload_modules:
                ordered[key] = payload_modules[key]
            elif module in ever_reported:
                # Not every skipped module is equally serious, and the report
                # should not say so in one flat yellow voice. The wording lives
                # in the skipped module's own YAML, so that module owns its text.
                spoken = self.module_wording(module).get("not_run", {})
                ordered[key] = {
                    "not_run": True,
                    "table_title": spoken.get("title", module),
                    "not_run_severity": spoken.get("severity", "warning"),
                    "not_run_message": spoken.get("message"),
                    "parameters": {},
                }
                missing.append(module)

        # Anything reported today that the config does not declare still belongs
        # in the report; better an out-of-order section than a lost one.
        for key, value in payload_modules.items():
            ordered.setdefault(key, value)

        if missing:
            self.log.warning(
                f"These modules were not run today and are marked as such in the "
                f"report: {', '.join(missing)}"
            )
        return ordered

    @staticmethod
    def module_config_path(module):
        """A module's own YAML, whichever of the two names it uses.

        Most are `<Module>/<Module>.yaml`, but BeamstopAlignment and RemoteAccess
        keep theirs as `GUI_<Module>.yaml`. Anything reading another module's
        configuration has to accept both, or it silently finds nothing for those
        two - which is exactly what happened to their parameter notes.
        """
        modules_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in (f"{module}.yaml", f"GUI_{module}.yaml"):
            candidate = os.path.join(modules_dir, module, name)
            if os.path.exists(candidate):
                return candidate
        return None

    def module_wording(self, module):
        """Read another module's YAML for the text it owns about itself.

        Never raises: a module with no YAML, or one that will not parse, must not
        be able to stop the report being written.
        """
        path = self.module_config_path(module)
        if not path:
            return {}
        try:
            with open(path) as handle:
                loaded = config_loader.safe_load(handle)
        except Exception as error:
            self.log.warning(f"Could not read {module}'s configuration: {error}")
            return {}
        # `or {}` is not enough: a YAML file holding a list or a bare string
        # loads as a truthy non-dict, and `.get()` on it raises inside the
        # report. An empty file loads as None.
        if not isinstance(loaded, dict):
            if loaded is not None:
                self.log.warning(
                    f"{module}'s configuration is a {type(loaded).__name__}, "
                    f"not a mapping; ignoring it"
                )
            return {}
        return loaded

    def attach_parameter_notes(self, payload_modules):
        """Add each module's parameter_notes to its report, for the render.

        The notes explain the parameters whose names do not speak for themselves,
        and they are configuration rather than data - the same sentence every day.
        So they are read from the module YAML at render time instead of being
        stored in redis with every report, which would put the same paragraph in
        the archive several hundred times.

        A module without notes simply gets none; the template only writes the
        block when there is something to say.
        """
        from base.GUI_Modules_Base import deep_merge, substitute_beamline

        modules_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        for key, report in payload_modules.items():
            if not isinstance(report, dict):
                continue
            module = key.split("_report_")[0]
            directory = os.path.join(modules_dir, module)
            base_path = os.path.join(directory, f"{module}.yaml")
            if not os.path.exists(base_path):
                continue
            try:
                with open(base_path) as handle:
                    config = config_loader.safe_load(handle) or {}
                override = os.path.join(directory, f"{module}.{self.ID}.yaml")
                if os.path.exists(override):
                    with open(override) as handle:
                        config = deep_merge(
                            config, config_loader.safe_load(handle) or {}
                        )
                notes = substitute_beamline(config, self.ID).get("parameter_notes")
            except Exception as error:
                self.log.warning(f"Could not read notes for {module}: {error}")
                continue
            if notes:
                report["parameter_notes"] = notes

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

    def launch_GUI(self):
        self.CreateReport_WZ = QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.CreateReport_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.CreateReport_WZ.button(QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.CreateReport_WZ.button(QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.CreateReport_WZ.button(QWizard.NextButton).clicked.connect(self.next)
        self.CreateReport_WZ.button(QWizard.BackButton).clicked.connect(self.back)

        # Handle pressing the top right X button
        self.CreateReport_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.CreateReport_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.CreateReport_WZ.show()

    def next(self):
        self.log.debug(f"Next button pressed.")
        self.drive()

    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def drive(self):
        try:
            if self.before():
                self.set_running()
                self.log.debug(
                    f"Trying to trigger run method on {self.class_name} module class."
                )
                payload_modules = {}
                try:
                    all = self.get_all()
                    for item in all.keys():
                        if f'_report_{self.now.strftime("%Y%m%d")}' in item:
                            payload_modules[item] = all[item]
                except Exception as e:
                    self.log.critical(f"Failed to get reporting data with error {e}")
                payload_modules = self.order_and_fill_gaps(payload_modules, all)
                self.attach_parameter_notes(payload_modules)
                self.log.info(f"payload_modules is: {payload_modules}")
                elog = Submit_Logbook(
                    module_config=self.config,
                    original_class_name=self.class_name,
                    log=self.log,
                    data=payload_modules,
                    username=self.username,
                )

                content = elog.prepare_logbook_entry()

                # --- DEBUGGING CODE to save the HTML file ---
                try:
                    report_dir = self.get("directories")[self.class_name]
                    debug_file_path = os.path.join(report_dir, "beamline_report.html")
                    with open(debug_file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    self.log.info(
                        f"DEBUG: HTML content saved for inspection to: {debug_file_path}"
                    )
                except Exception as e:
                    self.log.error(
                        f"DEBUG: Failed to save debug HTML file with error: {e}"
                    )
                # --- END DEBUGGING CODE ---

                if not content or not content.strip():
                    self.log.error("Generated logbook content is empty! Aborting post.")
                    self.set_status_false()
                    return False

                response = elog.submit_logbook(
                    title=f'Beamline setup {self.now.strftime("%A %d/%m/%Y")}',
                    content=content,
                )

                if response.status_code == 200:
                    # The setup is finished once the report is posted, so this
                    # is the second of the two timestamps the overtime report
                    # needs.
                    self.record_oncall(
                        "report_posted",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    self.set_status_true()
                else:
                    self.set_status_false()
            else:
                return False
        except Exception as e:
            self.log.critical(f"Failed with error {e}")
            self.set_status_false()

        finally:
            self.log.debug("Executing finally block to stop module")
            self.set_stopped()
