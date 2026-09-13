from base import MOD_Base
from PyQt5.QtWidgets import QFileDialog, QDialog, QMessageBox
from PyQt5 import QtCore
import datetime
from beamline import ID
import os, shutil
from PyQt5.QtCore import QDateTime


class CreateDirectories(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")

        self.now = datetime.datetime.now()
        self.ROOT_DIR = f"/dls/{ID}/data/{self.now.year}/"

        self.overwrite_config_criteria2expire()

    def overwrite_config_criteria2expire(self):
        # A bit of a hack as this particular module won't follow the criteria2expire setup on the main config file.
        key = f"{self.class_name}_{self.config['modules'][self.class_name]['widget2update']}_lastrun"
        if not self.check_day():
            self.log.warning(
                "Current day is different from last setup. Resetting directories to empty and reseting last update for CreateDirectories to the past"
            )
            self.reset_dirs()
            # Reset to a past date
            self.set(key, QDateTime.fromSecsSinceEpoch(1553504400))
        else:
            self.log.debug(
                "Directories still valid. Resetting date of last update for CreateDirectories to now"
            )
            self.set(key, QDateTime.currentDateTime())

    def check_day(self):
        check = self.now.strftime("%Y%m%d")
        dirs = self.get("directories")
        if type(dirs) != type({}) or dirs == {}:
            self.log.warning("List of directories does not exist in redis")
            return False
        for item in dirs:
            # Check if the folder date matches today
            if dirs[item].split("/")[-2] != check:
                return False
            else:
                self.log.debug(f"{item} folder is still valid")
        return True

    def reset_dirs(self):
        self.set(f"directories", {})

    def get_current_run_number(self):
        """Calculates the expected visit suffix based on the current month."""
        month = self.now.month
        if 1 <= month <= 3:
            return "-1"  # Jan - Mar
        elif 4 <= month <= 5:
            return "-2"  # Apr - May
        elif 6 <= month <= 8:
            return "-3"  # Jun - Aug
        elif 9 <= month <= 10:
            return "-4"  # Sep - Oct
        else:
            return "-5"  # Nov - Dec

    def show_instruction_message(self):
        """Displays a popup guiding the user to the correct folder."""
        suffix = self.get_current_run_number()
        year = self.now.year

        msg = (
            f"Please select the top-level commissioning folder for the current run.\n\n"
            f"Based on the date ({self.now.strftime('%B %Y')}), "
            f"we expect a commissioning visit ending in '{suffix}'.\n\n"
            f"Target Folder Structure:\n"
            f"/dls/{ID}/data/{year}/cm<proposal>{suffix}\n\n"
            f"Click OK to open the file browser."
        )

        # We use 'None' as parent so it creates a standalone window,
        # avoiding issues if 'self' is not a QWidget.
        QMessageBox.information(None, "Select Commissioning Folder", msg)

    def launch_GUI(self):
        # 1. Show Instructions FIRST
        self.show_instruction_message()

        # 2. Open File Dialog
        folder = self.FileDialog(
            directory=self.ROOT_DIR, forOpen=True, fmt="", isFolder=True
        )

        if not folder:
            self.log.warning("No folder selected.")
            return

        self.log.info(f"Got folder {folder}")

        # 3. Create Folders safely
        folders = self.make_folders(folder)
        self.log.debug(
            f'Created folders for all modules {folders}. Also stored on redis hashmap as "directories"'
        )
        self.set_status_true()

    def make_folders(self, base):
        dict_of_folders = {}
        for f in self.config["modules"]:
            if self.config["modules"][f]["needs_folder_to_write"]:
                self.log.info(f"{f}: checking/creating folder for this module")
                new_folder = f'{base}/beamline_setup/{self.now.strftime("%Y%m%d")}/{f}'

                # --- ROBUST DIRECTORY CREATION ---
                try:
                    os.makedirs(new_folder, exist_ok=True)
                except OSError as e:
                    self.log.error(f"Could not create directory {new_folder}: {e}")

                # --- ROBUST PERMISSIONS CHANGE ---
                try:
                    shutil.chown(new_folder, group="mx_staff")
                except OSError as e:
                    # Log warning but continue if we don't own the folder
                    self.log.warning(f"Could not chown {new_folder}: {e}")

                dict_of_folders[f] = new_folder

                # Try to chown parent folder too
                try:
                    parent_folder = (
                        f'{base}/beamline_setup/{self.now.strftime("%Y%m%d")}'
                    )
                    shutil.chown(parent_folder, group="mx_staff")
                except OSError as e:
                    self.log.warning(
                        f"Could not chown parent folder {parent_folder}: {e}"
                    )

        self.set(f"directories", dict_of_folders)
        return dict_of_folders

    def FileDialog(self, directory="", forOpen=True, fmt="", isFolder=False):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.DontUseCustomDirectoryIcons
        dialog = QFileDialog()
        dialog.setOptions(options)

        dialog.setFilter(dialog.filter() | QtCore.QDir.Hidden)

        if isFolder:
            dialog.setFileMode(QFileDialog.DirectoryOnly)
        else:
            dialog.setFileMode(QFileDialog.AnyFile)

        if forOpen:
            dialog.setAcceptMode(QFileDialog.AcceptOpen)
        else:
            dialog.setAcceptMode(QFileDialog.AcceptSave)

        if fmt != "" and isFolder is False:
            dialog.setDefaultSuffix(fmt)
            dialog.setNameFilters([f"{fmt} (*.{fmt})"])

        if directory != "":
            dialog.setDirectory(str(directory))
        else:
            dialog.setDirectory(str(self.ROOT_DIR))

        if dialog.exec_() == QDialog.Accepted:
            self.log.debug(f"got {dialog.selectedFiles()[0]} from selector")
            path = dialog.selectedFiles()[0]
            return path
        else:
            return ""
