# Mod Base
from base import MOD_Base

# pyQT5
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.RotationAxis.GUI_RotationAxis import GUI

# APP
import requests
import getpass
from beamline import motors
from beamline import cameras
from beamline import ID
import shutil
import epics

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

# Others
import functools
from datetime import datetime, timedelta


class RotationAxis(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.ID = ID
        self.now = datetime.now().strftime("%Y%m%d")
        self.can_proceed = True

    def launch_GUI(self):
        self.RotationAxis_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(self.RotationAxis_WZ)

        # Connections
        self.RotationAxis_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.RotationAxis_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.RotationAxis_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.RotationAxis_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )
        self.RotationAxis_WZ.rejected.connect(self.reject)

        self.RotationAxis_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.RotationAxis_WZ.show()

        # --- TRIGGER SMARGON HOME CHECK ---
        # This was missing in your previous version.
        self.check_smargon_home_age()

    def check_smargon_home_age(self):
        """
        Checks if Smargon homing is older than the limit defined in YAML.
        Uses self.ui.show_urgent_warning (Composition) for the popup.
        """
        # Access config via self.ui.config because that's where GUI_RotationAxis loads it
        config = self.ui.config.get("smargon_home_age_check", {})

        if not config.get("enabled", False):
            self.can_proceed = True
            return

        try:
            # 1. Find PV Name Dynamically
            pv_name = None
            # Iterate through PV dictionary to find the 'Smargon_home' alias
            for prefix, pvs in self.ui.config.get("PVs", {}).items():
                if "Smargon_home" in pvs:
                    suffix = pvs["Smargon_home"]
                    pv_name = f"{prefix}:{suffix}"
                    break

            if not pv_name:
                self.log.warning(
                    "Could not find 'Smargon_home' PV definition in YAML. Skipping check."
                )
                return

            # 2. Get Timestamp directly from EPICS
            pv = epics.PV(pv_name)
            ts = pv.timestamp

            if ts:
                last_home_time = datetime.fromtimestamp(ts)
                time_diff = datetime.now() - last_home_time

                # 3. Get the limit, preferring the Smargon_home assessment rule
                # so the popup and the report row can never disagree. They did
                # until 2026-08-31: this block said 6 hours while the rule said
                # 8, so between 6 and 8 hours the popup warned and the report
                # said good.
                unit = config.get("max_age", {}).get("unit", "hours")
                rule = self.ui.config.get("assessment_rules", {}).get(
                    "Smargon_home", {}
                )
                rule_limits = rule.get("limits") or []
                if rule_limits:
                    max_val = rule_limits[0]
                    unit = rule.get("unit", "hours")
                else:
                    max_val = config.get("max_age", {}).get("value", 8)

                if unit == "days":
                    max_age = timedelta(days=max_val)
                elif unit == "minutes":
                    max_age = timedelta(minutes=max_val)
                else:
                    max_age = timedelta(hours=max_val)

                self.log.info(
                    f"Smargon last homed: {last_home_time}. Age: {time_diff}. Limit: {max_age}"
                )

                if time_diff > max_age:
                    self.log.warning("Smargon home status is stale!")

                    popup_buttons = [
                        (
                            "Proceed Anyway",
                            QtWidgets.QMessageBox.YesRole,
                            "proceedButton",
                        ),
                        ("Cancel", QtWidgets.QMessageBox.RejectRole, "cancelButton"),
                    ]

                    # 4. Show Warning using self.ui (Composition)
                    choice = self.ui.show_urgent_warning(
                        self.RotationAxis_WZ,
                        title="Smargon Home Status Warning",
                        text=f"The smargon has not been homed for longer than {max_val} {unit}.",
                        informative_text="This is a risk for the equipment because if lost counts, collisions with the robot might occur.\n\nDo you want to proceed anyway?",
                        buttons=popup_buttons,
                    )

                    if choice != "Proceed Anyway":
                        self.log.info(
                            "User cancelled RotationAxis due to old Smargon home."
                        )
                        self.set_status_false()
                        self.RotationAxis_WZ.close()
                        self.can_proceed = False
                        return
            else:
                self.log.warning(f"Could not get timestamp for {pv_name}")
        except Exception as e:
            self.log.error(f"Error checking Smargon home age: {e}")

        self.can_proceed = True

    def check_zoom_level(self):
        """
        Reads the camera zoom using the beamline library. If it's not 7.5,
        throws an urgent warning popup and returns False to block the next step.
        """
        try:
            current_zoom = cameras.zoom.get_current_factor()

            if current_zoom != 7.5:
                self.log.warning(f"Zoom level is {current_zoom}x. Expected 7.5x.")

                popup_buttons = [
                    ("Understood", QtWidgets.QMessageBox.AcceptRole, "acceptButton")
                ]

                self.ui.show_urgent_warning(
                    self.RotationAxis_WZ,
                    title="Manual Zoom Check Required",
                    text=f"The current zoom level is {current_zoom}x, but 7.5x is required.",
                    informative_text="A manual check of the rotation axis needs to be done at zoom 7.5x before gathering QC data.\n\nPlease go to the beamline UI, set the zoom to 7.5x, manually verify the rotation axis, and then click Next again.",
                    buttons=popup_buttons,
                )
                return False

            self.log.info("Zoom level is correctly set to 7.5x. Proceeding.")
            return True

        except Exception as e:
            self.log.error(f"Failed to check zoom level via beamline library: {e}")
            return True  # Fallback so we don't break the module

    def next(self):
        if not self.can_proceed:
            self.log.warning(
                "Cannot proceed due to earlier check failure or cancellation."
            )
            return

        if not self.check_zoom_level():
            self.log.warning("Blocking QC gathering: Zoom is not at 7.5x.")
            # QWizard normally automatically advances visually when "Next" is clicked.
            # If it moved to the next page visually, this pushes them right back to the first page.
            self.RotationAxis_WZ.back()
            return  # <--- This prevents self.drive() from running!

        self.log.debug(
            "Next button pressed. Going to drive the goniometer on a different thread"
        )
        self.drive()

    def back(self):
        self.log.debug("Back button pressed")

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def drive(self):
        try:
            self.log.debug(f"Triggered drive method on {self.class_name}")

            rotationaxis_qc = DriveBeamline(
                self.get, self.ui.config, self.class_name, self.log, parent_module=self
            )
            payload = rotationaxis_qc.collect_CoR_data()

            if "parameters" in payload:
                raw_values = {k: v["value"] for k, v in payload["parameters"].items()}
                payload["parameters"] = self._assess_parameters(raw_values)

            self.store_report(payload)

        except Exception as e:
            self.log.critical(f"Failed with error {e}")

    def _assess_parameters(self, raw_params):
        """Assess the goniometer and stub positions against RotationAxis.yaml."""
        self.log.info("Assessing Rotation Axis statistics...")
        previous_report = self._get_previous_report_data() or {}
        previous_params = previous_report.get("parameters", {})
        return self.assess_parameters(
            raw_params,
            self.ui.config.get("assessment_rules", {}),
            previous_params,
            where="RotationAxis",
            hidden=self.ui.config.get("hidden_parameters", []),
        )


class DriveBeamline(object):
    def __init__(
        self,
        get_redis_method,
        module_config,
        original_class_name,
        log,
        parent_module=None,
    ):
        self.url = f"http://{cameras.ROIs['xtal']['server']}{cameras.ROIs['xtal']['static'][0]}"
        self.username = username = getpass.getuser()
        # Needed for the shared helpers on MOD_Base, the same way AlignBeam's
        # OpticsChecks holds one.
        self.parent_module = parent_module
        self.get = get_redis_method
        self.config = module_config
        self.original_class = original_class_name
        self.log = log
        self.now = datetime.now().strftime("%Y%m%d")

        self.display_configuration_file = self.config["display_configuration"]
        # self.zoom_pv = epics.PV(self.config["zoom_pv"])

        self.log.debug(f"{self.config['PVs']}")
        self.PV_instances = self.set_PVs()

    def _structure_parameters(self, pv_data):
        self.log.info("Structuring rotation axis parameters...")
        structured_params = {key: {"value": value} for key, value in pv_data.items()}
        return structured_params

    def get_PVs(self):
        self.data = {}
        for PV_prefix, PV_dict in self.config["PVs"].items():
            for name, suffix in PV_dict.items():
                if name == "Smargon_home":
                    self.data[name] = (
                        self.PV_instances[PV_prefix]
                        .get_PV_change_time("HOMESTATUS_MSG")
                        .strftime("%Y-%m-%d %H:%M")
                    )
                    self.log.info(f"Time since last home {self.data[name]}")
                else:
                    self.data[name] = getattr(self.PV_instances[PV_prefix], name)()
        self.log.info(f"Gather PV data without errors")
        return self.data

    def set_PVs(self):
        PV_instances = {}
        for prefix, pvs in self.config["PVs"].items():
            PV_instances[prefix] = BeamlineEpics(
                prefix=prefix, _init_list_=pvs.values(), nonpvs=list(pvs.keys())
            )
            lambdas = {}
            string_pvs = set(self.config.get("string_pvs", []))
            for name, suffix in pvs.items():
                # Numbers raw, text as text - see the note in AlignBeam.setup_PVs.
                # Reading a position through as_string rounds it to the PV's
                # display precision, which matters here because the stub and
                # goniometer checks compare against yesterday at the 0.001 level.
                lambdas[suffix] = functools.partial(
                    PV_instances[prefix].get, suffix, as_string=name in string_pvs
                )
                setattr(PV_instances[prefix], name, lambdas[suffix])
        return PV_instances

    def collect_CoR_data(self):
        dict_data = {}
        raw_pv_data = self.get_PVs()
        dict_data["parameters"] = self._structure_parameters(raw_pv_data)
        dict_data["table_title"] = self.config.get("report_table_title")

        self.is_needle_mounted()
        initial_location = motors.omega.RBV
        cameras.zoom.set(7.5)
        epics.poll(2.0)
        locations_and_zooms = self.collect_four_images()
        self.drive_goniometer_to(initial_location)
        self.store_original_frames(locations_and_zooms)
        dict_data["parameters"].update(self.measure_eccentricity(locations_and_zooms))
        path = self.make_montage(locations_and_zooms)
        final_path = self.store_montage_for_report(path)
        dict_data["images"] = [final_path]
        return dict_data

    def measure_eccentricity(self, locations_with_zooms):
        """How far the pin tip sits from the rotation axis, in pixels (B4).

        The module has driven omega to four angles and photographed the pin at
        each for years, and produced no number from them - the images went into a
        montage for a person to look at. This is that number.

        Measured on the frames as captured, before the montage draws a crosshair
        through them. Never raises: this is a new figure of merit on a module
        that already works, and it is not worth losing a morning's report over.
        """
        try:
            from PIL import Image

            from .eccentricity import measure

            frames = {
                angle: Image.open(path)
                for (path, _), angle in zip(locations_with_zooms, [0, 90, 180, 270])
            }
            tips, figures, missing = measure(frames)
            for angle, why in missing:
                self.log.warning(f"No pin tip found at omega {angle}: {why}")
            if not figures:
                return {"Rotation_axis_note": "no pin tip could be found"}

            parameters = {}
            if "eccentricity_px" in figures:
                parameters["Rotation_axis_eccentricity_px"] = round(
                    figures["eccentricity_px"], 2
                )
            for label in ("0_180", "90_270"):
                key = f"eccentricity_{label}_px"
                if key in figures:
                    parameters[f"Rotation_axis_eccentricity_{label}_px"] = round(
                        figures[key], 2
                    )
            self.log.info(f"Rotation axis eccentricity: {parameters}")
            return parameters
        except Exception as error:
            self.log.warning(f"Could not measure the rotation axis: {error}")
            return {"Rotation_axis_note": f"could not be measured: {error}"}

    def store_original_frames(self, locations_with_zooms):
        """Keep the four frames as captured, before the montage draws on them.

        They are written to /var/tmp, which is per-workstation and overwritten by
        the next run, so until now nothing survived the morning except the
        montage - and the montage has the crosshair drawn through every frame.

        The montage turns out to be losslessly decomposable (see montage.py), so
        this is not the only route to the originals. It is still the right one:
        it avoids the decomposition, and it keeps the three pixels per line that
        the drawn crosshair overwrites.

        Only the images are stored here. Nothing is assessed and nothing is
        added to the report, so a failure costs a file, not a morning.
        """
        folder = self.get("directories")[self.original_class]
        for (path, _), angle in zip(locations_with_zooms, [0, 90, 180, 270]):
            try:
                self.parent_module.store_versioned(
                    path, f"{folder}/rotationaxis_omega_{angle:03d}.jpg"
                )
            except Exception as error:
                self.log.warning(f"Could not keep the omega {angle} frame: {error}")

    def get_zoom_dict(self):
        self.zoom_dict = {}
        with open(self.display_configuration_file) as display_configuration:
            for line in display_configuration:
                parsed_line = line.split("=")
                if parsed_line[0].strip() == "zoomLevel":
                    current_zoom = parsed_line[1].strip()
                    self.zoom_dict[current_zoom] = {}
                self.zoom_dict[current_zoom][parsed_line[0].strip()] = parsed_line[
                    1
                ].strip()
        return self.zoom_dict

    def is_needle_mounted(self):
        pass

    def collect_single_picture(self, angle):
        self.drive_goniometer_to(angle)
        path, zoom = self.get_image_from_url(url=self.url, filename=angle)
        return [path, zoom]

    def drive_goniometer_to(self, angle):
        self.log.debug(f"Moving omega to {angle}")
        motors.omega.move(angle, wait=True, ignore_limits=True)

    def get_image_from_url(self, url, location="/var/tmp/", filename="image"):
        final_location = f"{location}{self.username}_{filename}.jpg"
        response = requests.get(url, stream=True)
        zoom = str(cameras.zoom.get_current_factor())
        with open(final_location, "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        return final_location, zoom

    def collect_four_images(self):
        angles = [0, 90, 180, 270]
        return [self.collect_single_picture(angle) for angle in angles]

    def make_montage(self, locations_with_zooms):
        ninty = locations_with_zooms[1]
        locations_with_zooms.remove(ninty)
        locations_with_zooms.insert(2, ninty)
        locations = [path[0] for path in locations_with_zooms]
        pill_image = self.make_contact_sheet(
            locations_with_zooms,
            2,
            2,
            1024,
            768,
            1,
            1,
            1,
            1,
            1,
            draw_horizontal_line=True,
        )
        temp_save = f"/var/tmp/{self.username}_montage.png"
        pill_image.save(temp_save)
        pill_image.show()
        return temp_save

    def store_montage_for_report(self, montage_image):
        final_location = (
            f"{self.get('directories')[self.original_class]}/rotationaxis_montage.png"
        )
        return self.parent_module.store_versioned(montage_image, final_location)

    def make_contact_sheet(
        self,
        locations_zoom,
        ncols,
        nrows,
        photow,
        photoh,
        marl,
        mart,
        marr,
        marb,
        padding,
        draw_horizontal_line=False,
        draw_beam_cross=False,
    ):
        fnames = [path[0] for path in locations_zoom]
        fzooms = [zoom[1] for zoom in locations_zoom]

        if draw_horizontal_line or draw_beam_cross:
            zoom_dict = self.get_zoom_dict()

        marw = marl + marr
        marh = mart + marb
        padw = (ncols - 1) * padding
        padh = (nrows - 1) * padding
        isize = (ncols * photow + marw + padw, nrows * photoh + marh + padh)

        white = (255, 255, 255)
        inew = Image.new("RGB", isize, white)

        count = 0
        for irow in range(nrows):
            for icol in range(ncols):
                left = marl + icol * (photow + padding)
                right = left + photow
                upper = mart + irow * (photoh + padding)
                lower = upper + photoh
                bbox = (left, upper, right, lower)
                try:
                    name = fnames[count].split(".")[0].split("_")[1]
                    img = Image.open(fnames[count]).resize((photow, photoh))

                    if draw_horizontal_line == True:
                        Y_coordinate = int(zoom_dict[fzooms[count]]["crosshairY"])
                        X_coordinate = int(zoom_dict[fzooms[count]]["crosshairX"])
                        ImageDraw.Draw(img).line(
                            (0, Y_coordinate, photow, Y_coordinate), fill=128, width=3
                        )
                        ImageDraw.Draw(img).line(
                            (X_coordinate, 0, X_coordinate, photoh), fill=128, width=3
                        )

                    if draw_beam_cross == True:
                        Y_coordinate = int(zoom_dict[fzooms[count]]["crosshairY"])
                        X_coordinate = int(zoom_dict[fzooms[count]]["crosshairX"])
                        size_of_line = 15
                        ImageDraw.Draw(img).line(
                            (
                                X_coordinate - size_of_line,
                                Y_coordinate,
                                X_coordinate + size_of_line,
                                Y_coordinate,
                            ),
                            fill=128,
                            width=3,
                        )
                        ImageDraw.Draw(img).line(
                            (
                                X_coordinate,
                                Y_coordinate - size_of_line,
                                X_coordinate,
                                Y_coordinate + size_of_line,
                            ),
                            fill=128,
                            width=3,
                        )

                    font = ImageFont.truetype("arial.ttf", 48)
                    ImageDraw.Draw(img).text((0, 0), name, (255, 255, 255), font=font)
                except Exception as e:
                    self.log.critical(f"Failed to prepare montage with error {e}")
                inew.paste(img, bbox)
                count += 1
        return inew


class BeamlineEpics(epics.Device):
    def __init__(self, prefix=None, _init_list_=(), nonpvs=[]):
        nonpvs = nonpvs + ["get_PV_change_time"] + list(epics.Device._nonpvs)
        epics.Device.__init__(
            self, prefix=prefix, delim=":", attrs=list(_init_list_), nonpvs=nonpvs
        )

    def get_PV_change_time(self, suffix):
        return datetime.fromtimestamp(self.PV(suffix).timestamp)


if __name__ == "__main__":
    pass
