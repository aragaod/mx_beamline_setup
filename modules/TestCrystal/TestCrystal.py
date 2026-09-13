from base import MOD_Base

from PyQt5.QtWidgets import QFileDialog, QDialog, QWizard
from PyQt5 import QtCore, QtWidgets

from .QualityControl import TestCrystalResults
from .ImageManipulation import TestCrystalPictures
from modules.TestCrystal.GUI_TestCrystal import GUI

from datetime import datetime
import pathlib
import time

import pandas as pd
import pprint


class TestCrystal(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()

    def launch_GUI(self):
        self.TestCrystal_WZ = QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.TestCrystal_WZ)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.TestCrystal_WZ.button(QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.TestCrystal_WZ.button(QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.TestCrystal_WZ.button(QWizard.NextButton).clicked.connect(self.next)
        self.TestCrystal_WZ.button(QWizard.BackButton).clicked.connect(self.back)

        # Handle pressing the top right X button
        self.TestCrystal_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.TestCrystal_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.TestCrystal_WZ.show()

    def next(self):
        self.log.debug(
            f"Next button pressed. Going to drive the goniometer on a different thread"
        )
        self.drive()

    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def drive(self):
        """Select masterfile to then harvest test crystal statistics"""
        payload = {}
        try:
            self.module_folder = self.get("directories")["TestCrystal"]
        except Exception as e:
            self.log.error(
                f"Please create the directories first. Can't run test crystal without a folder to store the QC"
            )
            return False

        try:
            self.montage_file = str(
                pathlib.PurePath(self.module_folder, "crystalNdiff_images.png")
            )  # need to define this earlier because it is used by get_visit_folder to guess open file folder to start

            self.ROOT_DIR = self.get_visit_folder()
            self.log.debug(f"Folder to find master files will start at {self.ROOT_DIR}")

            # folder = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
            self.log.debug(f"Using {self.ROOT_DIR} as starting point for GUI opening")
            self.masterfile = self.FileDialog(
                directory=self.ROOT_DIR, forOpen=True, fmt="_master.h5", isFolder=False
            )
            self.log.info(f"Got masterfile {self.masterfile}")

            self.log.debug(f"Going to extract processing results")
            extraction_status, parameters = self.extract_processing_data(
                self.masterfile
            )

            parameters.update(self.collect_dose(self.masterfile))

            assessed_parameters = self._assess_parameters(parameters)
            self.warn_if_crystal_is_spent(parameters)

            payload = {
                "parameters": assessed_parameters,
                "table_title": self.ui.config.get("report_table_title"),
            }

            self.log.debug(f"Going to make picture montage")
            montage_status = self.make_image_montage(self.masterfile)

            if montage_status:
                self.log.debug(f"Got a montage file, storing path into payload")
                payload["images"] = [self.montage_file]

            self.log.info("RESULTS")
            self.log.info("--------------------")
            if "parameters" in payload:
                self.log_dict_as_table(payload["parameters"])
            self.log.info("--------------------")

            key = self.store_report(payload)

            if extraction_status and montage_status:
                self.log.info(
                    f"Both processing results extaction and picture montage were sucessfull. Happy days!"
                )
                self.set_status_true()
        except Exception as e:
            self.log.critical(f"Failed with error {e}")
            self.set_status_false()

    def get_visit_folder(self):
        list_path = self.montage_file.split("/")
        list_path.remove("beamline_setup")
        list_path.remove("TestCrystal")
        list_path = list_path[0:-1]
        probable_master_file_path = "/".join(list_path)
        path_dir = pathlib.Path(probable_master_file_path)
        if path_dir.is_dir():
            return probable_master_file_path
        else:
            self.log.debug(
                f"The folder for today does not exist on this visit. Going to provide the parent folder"
            )
            return str(path_dir.parent)

    def extract_processing_data(
        self,
        masterfile="/dls/i04/data/2024/cm37236-1/20240313/TestProteinaseK/ProtK_13/ProtK_13_3_master.h5",
    ):
        """
        Given a masterfile extract processing statistics from the corresponding autoprocessing runNumber
        """

        self.log.debug("before masterfile")
        # masterfile below for testing purposes - to  be replaced by popup and staff selecting directory
        qc = TestCrystalResults(
            masterfile, registry=self.ui.config.get("test_samples", {})
        )
        self.log.debug("After test instantiation")
        payload = qc.get_results()

        # Here some code just assess if this task ran successfully and set status to True/False
        status = True
        if status == False:
            self.set(f"{self.class_name}_status", status)
        return [status, payload]

    def warn_if_crystal_is_spent(self, parameters):
        """Say out loud when the test crystal is past its useful life (B2b).

        A red row in a table that is read after the fact is not enough. The
        person is standing at the beamline now and could swap the crystal in the
        next few minutes; an hour later they cannot. So this interrupts.

        It does not block anything. The data is parsed, stored and reported
        exactly as usual, and the danger status goes to ISPyB either way - the
        popup is a prompt to fetch a fresh crystal, not a refusal to record this
        one.
        """
        try:
            from base.dose import GARMAN_LIMIT_MGY

            lifetime = parameters.get("Dose_crystal_lifetime_MGy")
            if lifetime is None or float(lifetime) < GARMAN_LIMIT_MGY:
                return

            over = float(lifetime) - GARMAN_LIMIT_MGY
            self.log.warning(
                f"Test crystal has absorbed {lifetime} MGy, past the "
                f"{GARMAN_LIMIT_MGY:.0f} MGy limit - staff advised to replace it"
            )
            self.ui.show_urgent_warning(
                self.TestCrystal_WZ,
                title="Test Crystal Is Past Its Dose Limit",
                text=f"This crystal has absorbed {lifetime} MGy.",
                # Short on purpose. A popup interrupts someone mid-task, so it
                # says what to do rather than explaining radiation damage. The
                # reasoning lives in the report's note under the table, where
                # there is room for it and time to read it.
                informative_text=(
                    f"That is <b>{over:.1f} MGy past the "
                    f"{GARMAN_LIMIT_MGY:.0f} MGy limit</b> (the Garman limit)."
                    f"<br><br>Its statistics now describe the crystal rather "
                    f"than the beamline."
                    f"<br><br><b>Please mount a fresh test crystal.</b>"
                    f"<br><br>Today's data is still recorded as normal."
                ),
                buttons=[
                    ("Understood", QtWidgets.QMessageBox.AcceptRole, "acceptButton")
                ],
            )
        except Exception as error:
            # A missing popup must never cost the report.
            self.log.warning(f"Could not show the dose warning: {error}")

    def collect_dose(self, masterfile):
        """Absorbed dose for this collection, and for the crystal's life (B2b).

        Why this is here at all: the module reports ISa and Rmeas as a measure of
        the beamline, and a test crystal's ISa falls steadily as it ages whatever
        the beamline is doing. Over one crystal's life in 2026 that decline was
        about 70% explained by accumulated dose, so without this column the
        assessment reads as a degrading beamline when it is a tiring crystal.

        Everything needed was already recorded when the detector was armed, and
        RADDOSE-3D is already a service - see base/dose.py. Nothing new is
        measured here; two existing sources are joined.

        Returns a dictionary of parameters to merge into the report. **Never
        raises**: a dose column is worth having and is not worth losing a
        morning's report over, so every failure returns an explanation instead of
        a number.
        """
        parameters = {}
        try:
            from base.dose import DoseCalculator, DoseUnavailable
            from base.eiger_log import EigerLog, crystal_name, history_for_crystal
            from beamline import redis as redis_client

            config = self.ui.config
            eiger = EigerLog(redis_client, self.ID, log=self.log)
            calculator = DoseCalculator(
                api_url=config.get("dose_api_url"),
                timeout=config.get("dose_timeout_s", 20),
                log=self.log,
            )

            # This collection, plus the X-ray centring shots fired at the same
            # crystal beforehand. Those are only about 0.4% of the total, but the
            # crystal absorbed them and the ratio does not hold everywhere.
            # The same window for both reads. The default depth is about a
            # day's worth of arming records, so a master file older than
            # that is reported as having no arming record at all - a 30 July
            # file did exactly that on 2026-08-31 while the record was
            # plainly there.
            lookback = config.get("dose_lookback_days", 60)
            since = time.time() - lookback * 86400
            this_collection = eiger.around(masterfile, depth=200000, since=since)
            if not this_collection:
                self.log.warning(
                    f"No armed collection in the eiger log for {masterfile} "
                    f"within the last {lookback} days, so no dose can be "
                    f"reported for it"
                )
                # Say the window. Without it, "no arming record" reads as "the
                # detector never collected this", when the usual cause is that
                # the collection is older than we looked.
                return {
                    "Dose_note": (
                        f"no arming record found for this collection in the "
                        f"last {lookback} days"
                    )
                }

            rows, total, skipped = calculator.dose_for_collections(this_collection)
            if not rows:
                return {"Dose_note": skipped[0][1] if skipped else "no usable record"}
            parameters["Dose_this_collection_MGy"] = round(total, 2)

            # The crystal's whole life within the visit. Sample names are only
            # unique inside a visit, so the search is scoped to it, and it stops
            # at this collection so the figure is what the crystal had absorbed
            # by the time these data were taken.
            anchor = this_collection[0]
            name = crystal_name(anchor)
            history = history_for_crystal(
                eiger.collections(depth=200000, since=since),
                name,
                visit=anchor.get("full_visit"),
                until=anchor.get("unix_time"),
            )
            life_rows, lifetime, life_skipped = calculator.dose_for_collections(history)
            parameters["Dose_crystal_lifetime_MGy"] = round(lifetime, 1)
            parameters["Dose_collections_counted"] = len(life_rows)

            if life_skipped:
                self.log.warning(
                    f"{len(life_skipped)} of this crystal's collections had no "
                    "usable flux or exposure, so the lifetime dose is a lower bound"
                )
            self.log.info(
                f"Dose: {total:.2f} MGy this collection, {lifetime:.1f} MGy over "
                f"{len(life_rows)} collections on {name or 'this crystal'} "
                f"({calculator.calls} API calls)"
            )
        except Exception as error:
            # The service being down, or the log not reaching back far enough, is
            # ordinary and not the operator's problem. Say so and carry on.
            self.log.warning(f"Dose not calculated: {error}")
            return {"Dose_note": f"dose could not be calculated: {error}"}
        return parameters

    def make_image_montage(self, masterfile):
        self.log.debug(f"Will write montage file to {self.montage_file}")
        # Built directly at the final path rather than copied into it, so the
        # previous run's montage has to be moved aside first (B6).
        self.displace_existing(self.montage_file)
        im = TestCrystalPictures(self.log)
        files2process = im.get_images(masterfile)
        im.create_l_montage(
            files2process["xtal_pictures"],
            files2process["diff_image"],
            self.montage_file,
        )
        if pathlib.Path(self.montage_file).is_file():
            status = True
        else:
            status = False
        return status

    def FileDialog(self, directory="", forOpen=True, fmt="", isFolder=False):
        # Taken from https://stackoverflow.com/questions/38746002/pyqt-qfiledialog-directly-browse-to-a-folder?rq=1
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.DontUseCustomDirectoryIcons
        dialog = QFileDialog()
        dialog.setOptions(options)

        dialog.setFilter(dialog.filter() | QtCore.QDir.Hidden)

        # ARE WE TALKING ABOUT FILES OR FOLDERS
        if isFolder:
            dialog.setFileMode(QFileDialog.DirectoryOnly)
        else:
            dialog.setFileMode(QFileDialog.AnyFile)
        # OPENING OR SAVING
        (
            dialog.setAcceptMode(QFileDialog.AcceptOpen)
            if forOpen
            else dialog.setAcceptMode(QFileDialog.AcceptSave)
        )

        # SET FORMAT, IF SPECIFIED
        if fmt != "" and isFolder is False:
            dialog.setDefaultSuffix(".h5")
            dialog.setNameFilters([f"{fmt} (*{fmt})"])

        # SET THE STARTING DIRECTORY
        if directory != "":
            dialog.setDirectory(str(directory))
        else:
            dialog.setDirectory(str(self.ROOT_DIR))

        if dialog.exec_() == QDialog.Accepted:
            self.log.debug(f"got {dialog.selectedFiles()[0]} from selector")
            path = dialog.selectedFiles()[0]  # returns a list
            return path
        else:
            return ""

    def log_dict_as_table(self, params_dict):
        """Formats the assessed parameters dictionary into a readable ASCII table."""
        if not params_dict:
            self.log.info("No parameters to display.")
            return

        # 1. Convert the nested dictionary into a list of lists with headers
        list_of_lists = [["Parameter", "Value", "Status"]]
        for param_name, data in params_dict.items():
            # Grab value and status, providing defaults if they happen to be missing
            val = str(data.get("value", "N/A"))
            status = str(data.get("status", "-"))
            list_of_lists.append([str(param_name), val, status])

        # 2. Find the maximum width needed for each column
        col_widths = [
            max(len(str(item)) for item in col) for col in zip(*list_of_lists)
        ]

        # 3. Create the format string and separator
        format_str = " | ".join([f"{{:<{w}}}" for w in col_widths])
        separator_width = sum(col_widths) + 3 * (len(col_widths) - 1)
        separator = "-" * separator_width

        # 4. Print it to the log
        self.log.info(separator)
        for i, row in enumerate(list_of_lists):
            self.log.info(format_str.format(*row))
            # Print an extra separator right after the header row
            if i == 0:
                self.log.info(separator)
        self.log.info(separator)

    def _assess_parameters(self, raw_params):
        """Assess the diffraction statistics against TestCrystal.yaml.

        These are absolute quality thresholds rather than comparisons with
        yesterday, so no previous report is needed.
        """
        self.log.info("Assessing Test Crystal statistics for status...")
        assessed = self.assess_parameters(
            raw_params,
            self.ui.config.get("assessment_rules", {}),
            previous_params=None,
            where="TestCrystal",
            hidden=self.ui.config.get("hidden_parameters", []),
        )
        self._hide_locations_that_point_at_nothing(assessed)
        self._fold_identity_verdicts(assessed)
        return assessed

    @staticmethod
    def _fold_identity_verdicts(assessed):
        """Put the tick on the row a reader actually looks at.

        The identity checks produce a value and a verdict as separate parameters:
        Test_sample says "Thaumatin" and Test_sample_identified says "yes";
        Space_group says 89, Space_group_expected says 89 and Space_group_match
        says "yes". Reported literally that is six rows, of which the three
        carrying the information have no status and the three carrying a status
        say nothing a reader wants to know.

        So the status moves onto the informative row and the verdict row is
        hidden. The verdicts stay in redis, because they are what a trend over
        the archive would count.
        """
        pairs = [
            # informative row, verdict row, what the criterion should read
            ("Test_sample", "Test_sample_identified", "in the registry"),
            ("Space_group", "Space_group_match", None),
            ("Unit_cell", "Unit_cell_deviation_pct", "within 2% of usual"),
        ]
        for shown, verdict, criterion in pairs:
            value_row = assessed.get(shown)
            verdict_row = assessed.get(verdict)
            if not (isinstance(value_row, dict) and isinstance(verdict_row, dict)):
                continue
            if verdict_row.get("status"):
                value_row["status"] = verdict_row["status"]
            if criterion:
                value_row["criterion"] = criterion
            elif verdict_row.get("criterion"):
                value_row["criterion"] = verdict_row["criterion"]
            if verdict != "Unit_cell_deviation_pct":
                # The deviation is a number worth reading in its own right; the
                # yes/no verdicts are not.
                verdict_row["hidden"] = True

        # The expected space group belongs in the criterion, not in a row of
        # its own that says nothing without the observed one beside it.
        expected = assessed.get("Space_group_expected")
        observed = assessed.get("Space_group")
        if isinstance(expected, dict) and isinstance(observed, dict):
            observed["criterion"] = f"= {expected.get('value')}"
            expected["hidden"] = True

    @staticmethod
    def _hide_locations_that_point_at_nothing(assessed):
        """Show where something happened only when something happened.

        Scale_step_at names the images around the largest jump in per-image
        scale. That is worth reading when the jump is big enough to be worth
        investigating, and is an invitation to go and look at nothing when it is
        not. So it is shown only when Scale_step_pct is not good.

        The value is still stored either way - it costs nothing in redis and the
        trend analysis wants it - it is only kept out of the report.
        """
        magnitude = assessed.get("Scale_step_pct")
        location = assessed.get("Scale_step_at")
        if not (isinstance(magnitude, dict) and isinstance(location, dict)):
            return
        if magnitude.get("status") == "good":
            location["hidden"] = True
