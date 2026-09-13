from base import MOD_Base
from PyQt5 import QtCore, QtGui, QtWidgets
from modules.SampleLoad.GUI_SampleLoad import GUI
import subprocess

from beamline import ID
from devices import PuckImageClient

from PIL import Image, ImageDraw, ImageFont
import getpass
from datetime import datetime
import os, glob, re, json, shutil, functools, time
import epics
import requests
import io


class SampleLoad(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now().strftime("%Y%m%d")
        self.can_proceed = True

    def launch_GUI(self):
        self.SampleLoad_WZ = QtWidgets.QWizard()
        self.ui = GUI()
        self.log.debug(f"Created ui instance for new window for {self.class_name}")
        self.ui.read_config()

        self.ui.config["json_file_location"] = self.ui.config[
            "json_file_location"
        ].format(BEAMLINE=self.ID)

        self.ui.setupUi(
            self.SampleLoad_WZ,
            width=self.ui.config["width"],
            height=self.ui.config["height"],
        )

        self.SampleLoad_WZ.button(QtWidgets.QWizard.FinishButton).clicked.connect(
            self.set_status_true
        )
        self.SampleLoad_WZ.button(QtWidgets.QWizard.CancelButton).clicked.connect(
            self.set_status_false
        )
        self.SampleLoad_WZ.button(QtWidgets.QWizard.NextButton).clicked.connect(
            self.next
        )
        self.SampleLoad_WZ.button(QtWidgets.QWizard.BackButton).clicked.connect(
            self.back
        )
        self.SampleLoad_WZ.rejected.connect(self.reject)

        self.SampleLoad_WZ.setWindowModality(QtCore.Qt.ApplicationModal)
        self.SampleLoad_WZ.show()

        # --- CHECK 1: Blocked Positions (Immediate) ---
        self.check_blocked_positions()

    def check_blocked_positions(self):
        """
        Checks if the sample changer blocked positions file is empty.
        If not, warns the user using text from config.
        """
        blocked_file = self.ui.config.get("blocked_positions_file")

        if not blocked_file:
            self.log.warning("No blocked_positions_file defined in config.")
            return

        self.log.info(f"Checking Blocked Positions file: {blocked_file}")

        try:
            if os.path.exists(blocked_file):
                with open(blocked_file, "r") as f:
                    content = f.read().strip()

                if content:
                    # File is NOT empty, show warning
                    self.log.warning(f"Blocked positions found in {blocked_file}")
                    self.log.warning(f"Content: {content}")

                    popup_buttons = [
                        (
                            "I Understand",
                            QtWidgets.QMessageBox.YesRole,
                            "proceedButton",
                        ),
                    ]

                    # Get text from config (with defaults)
                    warn_conf = self.ui.config.get("blocked_positions_warning", {})
                    title = warn_conf.get("title", "Robot Blocked Positions Detected")
                    msg = warn_conf.get(
                        "message",
                        "Attention: There are blocked positions in the robot dewar.",
                    )

                    self.ui.show_urgent_warning(
                        self.SampleLoad_WZ,
                        title=title,
                        text="Blocked Positions File is not empty!",
                        informative_text=msg + f"\n\nFile Content:\n{content}",
                        buttons=popup_buttons,
                    )
                else:
                    # --- ADDED LOG MESSAGE ---
                    self.log.info(
                        f"Blocked positions check passed. File is empty: {blocked_file}"
                    )
            else:
                self.log.debug(f"Blocked positions file does not exist: {blocked_file}")
        except Exception as e:
            self.log.error(f"Error checking blocked positions file: {e}")

    def next(self):
        """
        Called when Next is pressed.
        Performs the JSON file age check here.
        """
        self.log.debug("Next button pressed.")

        # --- CHECK 2: JSON File Age (Moved from launch_GUI) ---
        if not self.run_json_age_check():
            # If user clicked Cancel or is Editing, do not proceed
            return

        self.log.debug("Checks passed. Going to graph robot dewar image")
        self.collect_pucks_data()

    def run_json_age_check(self):
        """
        Checks the age of the proposal_positions.json file.
        Returns True if allowed to proceed, False if cancelled/editing.
        """
        age_check_config = self.ui.config.get("json_file_age_check", {})
        if not age_check_config.get("enabled", False):
            return True

        file_path = self.ui.config["json_file_location"]
        max_age_info = age_check_config.get("max_age")
        is_file_recent = self.check_file_age(file_path, max_age_info)

        if not is_file_recent:
            unit = max_age_info.get("unit", "hours")
            value = max_age_info.get("value", 12)

            self.log.warning("STALE FILE DETECTED!")

            popup_buttons = [
                ("Proceed Anyway", QtWidgets.QMessageBox.YesRole, "proceedButton"),
                ("Edit File", QtWidgets.QMessageBox.ActionRole, "editButton"),
                ("Cancel", QtWidgets.QMessageBox.RejectRole, "cancelButton"),
            ]

            choice = self.ui.show_urgent_warning(
                self.SampleLoad_WZ,
                title="Stale File Warning",
                text=f"The proposal_positions.json file is older than {value} {unit}.",
                informative_text="You can proceed anyway, cancel, or open the file for editing.\n\n"
                "If you choose to edit, this window will close and you can restart the 'Load Samples' task after saving the file.",
                buttons=popup_buttons,
            )

            if choice == "Proceed Anyway":
                self.log.warning("User chose to PROCEED with the old JSON file.")
                return True
            elif choice == "Edit File":
                self.log.info("User chose to EDIT the JSON file. Opening gedit...")
                try:
                    subprocess.Popen(["gedit", file_path])
                except FileNotFoundError:
                    self.log.error("Could not find 'gedit'.")
                self.set_status_false()
                self.SampleLoad_WZ.close()
                return False
            else:
                self.log.info("User chose to CANCEL the operation.")
                self.set_status_false()
                self.SampleLoad_WZ.close()
                return False

        return True

    def back(self):
        self.log.debug("Back button pressed")

    def reject(self):
        self.log.debug("Kill X was clicked")
        self.set_status_false()

    def collect_pucks_data(self):
        payload = {}

        self.log.debug(f"Initialising RobotImageProcessor")
        img_processor = RobotImageProcessor(
            displace_existing=self.displace_existing,
            base_url=self.ui.config["logistics_api_base_url"],
            log=self.log,
            redis_get_method=self.get,
            module_config=self.ui.config,
            original_class_name=self.class_name,
            json_file_path=self.ui.config["json_file_location"],
            beamline_id=self.ID,
        )

        latest_image_url = img_processor.fetch_latest_image_url()
        if latest_image_url:
            # --- CHECK 3: Image Age Check ---
            age_check_config = self.ui.config.get("image_age_check", {})
            if age_check_config.get("enabled", False):
                max_age_info = age_check_config.get(
                    "max_age", {"unit": "hours", "value": 12}
                )
                image_filename = os.path.basename(latest_image_url)
                is_image_recent = self.check_age_from_filename(
                    image_filename, max_age_info
                )

                if not is_image_recent:
                    unit = max_age_info.get("unit", "hours")
                    value = max_age_info.get("value", 12)
                    self.log.warning("Stale dewar image detected.")

                    popup_buttons = [
                        (
                            "Proceed Anyway",
                            QtWidgets.QMessageBox.YesRole,
                            "proceedButton",
                        ),
                        ("Cancel", QtWidgets.QMessageBox.RejectRole, "cancelButton"),
                    ]

                    choice = self.ui.show_urgent_warning(
                        self.SampleLoad_WZ,
                        title="Stale Image Warning",
                        text=f"The latest dewar image is older than {value} {unit}.",
                        informative_text="This could mean the pucks in the report are not correct.\n\nDo you want to proceed anyway?",
                        buttons=popup_buttons,
                    )

                    if choice != "Proceed Anyway":
                        self.log.info(
                            "User cancelled operation due to old dewar image."
                        )
                        self.SampleLoad_WZ.close()
                        return

            img = img_processor.load_image()
            if img:
                img_with_overlay = img_processor.add_overlay_text_to_image(
                    img,
                    font_size=20,
                    text_color=(255, 255, 0),
                    beamline_offset=(10, 10),
                    table_offset=(10, -10),
                    col_padding=30,
                    line_spacing_factor=1.4,
                )

                temp_image_path = img_processor.save_image(img_with_overlay)
                img_processor.show_image(img_with_overlay)
                final_location = img_processor.store_beam_image_for_report(
                    temp_image_path
                )

                payload["parameters"] = img_processor.get_PVs()
                if final_location:
                    payload["images"] = [final_location]
                else:
                    payload["images"] = []  # Empty list won't crash CreateReport

                interactive_pucks_raw = img_processor.proposal_data
                params_table = payload.get("parameters", {})
                payload["table_title"] = self.ui.config.get("report_table_title")
                processed_puck_list = []

                # --- 1. Gather ALL pucks physically present in the dewar ---
                all_found_pucks = []
                for loc in range(1, 38):
                    formatted_loc = f"{loc:02d}"
                    epics_key = f"Puck name in location {formatted_loc}"
                    puck_name = params_table.get(epics_key)
                    # If EPICS says a puck is here, queue it for download
                    if puck_name and puck_name.strip():
                        all_found_pucks.append(puck_name)

                # Initialize the client, get URLs, and download locally
                try:
                    puck_client = PuckImageClient()
                    puck_urls_dict = puck_client.get_multiple_puck_urls(all_found_pucks)

                    # --- NEW: Download to local report directory ---
                    local_puck_images = {}
                    report_dir = self.get("directories")[self.class_name]

                    for p_name, p_url in puck_urls_dict.items():
                        if p_url:
                            try:
                                response = requests.get(p_url, stream=True, timeout=10)
                                if response.status_code == 200:
                                    local_filename = os.path.join(
                                        report_dir, f"{p_name}.png"
                                    )
                                    with open(local_filename, "wb") as f:
                                        for chunk in response.iter_content(1024):
                                            f.write(chunk)
                                    # Ensure group permissions are correct
                                    shutil.chown(local_filename, group="mx_staff")
                                    local_puck_images[p_name] = local_filename
                                    time.sleep(
                                        0.2
                                    )  # sleep or 200 ms between image download
                            except Exception as e:
                                self.log.error(
                                    f"Failed to download {p_name} image: {e}"
                                )

                except Exception as e:
                    self.log.error(f"Failed to fetch puck images: {e}")
                    puck_urls_dict = {}
                    local_puck_images = {}

                # --- 2. Build the final payload list ---
                assigned_locations = set()

                # First, process the scheduled proposals from the JSON file
                for proposal, locations in interactive_pucks_raw.items():
                    if proposal == "fake_last_sans_comma":
                        continue

                    if locations:
                        assigned_locations.update(locations)

                    is_commissioning = proposal.lower().startswith("cm")
                    pucks_data = []

                    if locations:
                        for loc in locations:
                            formatted_loc = f"{loc:02d}"
                            epics_key = f"Puck name in location {formatted_loc}"
                            puck_name = params_table.get(epics_key)
                            if puck_name and puck_name.strip():
                                pucks_data.append(
                                    {
                                        "name": puck_name,
                                        "url": puck_urls_dict.get(puck_name),
                                        "local_path": local_puck_images.get(puck_name),
                                        "is_udc": False,  # TAG FOR JINJA2
                                    }
                                )

                    processed_puck_list.append(
                        {
                            "proposal": proposal,
                            "locations": locations,
                            "pucks": pucks_data,
                            "is_commissioning": is_commissioning,
                            "is_udc": False,  # TAG FOR JINJA2
                        }
                    )

                # --- 3. Process the remaining UDC pucks ---
                udc_pucks_data = []
                udc_locations = []

                for loc in range(1, 38):
                    # If the location wasn't claimed by the JSON file, it's UDC
                    if loc not in assigned_locations:
                        formatted_loc = f"{loc:02d}"
                        epics_key = f"Puck name in location {formatted_loc}"
                        puck_name = params_table.get(epics_key)

                        if puck_name and puck_name.strip():
                            udc_locations.append(loc)
                            udc_pucks_data.append(
                                {
                                    "name": puck_name,
                                    "url": puck_urls_dict.get(puck_name),
                                    "local_path": local_puck_images.get(puck_name),
                                    "is_udc": True,  # TAG FOR JINJA2
                                }
                            )

                # Append a special UDC section if we found any
                if udc_pucks_data:
                    processed_puck_list.append(
                        {
                            "proposal": "UDC / Unassigned",
                            "locations": udc_locations,
                            "pucks": udc_pucks_data,
                            "is_commissioning": False,
                            "is_udc": True,  # TAG FOR JINJA2
                        }
                    )

                payload["processed_pucks"] = processed_puck_list

                # Say so when there is nothing there. An empty dewar and a
                # successful load look identical in a report that only lists what
                # it found, and a reader cannot tell "nothing was loaded" from
                # "this check did not run".
                if not any(entry.get("pucks") for entry in processed_puck_list):
                    payload["no_pucks_message"] = (
                        "No pucks are loaded in the robot dewar: all 37 positions "
                        "read empty in the robot's EPICS records, so no puck "
                        "images were fetched. Nothing needs editing by hand - "
                        "this comes from the robot, not from a file."
                    )
                    self.log.warning(
                        "The robot reports no pucks in any position, so no puck "
                        "images were fetched."
                    )
                    # Acknowledge only, and the module still counts as done. An
                    # empty dewar is a legitimate state - during a shutdown it is
                    # the expected one - so this is worth telling the operator in
                    # case they expected pucks, not worth refusing over.
                    self.ui.show_urgent_warning(
                        self.SampleLoad_WZ,
                        title="No Pucks Found In The Robot Dewar",
                        text="The robot reports no pucks in any position.",
                        informative_text=(
                            "All 37 positions read empty <b>in the robot's EPICS "
                            "records</b>, so no puck images were fetched."
                            "<br><br>If the dewar really is empty, this is "
                            "expected and nothing needs doing."
                            "<br><br>If pucks <i>are</i> loaded, the problem is "
                            "with the robot EPICS PVs rather than with the dewar, "
                            "and the puck names will be missing from the report."
                            "<br><br><b>Do not edit the puck JSON file to work "
                            "around this.</b> These positions are read live from "
                            "the robot; editing a file will not change what the "
                            "robot reports and will leave the report disagreeing "
                            "with the dewar."
                        ),
                        buttons=[
                            (
                                "Understood",
                                QtWidgets.QMessageBox.AcceptRole,
                                "acceptButton",
                            )
                        ],
                    )
            else:
                self.log.error("Failed to load image from URL")
        else:
            self.log.error("Could not find image URL from API")

        self.store_report(payload)


class BeamlineEpics(epics.Device):
    def __init__(self, prefix=None, _init_list_=(), nonpvs=[]):
        nonpvs = nonpvs + ["get_PV_change_time"] + list(epics.Device._nonpvs)
        epics.Device.__init__(
            self, prefix=prefix, delim=":", attrs=list(_init_list_), nonpvs=nonpvs
        )


class RobotImageProcessor:
    def __init__(
        self,
        log,
        redis_get_method,
        module_config,
        original_class_name,
        json_file_path=None,
        beamline_id="I04",
        base_url="https://logistics.example.org",
        displace_existing=None,
    ):
        # Passed in rather than inherited: this is a plain helper, not a module,
        # so it has no `displace_existing` of its own. Without it a second run of
        # the day overwrites the first run's dewar picture (B6).
        self.displace_existing = displace_existing or (lambda path: None)
        self.log = log
        self.get = redis_get_method
        self.config = module_config
        self.original_class = original_class_name
        self.username = getpass.getuser()
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/cgi-bin/barcodes.py?q=getDewarImages"
        self.latest_image_url = None
        self.json_file_path = json_file_path
        self.beamline_id = beamline_id
        self.proposal_data = {}
        self.now = datetime.now().strftime("%Y%m%d")
        self.PV_instances = self.set_PVs()
        if self.json_file_path:
            self._load_json_data()

    def fetch_latest_image_url(self):
        try:
            response = requests.get(self.api_endpoint, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data:
                return None
            self.latest_image_url = f"{self.base_url}/{data[0]}"
            return self.latest_image_url
        except Exception:
            return None

    def load_image(self):
        if not self.latest_image_url:
            return None
        try:
            response = requests.get(self.latest_image_url, timeout=10)
            return Image.open(io.BytesIO(response.content))
        except Exception:
            return None

    def _load_json_data(self):
        if not self.json_file_path:
            return
        try:
            with open(self.json_file_path, "r") as f:
                self.proposal_data = json.load(f)
        except Exception:
            self.proposal_data = {}

    def _format_proposal_data_for_table(self):
        table_rows = []
        if not self.proposal_data:
            return [("N/A", "No Data")]
        table_rows.append(("Proposal ID", "Puck Positions"))
        for p_id, p_ids in self.proposal_data.items():
            table_rows.append(
                (p_id, f"[{', '.join(map(str, p_ids))}]" if p_ids else "None")
            )
        return table_rows

    def add_overlay_text_to_image(
        self,
        pil_image,
        font_size=20,
        text_color=(255, 255, 0),
        beamline_offset=(10, 10),
        table_offset=(10, -10),
        col_padding=20,
        line_spacing_factor=1.2,
    ):
        if not pil_image:
            return None
        draw = ImageDraw.Draw(pil_image)
        try:
            font = ImageFont.load_default(size=font_size)
        except:
            font = ImageFont.load_default()

        draw.text(
            beamline_offset, f"Beamline {self.beamline_id}", fill=text_color, font=font
        )

        table_rows = self._format_proposal_data_for_table()
        if not table_rows:
            return pil_image

        temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        bbox = temp_draw.textbbox((0, 0), "Test", font=font)
        line_height = bbox[3] - bbox[1]

        max_w = 0
        for p_id, _ in table_rows:
            w = temp_draw.textbbox((0, 0), p_id, font=font)[2]
            if w > max_w:
                max_w = w

        col1_x = table_offset[0]
        col2_x = col1_x + max_w + col_padding

        total_h = len(table_rows) * line_height * line_spacing_factor
        curr_y = pil_image.height + table_offset[1] - total_h

        for p_id, p_list in table_rows:
            draw.text((col1_x, curr_y), p_id, fill=text_color, font=font)
            draw.text((col2_x, curr_y), p_list, fill=text_color, font=font)
            curr_y += line_height * line_spacing_factor

        return pil_image

    def show_image(self, pil_image):
        if pil_image:
            pil_image.show()

    def save_image(self, pil_image):
        path = f"/var/tmp/{self.username}_robot_dewar.png"
        pil_image.save(path)
        return path

    def store_beam_image_for_report(self, final_image):
        loc = f"{self.get('directories')[self.original_class]}/robot_dewar.png"
        try:
            # Keep the previous run's picture before copying over it (B6).
            self.displace_existing(loc)
            shutil.copy2(final_image, loc)
            shutil.chown(loc, group="mx_staff")
            return loc
        except Exception as e:
            self.log.error(
                f"Failed to copy or chown robot_dewar.png: {e}"
            )  # Log the actual error
            # If chown fails, the file might still be there, so we return the loc anyway just in case
            if os.path.exists(loc):
                return loc
            return None

    def get_PVs(self):
        data = {}
        for prefix, pvs in self.config["PVs"].items():
            for name, _ in pvs.items():
                data[name] = getattr(self.PV_instances[prefix], name)()
        return data

    def set_PVs(self):
        instances = {}
        for prefix, pvs in self.config["PVs"].items():
            instances[prefix] = BeamlineEpics(
                prefix=prefix, _init_list_=pvs.values(), nonpvs=list(pvs.keys())
            )
            for name, suffix in pvs.items():
                setattr(
                    instances[prefix],
                    name,
                    functools.partial(instances[prefix].get, suffix, as_string=True),
                )
        return instances
