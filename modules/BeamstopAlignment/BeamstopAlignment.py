from base import MOD_Base
from PyQt5 import QtCore, QtWidgets
from modules.BeamstopAlignment.GUI_BeamstopAlignment import GUI
from modules.BeamstopAlignment.BeamstopAnalysis import BeamstopAnalyzer
import os
import yaml as config_loader
from datetime import datetime
import pprint
from PIL import Image
import logging

from base import MOD_Base
from PyQt5 import QtCore, QtWidgets
from modules.BeamstopAlignment.GUI_BeamstopAlignment import GUI
from modules.BeamstopAlignment.BeamstopAnalysis import BeamstopAnalyzer
import os
import yaml as config_loader
from datetime import datetime
import pprint
from PIL import Image
import logging

# --- SILENCE NOISY LIBRARIES ---
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)


class BeamstopAlignment(MOD_Base):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

        # Load config immediately
        self.read_module_config()

        # Instantiate the helper logic
        self.analyzer = BeamstopAnalyzer(self.log)

    def read_module_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "GUI_BeamstopAlignment.yaml")
        self.config_module = {}
        try:
            with open(file_path, "r") as f:
                self.config_module = config_loader.load(
                    f, Loader=config_loader.FullLoader
                )
        except Exception as e:
            self.log.error(f"Failed to load module config: {e}")

    def launch_GUI(self):
        self.BeamstopAlignment_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")

        # Explicitly assign config to UI before setupUi
        self.ui.config = self.config_module

        if "display_configuration" in self.ui.config:
            self.ui.config["display_configuration"] = self.ui.config[
                "display_configuration"
            ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.BeamstopAlignment_WZ)

        # Connect Buttons
        self.BeamstopAlignment_WZ.button(
            QtWidgets.QWizard.FinishButton
        ).clicked.connect(self.set_status_true)
        self.BeamstopAlignment_WZ.button(
            QtWidgets.QWizard.CancelButton
        ).clicked.connect(self.set_status_false)
        self.BeamstopAlignment_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.BeamstopAlignment_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )
        self.BeamstopAlignment_WZ.rejected.connect(self.reject)

        self.BeamstopAlignment_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.BeamstopAlignment_WZ.show()

    def next(self):
        self.log.debug(f"Next button pressed. Starting Analysis...")
        self.drive_analysis()

    def back(self):
        self.log.debug("Back button pressed")

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def drive_analysis(self):
        """
        Orchestrates finding, analyzing, stitching, and reporting.
        """
        try:
            # 1. Get Destination Directory
            try:
                self.module_folder = self.get("directories")[self.class_name]
            except Exception as e:
                self.log.error(f"Directory not found in Redis: {e}")
                self.module_folder = "/tmp"

            # 2. Find Datasets
            # Uses config from the GUI object or the loaded config
            config = getattr(self.ui, "config", self.config_module)
            datasets = self.analyzer.find_best_datasets(config)

            payload = {"parameters": {}, "images": []}
            individual_images = []

            plot_opts = config.get("plot_options", {})

            # --- Enforce Order: High -> Standard -> Low ---
            target_order = ["high_resolution", "standard", "low_resolution"]
            # Find which keys exist and order them
            present_keys = [k for k in target_order if k in datasets]
            extras = [k for k in datasets.keys() if k not in target_order]
            ordered_keys = present_keys + sorted(extras)

            # Say so when the search found nothing. A report listing only what it
            # found cannot distinguish "no beamstop collections in the window"
            # from "everything was fine", and the second is what an empty table
            # looks like.
            if not ordered_keys:
                hours = config.get("search_hours", "the search window")
                payload["no_data_message"] = (
                    f"No beamstop collections were found in the last {hours} hours, "
                    f"so no positions could be compared with yesterday."
                )
                self.log.warning(
                    f"No beamstop collections found in the last {hours} hours. "
                    f"Nothing to assess."
                )
                # Proceed or cancel, because a beamstop check that compared
                # nothing has not been done, whatever the report says. The most
                # likely cause is the file names not matching what the search
                # looks for, which the operator can go and fix.
                choice = self.ui.show_urgent_warning(
                    self.BeamstopAlignment_WZ,
                    title="No Beamstop Collections Found",
                    text=f"Nothing was found in the last {hours} hours.",
                    informative_text=(
                        "No beamstop positions could be compared with yesterday, "
                        "so this check has not really been made.\n\nWere the "
                        "default file names used for the beamstop collections? If "
                        "not, the search cannot find them.\n\nCancel to go and "
                        "look, or proceed to record that there was nothing to "
                        "compare."
                    ),
                    buttons=[
                        (
                            "Proceed Anyway",
                            QtWidgets.QMessageBox.YesRole,
                            "proceedButton",
                        ),
                        ("Cancel", QtWidgets.QMessageBox.RejectRole, "cancelButton"),
                    ],
                )
                if choice != "Proceed Anyway":
                    self.log.info(
                        "Operator cancelled BeamstopAlignment: nothing was found "
                        "to compare."
                    )
                    self.set_status_false()
                    self.BeamstopAlignment_WZ.close()
                    return

            # 3. Analyze
            for label in ordered_keys:
                dataset_entry = datasets[label]
                stats, image_path = self.analyzer.analyze_dataset(
                    label, dataset_entry, self.module_folder, plot_opts
                )
                # Same reason: `<label>_beamstop.png` is savefig'd in place.
                if image_path:
                    self.displace_existing(image_path)

                payload["parameters"].update(stats)
                if image_path:
                    individual_images.append(image_path)

            # 4. Stitch Images & Display
            if individual_images:
                # BeamstopAnalysis writes its figures straight to the report
                # folder rather than copying them in, so anything from an earlier
                # run today has to be moved aside here (B6).
                self.displace_existing(
                    os.path.join(self.module_folder, "beamstop_summary_montage.png")
                )
                summary_path = os.path.join(
                    self.module_folder, "beamstop_summary_montage.png"
                )
                # Vertical stitching handled by updated BeamstopAnalysis
                final_image = self.analyzer.stitch_images(
                    individual_images, summary_path
                )
                if final_image:
                    payload["images"] = [final_image]

                    # Open Image Viewer for User to Inspect
                    try:
                        self.log.info(f"Opening image viewer for: {final_image}")
                        img = Image.open(final_image)
                        img.show()
                    except Exception as e:
                        self.log.error(f"Could not open image viewer: {e}")

            # 5. Assess Statistics
            assessed_params = self._assess_parameters(payload["parameters"])
            payload["parameters"] = assessed_params
            payload["table_title"] = config.get("report_table_title")

            # 6. Consistency Check
            has_high = "high_resolution" in datasets
            has_std = "standard" in datasets

            if not (has_high and has_std):
                self.log.info(
                    "Missing experimental data for HighRes or Standard. Running parameter consistency check."
                )
                is_consistent, msg = self.analyzer.check_consistency(config)

                if not is_consistent:
                    self.log.warning(f"Consistency Check Failed: {msg}")
                    QtWidgets.QMessageBox.warning(
                        self.BeamstopAlignment_WZ,
                        "Beamstop Configuration Mismatch",
                        f"WARNING: One position was not tested experimentally, and the configuration file has a mismatch!\n\n{msg}",
                    )
                    payload["parameters"]["Config_Consistency"] = {
                        "value": "MISMATCH",
                        "status": "danger",
                    }
                else:
                    self.log.info("Configuration is consistent.")
                    payload["parameters"]["Config_Consistency"] = {
                        "value": "OK",
                        "status": "good",
                    }
            else:
                self.log.info(
                    "Both HighRes and Standard measured experimentally. Skipping file check."
                )
                payload["parameters"]["Config_Consistency"] = {
                    "value": "Verified Exp.",
                    "status": "good",
                }

            # 7. Store Report
            redis_key = self.store_report(payload)

            self.log.info(f"Analysis complete. Results stored in {redis_key}")

        except Exception as e:
            self.log.critical(f"Analysis process failed: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self.BeamstopAlignment_WZ, "Error", f"Analysis Failed: {e}"
            )

    def _assess_parameters(self, raw_params):
        """Assess beamstop positions against yesterday's, using the shared engine.

        This module used to reimplement the deadband comparison inline and gate
        the whole thing on isinstance(value, (int, float)), so a position that
        arrived as a string - which is what a round trip through the report gives
        - was silently left unassessed. The shared helpers coerce with float()
        instead.
        """
        self.log.info("Assessing Beamstop statistics...")
        previous_report = self._get_previous_report_data() or {}
        previous_params = previous_report.get("parameters", {})
        if not previous_params:
            self.log.info("No previous beamstop report; positions cannot be compared.")
        return self.assess_parameters(
            raw_params,
            self.ui.config.get("assessment_rules", {}),
            previous_params,
            where="BeamstopAlignment",
            hidden=self.ui.config.get("hidden_parameters", []),
        )
