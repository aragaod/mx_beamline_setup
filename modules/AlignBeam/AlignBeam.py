# Mod Base
from base import MOD_Base

# pyQT5
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.AlignBeam.GUI_AlignBeam import GUI

# APP
import requests
import getpass
from beamline import cameras
from beamline import ID
import shutil
import epics

# PIL
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

# Others
import functools
from datetime import datetime
import pprint


class AlignBeam(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now().strftime("%Y%m%d")

    def what_to_do_about(self, error):
        """Turn the failed condition into the next action, as list items.

        The popup used to end with "put the beamline in the right state", which
        tells an experienced person nothing and a new starter less than that.
        Each condition has one obvious next step, so say it. The camera case is
        first because it is the one that is not about the beam at all.
        """
        reason = str(error).lower()
        steps = []
        if "camera" in reason or "oav" in reason:
            steps.append(
                "The on-axis camera did not answer. Check whether its EPICS IOC "
                "is running - this is not a beam problem and nothing else here "
                "will help until the camera is back."
            )
        if "endstation shutter" in reason:
            steps.append(
                "Open the <b>endstation shutter</b>. Without it there is no flux, "
                "so this is the first thing to fix."
            )
        if "fast shutter" in reason:
            steps.append("Open the <b>fast shutter</b>.")
        if "scintillator" in reason:
            steps.append(
                "Put the <b>scintillator in the beam</b> - there is nothing for "
                "the camera to see without it."
            )
        if "flux" in reason and "endstation shutter" not in reason:
            steps.append(
                "There is no flux. Check the shutters and that the machine is "
                "delivering beam."
            )
        if not steps:
            steps.append("Check the beamline state, then try again.")
        return "".join(f"<li>{step}</li>" for step in steps)

    def launch_GUI(self):
        self.AlignBeam_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        # TODO: implement display configuration and zoom in beamline library
        self.ui.config["display_configuration"] = self.ui.config[
            "display_configuration"
        ].format(BEAMLINE=self.ID)

        width = self.ui.config.get("width", 600)
        height = self.ui.config.get("height", 550)
        self.ui.setupUi(self.AlignBeam_WZ, width=width, height=height)
        self.AlignBeam_WZ.resize(width, height)

        # Connecting the Finish and Cancel buttons so that they trigger update of status. (set_status_true() set_status_false() are defined in Modules.py/MOD_Base
        self.AlignBeam_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.AlignBeam_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.AlignBeam_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.AlignBeam_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )

        # Handle pressing the top right X button
        self.AlignBeam_WZ.rejected.connect(self.reject)

        # Lock main window to prevent other tasks
        self.AlignBeam_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.AlignBeam_WZ.show()

        # import code
        # code.interact(local=locals())

    def next(self):
        self.log.debug("Next button pressed. Going to collect optical alignment data")
        self.collect_qc_data()

    def back(self):
        self.log.debug(
            "Back button pressed, maybe you want to collect rotation axis data again?"
        )

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def collect_qc_data(self):
        """
        Orchestrates the collection of optics data in two steps:
        1. Gathers and assesses PV data (safe).
        2. Collects images, which involves moving motors (interactive).
        """
        try:
            self.log.debug(
                f"Triggered collect_qc_data method on {self.class_name} module class"
            )
            alignbeam_qc = OpticsChecks(
                self, self.get, self.ui.config, self.class_name, self.log
            )

            # Step 1: Gather all PV data and perform assessments. This is safe.
            payload = alignbeam_qc.collect_pv_data()

            # Step 2: the interactive part, which moves the zoom and takes images.
            #
            # Kept separate so that losing it does not lose step 1. The camera
            # server can be down - it was on 2026-08-31, refusing connections on
            # OAV.mjpg.jpg - and before this the exception escaped run(), no
            # report was written, and every PV reading and the crosshair
            # positions were discarded despite having been collected without
            # trouble. A morning with a dead camera should still record the beam
            # numbers.
            try:
                payload = alignbeam_qc.collect_image_data(payload)
            except BeamNotReady as error:
                # The beamline can be reached; there is just nothing worth
                # photographing. Nothing moved, because this is checked first.
                self.log.error(f"Not collecting images: {error}")
                payload["images"] = payload.get("images", [])
                payload["no_images_message"] = (
                    f"No images were collected because the beamline was not "
                    f"ready: {error}. The beam parameters below were read "
                    f"normally, and nothing was moved."
                )
                self.ui.show_urgent_warning(
                    self.AlignBeam_WZ,
                    title="Beamline Not Ready For Images",
                    text="No pictures of the beam were taken.",
                    informative_text=(
                        f"<b>Why:</b> {error}."
                        f"<br><br><b>What to do:</b>"
                        f"<ul>{self.what_to_do_about(error)}</ul>"
                        f"Then run this module again."
                        f"<br><br>Nothing was moved and the beam parameters "
                        f"were read normally, so the report is not lost."
                    ),
                    buttons=[
                        ("Understood", QtWidgets.QMessageBox.AcceptRole, "acceptButton")
                    ],
                )
                self.store_report(payload)
                self.set_status_false()
                return

            except Exception as error:
                camera_url = getattr(alignbeam_qc, "url", "the camera URL")
                self.log.error(
                    f"Could not collect the zoom images from {camera_url}, so the "
                    f"report has the beam parameters but no montage: {error}"
                )
                payload["images"] = payload.get("images", [])
                payload["no_images_message"] = (
                    f"The zoom images could not be collected from {camera_url}, "
                    f"so there is no montage to inspect. The beam parameters "
                    f"below were read normally. Reason: {error}"
                )

                # Tell the operator now rather than leaving them to notice a
                # missing montage in the report later. The most likely cause by
                # far is the camera IOC being down, so the message says so.
                self.ui.show_urgent_warning(
                    self.AlignBeam_WZ,
                    title="Camera Images Not Collected",
                    text="The beam images could not be collected.",
                    informative_text=(
                        f"The camera did not respond at:\n\n{camera_url}\n\n"
                        f"The most likely cause is that the OAV camera IOC is "
                        f"down. The beam parameters were read normally and have "
                        f"been recorded, but there is no montage to inspect, so "
                        f"this check is not complete.\n\nReason: {error}"
                    ),
                    buttons=[
                        ("Understood", QtWidgets.QMessageBox.AcceptRole, "acceptButton")
                    ],
                )

                # The images are the point of this step, so without them the
                # module has not done its job, whatever the parameters say.
                self.store_report(payload)
                self.set_status_false()
                return

            self.store_report(payload)

        except Exception as e:
            self.log.critical(f"Failed with error {e}", exc_info=True)


class BeamNotReady(Exception):
    """The beamline is not in a state where photographing it means anything.

    Distinct from a camera failure: there the equipment could not be reached; here
    it can be, and there is nothing worth looking at.
    """


class OpticsChecks(object):
    def __init__(
        self, parent_module, get_redis_method, module_config, original_class_name, log
    ):
        self.parent_module = parent_module
        self.url = f"http://{cameras.ROIs['xtal']['server']}{cameras.ROIs['xtal']['static'][0]}"
        self.username = getpass.getuser()
        self.get = get_redis_method
        self.config = module_config
        self.original_class = original_class_name
        self.log = log
        self.now_obj = datetime.now()
        self.now = self.now_obj.strftime("%Y%m%d")

        self.display_configuration_file = self.config["display_configuration"]
        self.zoom_pv = epics.PV(self.config["zoom_pv"])

        self.log.debug(f"{self.config['PVs']}")
        self.PV_instances = self.setup_PVs()

    def collect_pv_data(self):
        """
        Gathers and assesses all PV data without moving any motors.
        This is safe to run during user operations.
        """
        self.log.info("Collecting and assessing PV data...")
        dict_data = {}
        raw_pv_data = self.get_PVs()

        # Record where the crosshair was. This belongs in the safe path: it reads
        # display.configuration, a file, and touches no PV and no motor.
        raw_pv_data.update(self.collect_crosshair_positions())

        # Assess the parameters using our YAML rules
        dict_data["parameters"] = self._assess_parameters(raw_pv_data)
        dict_data["table_title"] = self.config.get("report_table_title")

        if dict_data.get("parameters"):
            self.log.info(
                f"List of human readable PVs available {list(dict_data['parameters'].keys())}"
            )
        return dict_data

    def camera_is_available(self, timeout=5):
        """Can the camera be reached at all?

        Asked before anything moves. Without this the module drives the zoom to 0
        and back through all eight levels and only then discovers the camera is
        not answering - eight pointless moves of beamline hardware to produce
        nothing. That is what happened on 2026-08-31 with the OAV IOC down.
        """
        try:
            response = requests.get(self.url, stream=True, timeout=timeout)
            response.close()
            response.raise_for_status()
            return True
        except Exception as error:
            self.log.error(f"Camera at {self.url} did not respond: {error}")
            self.camera_error = error
            return False

    def collect_image_data(self, payload):
        """
        Moves the scintillator, changes zoom, and collects images.
        This method takes the existing payload and adds the image data to it.
        WARNING: This method moves beamline components.
        """
        self.log.info("Collecting image data...")

        # Is there anything worth photographing? Asked before the camera and
        # before anything moves.
        if not self.checks(payload.get("parameters")):
            raise BeamNotReady("; ".join(getattr(self, "not_ready_reasons", [])))

        # Check the camera before moving anything. A dead camera means the images
        # cannot be collected whatever the zoom does, so there is no reason to
        # drive it first.
        if not self.camera_is_available():
            raise ConnectionError(
                f"The camera at {self.url} did not respond, so no images were "
                f"collected and the zoom was left where it was. "
                f"{getattr(self, 'camera_error', '')}"
            )

        if self.checks():
            self.log.info(f"Passed checks")
            initial_zoom = self.zoom_pv.get()
            self.move_to_zoom(0)
            epics.poll(0.5)
            locations_and_zooms = self.collect_all_zoom_images()
            self.move_to_zoom(initial_zoom)

            params_table = payload.get("parameters", {})

            def get_value_helper(param_name):
                entry = params_table.get(param_name, {})
                return entry.get("value", "N/A")

            flux_display_value = self.parent_module.format_scientific(
                get_value_helper("FLUX")
            )

            payload_text = f"""
            {self.now}
            
            Flux: {flux_display_value} ph/s
            Transmission: {get_value_helper('TRANSMISSION')}
            Beamsize: {round(float(get_value_helper('BEAM_SIZE_X')), 1) if get_value_helper('BEAM_SIZE_X') not in ['N/A', None] else 'N/A'} um (H) x {round(float(get_value_helper('BEAM_SIZE_Y')), 1) if get_value_helper('BEAM_SIZE_Y') not in ['N/A', None] else 'N/A'} um (V)
            Feedback on: {get_value_helper('Feedback_enable')}
            Machine Steer X: {get_value_helper('Machine_X_STEER')}
            Machine Steer Y: {get_value_helper('Machine_Y_STEER')}
            """
            locations_and_zooms.append(self.create_image_with_text(text=payload_text))
            path = self.make_montage(locations_and_zooms)
            path = self.store_beam_image_for_report(path)
            payload["images"] = [path]

        return payload

    def collect_single_picture(self, new_zoom):
        self.log.info(f"Moving to {new_zoom} zoom level")
        self.move_to_zoom(new_zoom)
        epics.poll(0.5)
        path, zoom = self.get_image_from_url(url=self.url, filename=new_zoom)
        self.log.info(f"Got image for zoom {new_zoom} with path {path}")
        return [path, zoom]

    def move_to_zoom(self, zoom):
        self.zoom_pv.put(zoom)
        epics.poll(0.2)

    def collect_crosshair_positions(self):
        """Where the beam crosshair sits at each zoom level, for the record.

        Nothing stored this before, so there is no history: it starts
        accumulating from the first run after deployment and cannot be
        backfilled. Wanted for correlating crosshair movement against the machine
        steering and beamstop realignment question, which is why it is worth
        recording now rather than when the analysis is written.

        Reported as a single parameter rather than one per zoom level, because
        which zoom levels exist is beamline-specific - i04 has eight including
        7.5x, which i04-1 does not have - and a per-zoom parameter name would put
        that difference into every report. It is listed in hidden_parameters, so
        it is stored without appearing in the eLog table.

        This reads display.configuration, which is currently the master. The
        definitions are migrating to EPICS PVs, but the two can be out of sync, so
        the file stays authoritative until that settles. When it does, this is the
        one place to change.
        """
        positions = {}
        try:
            for zoom, values in self.get_zoom_dict().items():
                try:
                    positions[zoom] = {
                        "x": int(values["crosshairX"]),
                        "y": int(values["crosshairY"]),
                    }
                except (KeyError, ValueError):
                    continue
        except (OSError, KeyError) as error:
            self.log.warning(f"Could not read crosshair positions: {error}")
            return {}

        if not positions:
            self.log.warning("No crosshair positions found in display.configuration")
            return {}

        self.log.info(f"Crosshair positions recorded for {len(positions)} zoom levels")
        return {"Crosshair_positions": positions}

    def get_zoom_dict(self):
        # Needs location of configuration stored in self.display_configuration_file

        self.zoom_dict = {}
        with open(self.display_configuration_file) as display_configuration:
            for line in display_configuration:
                parsed_line = line.split("=")
                if parsed_line[0].strip() == "zoomLevel":
                    n = 0
                    current_zoom = parsed_line[1].strip()
                    self.zoom_dict[current_zoom] = {}
                self.zoom_dict[current_zoom][parsed_line[0].strip()] = parsed_line[
                    1
                ].strip()

        # Example of zoom_dict structure, values will be different
        # {'1.0': {'bottomRightX': '410',
        #         'bottomRightY': '278',
        #         'crosshairX': '589',
        #         'crosshairY': '359',
        #         'topLeftX': '383',
        #         'topLeftY': '253',
        #         'zoomLevel': '1.0'},
        # '1.5': {'bottomRightX': '410',
        #         'bottomRightY': '278',
        #         'crosshairX': '582',
        #         'crosshairY': '359',
        #         'topLeftX': '383',
        #         'topLeftY': '253',
        #     }

        return self.zoom_dict

    # What has to be true before the images mean anything. Without these the
    # module can photograph a dark field and report it as a beam alignment -
    # obvious to a person looking at the image, which is why it went unchecked so
    # long, but nothing in the assessment said so.
    #
    # The thresholds live in AlignBeam.i04.yaml like every other check, and the
    # parameters are in hidden_parameters, so they are read, judged and logged
    # without adding three rows saying "Open" to the report every morning. They
    # earn their place by stopping the module, not by being read.
    BEAM_PRESENT_CHECKS = {
        "Scintillator_Y": "the scintillator is not in the beam",
        "Endstation_shutter": "the endstation shutter is not open",
        "Fast_shutter": "the fast shutter is not open",
        "FLUX": "there is no flux",
    }

    def checks(self, assessed=None):
        """Is the beamline actually ready to be photographed?

        Reads the assessed parameters rather than the PVs again, so the
        thresholds stay in one place, and a beamline without one of these devices
        simply omits the rule and the check disappears with it.
        """
        if not assessed:
            self.log.warning(
                "No assessed parameters available, so the beam-present checks "
                "were skipped."
            )
            return True

        not_ready = []
        for name, complaint in self.BEAM_PRESENT_CHECKS.items():
            entry = assessed.get(name)
            if isinstance(entry, dict) and entry.get("status") == "danger":
                shown = entry.get("display", entry.get("value"))
                not_ready.append(f"{complaint} ({name} reads {shown})")

        if not_ready:
            self.not_ready_reasons = not_ready
            self.log.error("Not collecting images: " + "; ".join(not_ready))
            return False

        self.log.info(
            "Beam-present checks passed: scintillator in, shutters open, flux present."
        )
        return True

    def get_PVs(self):
        self.data = {}
        for PV_prefix, PV_dict in self.config["PVs"].items():
            for name, suffix in PV_dict.items():
                self.data[name] = getattr(self.PV_instances[PV_prefix], name)()
        self.log.info(f"Gather PV data without errors")
        return self.data

    def setup_PVs(self):
        PV_instances = {}
        for prefix, pvs in self.config["PVs"].items():
            PV_instances[prefix] = BeamlineEpics(
                prefix=prefix, _init_list_=pvs.values(), nonpvs=list(pvs.keys())
            )
            lambdas = {}
            string_pvs = set(self.config.get("string_pvs", []))
            for name, suffix in pvs.items():
                self.log.debug(
                    f"Setting functool with pv {prefix} and suffix to query {suffix}"
                )

                # Read numbers raw and text as text. Everything except FLUX used
                # to be fetched with as_string=True, which formats through the
                # PV's PREC field, so what reached the report was the number as
                # the EDM screen shows it: -5.67e-05 stored as -0.00006, and
                # 0.000108 stored as 0.00011. Comparisons with yesterday were
                # then blind to any change smaller than the display precision,
                # and a value sitting on a rounding boundary could flip between
                # two stored strings and look like a change that never happened.
                # FLUX was already special-cased for exactly this reason.
                lambdas[suffix] = functools.partial(
                    PV_instances[prefix].get, suffix, as_string=name in string_pvs
                )
                self.log.info(
                    f"Setting new property {name} on PV to run lamba and get value of {lambdas[suffix]()}"
                )
                setattr(PV_instances[prefix], name, lambdas[suffix])
        return PV_instances

    def create_image_with_text(self, path="/var/tmp/", text=""):
        new_location = f"{path}{self.username}_Z.jpg"
        img = Image.new("RGB", (1024, 768), (255, 255, 255))
        font = ImageFont.truetype("arial.ttf", 24)
        ImageDraw.Draw(img).text((100, 100), text, (0, 0, 0), font=font)
        img.save(new_location, "JPEG")
        return [new_location, "AlignBeam"]

    def get_image_from_url(self, url, location="/var/tmp/", filename="image"):
        final_location = f"{location}{self.username}_{filename}.jpg"

        response = requests.get(url, stream=True)

        zoom = self.zoom_pv.get(as_string=True).strip("x")

        with open(final_location, "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)
        del response
        return final_location, zoom

    def collect_all_zoom_images(self):
        # TODO: Ask permission to drive goniometer
        # range8: 8 zoom levels from 1X,1.5X,2X,2.5X,3X,5X,7.5X,10X with PV starting at zero
        zooms = range(8)
        self.log.info(f"Going to collect {len(zooms)} images at different zoom levels")
        picture_locations_and_zooms = [
            self.collect_single_picture(zoom) for zoom in zooms
        ]
        return picture_locations_and_zooms

    def make_montage(self, locations_with_zooms):
        locations = [path[0] for path in locations_with_zooms]
        self.log.debug(f"Files to make montage are: {locations}")
        pill_image = self.make_contact_sheet(
            locations_with_zooms, 3, 3, 1024, 768, 1, 1, 1, 1, 1, draw_beam_cross=True
        )
        temp_save = f"/var/tmp/{self.username}_montage.png"
        pill_image.save(temp_save)
        self.log.info(f"Saved montage image to {temp_save}")
        pill_image.show()
        return temp_save

    def store_beam_image_for_report(self, montage_image):
        final_location = (
            f"{self.get('directories')[self.original_class]}/beam_at_sample.png"
        )
        # Versioned: re-running this module is usually a sign the first attempt
        # was wrong, so the first attempt's image is the one worth keeping.
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
        """
        Make a contact sheet from a group of filenames:

        fnames       A list of names of the image files

        ncols        Number of columns in the contact sheet
        nrows        Number of rows in the contact sheet
        photow       The width of the photo thumbs in pixels
        photoh       The height of the photo thumbs in pixels

        marl         The left margin in pixels
        mart         The top margin in pixels
        marr         The right margin in pixels
        marb         The bottom margin in pixels

        padding      The padding between images in pixels

        returns a PIL image object.
        http://code.activestate.com/recipes/578267-use-pil-to-make-a-contact-sheet-montage-of-images/
        """

        fnames = [path[0] for path in locations_zoom]
        fzooms = [zoom[1] for zoom in locations_zoom]

        self.log.info(f"locations_zoom: {locations_zoom}")
        self.log.info(f"fnames: {fnames}")
        self.log.info(f"fzooms: {fzooms}")

        if draw_horizontal_line or draw_beam_cross:
            zoom_dict = self.get_zoom_dict()

        # Calculate the size of the output image, based on the
        #  photo thumb sizes, margins, and padding
        marw = marl + marr
        marh = mart + marb

        padw = (ncols - 1) * padding
        padh = (nrows - 1) * padding
        isize = (ncols * photow + marw + padw, nrows * photoh + marh + padh)

        # Create the new image. The background doesn't have to be white
        white = (255, 255, 255)
        self.log.debug("Creating empty white canvas")
        inew = Image.new("RGB", isize, white)

        count = 0
        # Insert each thumb:
        for irow in range(nrows):
            for icol in range(ncols):
                left = marl + icol * (photow + padding)
                right = left + photow
                upper = mart + irow * (photoh + padding)
                lower = upper + photoh
                bbox = (left, upper, right, lower)
                try:
                    name = fnames[count].split(".")[0].split("_")[1]
                    # Read in an image and resize appropriately
                    img = Image.open(fnames[count]).resize((photow, photoh))
                    # draw = ImageDraw.Draw(img)

                    if draw_horizontal_line == True:
                        self.log.debug(
                            "Ok, we have centre of rotation pictures going to draw an horizontal line"
                        )
                        # ImageDraw.Draw(img).line((512,0,512,photoh), fill=128,width=3) - vertical line not needed

                        # get crosshair for this zoom
                        # self.log.debug(zoom_dict)
                        self.log.debug(f"fzooms[count]: {fzooms[count]}")
                        Y_coordinate = int(zoom_dict[fzooms[count]]["crosshairY"])
                        self.log.debug(f"Got an Y coordinate of: {Y_coordinate}")
                        # Write horizontal line at Y height
                        ImageDraw.Draw(img).line(
                            (0, Y_coordinate, photow, Y_coordinate), fill=128, width=3
                        )
                        self.log.debug(
                            f"Line from 0,{Y_coordinate} to {photow},{Y_coordinate} drawn"
                        )

                    if draw_beam_cross == True and fzooms[count] != "AlignBeam":
                        self.log.info(
                            "Ok, we have beam in yag image. Going to draw a cross"
                        )
                        self.log.debug(f"fzooms[count]: {fzooms[count]}")
                        self.log.debug(f"fzooms[count]: {fzooms[count]}")
                        from pprint import pprint

                        pprint(zoom_dict)
                        Y_coordinate = int(zoom_dict[fzooms[count]]["crosshairY"])
                        X_coordinate = int(zoom_dict[fzooms[count]]["crosshairX"])
                        size_of_line = (
                            15  # size in pixels for vertical and horizontal lines
                        )

                        self.log.debug(
                            "Draw horizontal line with size equal size_of_line"
                        )
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

                        self.log.debug(
                            "Draw vertical line with size equal size_of_line"
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
                    self.log.debug("Draw text over image with ImageFont")
                    ImageDraw.Draw(img).text(
                        (0, 0), fzooms[count], (255, 255, 255), font=font
                    )
                except Exception as e:
                    self.log.critical(
                        f"Failed to prepare montage with error {e} for image {count}"
                    )
                self.log.info("Pasting the images into the white canvas")
                inew.paste(img, bbox)
                count += 1
        self.log.debug("Finished making montage. Giving it back")
        return inew

    # In AlignBeam.py, inside the OpticsChecks class

    def _assess_parameters(self, pv_data):
        """Assess the gathered PVs against the rules in AlignBeam.yaml.

        The generic checks are handled by the shared engine on MOD_Base; only
        FLUX needs local work, because it is the one rule that has to combine two
        parameters (flux and transmission) before it can be compared.
        """
        self.log.info("Assessing beam alignment parameters for status...")

        rules = self.config.get("assessment_rules", {})
        previous_report = self.parent_module._get_previous_report_data() or {}
        previous_params = (
            previous_report.get("parameters") or previous_report.get("EPICS") or {}
        )

        structured_params = self.parent_module.assess_parameters(
            pv_data,
            rules,
            previous_params,
            where="AlignBeam",
            hidden=self.config.get("hidden_parameters", []),
        )

        self._assess_normalised_flux(structured_params, previous_params, rules)

        if "FLUX" in structured_params:
            structured_params["FLUX"]["value"] = self.parent_module.format_scientific(
                structured_params["FLUX"]["value"]
            )

        return structured_params

    def _normalise_flux(self, flux, transmission):
        """Flux scaled to what it would be at 100% transmission.

        Staff align at whatever transmission suits the day, so the raw reading is
        not comparable between setups; normalising makes it so. Measured
        day-to-day variation at constant transmission is about 1.3%, against
        roughly 5% once transmission changes are mixed in, which is why this
        matters more than it looks.
        """
        transmission = float(transmission)
        if transmission <= 0:
            raise ZeroDivisionError("transmission is zero or negative")
        return (float(flux) / transmission) * 100

    def _assess_normalised_flux(self, structured_params, previous_params, rules):
        """The custom_flux rule: compare today's normalised flux with yesterday's."""
        rule = rules.get("FLUX")
        if (
            not rule
            or self.parent_module.resolve_check_type(rule.get("check_type"))
            != "custom_flux"
        ):
            return
        if self.parent_module.validate_assessment_rule("FLUX", rule):
            return  # already logged and marked by the shared engine

        get = self.parent_module._plain_value
        current_flux = get(structured_params.get("FLUX"))
        current_transmission = get(structured_params.get("TRANSMISSION"))
        previous_flux = get(previous_params.get("FLUX"))
        previous_transmission = get(previous_params.get("TRANSMISSION"))

        if any(
            value is None
            for value in (
                current_flux,
                current_transmission,
                previous_flux,
                previous_transmission,
            )
        ):
            structured_params.setdefault("FLUX", {})[
                "note"
            ] = "no previous flux and transmission pair to compare against"
            return

        try:
            now = self._normalise_flux(current_flux, current_transmission)
            before = self._normalise_flux(previous_flux, previous_transmission)
        except (ValueError, TypeError, ZeroDivisionError) as error:
            self.log.error(f"Could not normalise flux: {error}")
            structured_params["FLUX"]["note"] = f"could not normalise flux: {error}"
            return

        status = self.parent_module.assess_deadband(
            now, before, rule["limits"], "percent"
        )
        if status:
            structured_params["FLUX"]["status"] = status

        change = abs(now - before) / before * 100 if before else float("inf")
        self.log.info(
            f"Flux normalised to 100% transmission: today {now:.3e}, "
            f"yesterday {before:.3e}, change {change:.1f}% "
            f"(good <= {rule['limits'][0]}%) -> {status}"
        )


class BeamlineEpics(epics.Device):
    def __init__(self, prefix=None, _init_list_=(), nonpvs=[]):
        nonpvs = nonpvs + list(epics.Device._nonpvs)
        epics.Device.__init__(
            self, prefix=prefix, delim=":", attrs=list(_init_list_), nonpvs=nonpvs
        )
