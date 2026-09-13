from base import MOD_Base

# GUI
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QGroupBox,
    QRadioButton,
    QDialogButtonBox,
    QApplication,
)


# APP
import os
import getpass, pwd
from datetime import datetime, date
from jinja2 import Environment, FileSystemLoader
import random
import subprocess

import pprint

import yaml as config_loader

from modules.EmailReady.GUI_EmailReady import TemplateSelectionDialog


class EmailReady(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading {self.class_name}_MD module/instance")
        self.now = datetime.now()
        self.read_module_config()

        # Define the widget type to update when finalised with the job
        # self.widget2update = 'CB' # THIS HAS BEEN MOVED TO THE CONFIGURATION FILE

    def read_module_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "EmailReady.yaml")
        self.config_module = {}
        with open(file_path, "r") as f:
            self.config_module = config_loader.load(f, Loader=config_loader.FullLoader)

    def get_seasonal_template_for_today(self):
        """
        Selects the appropriate seasonal template based on the current date
        by checking against date ranges defined in the YAML config.
        If a fallback is needed, it uses the first template defined in the
        main 'email_styles' config.
        """
        email_styles = self.config_module.get("email_styles", [])
        ultimate_fallback_template = None
        if email_styles:
            ultimate_fallback_template = email_styles[0].get("template")

        if not ultimate_fallback_template:
            self.log.error(
                "CRITICAL: No 'email_styles' configured in YAML. Cannot determine a fallback template."
            )
            return None  # Return None to be handled by the run() method

        seasonal_configs = self.config_module.get("seasonal_templates", [])
        if not seasonal_configs:
            self.log.error(
                "No 'seasonal_templates' definition found in config. Using first available style as fallback."
            )
            return ultimate_fallback_template

        today = date.today()

        for config in seasonal_configs:
            if "date_ranges" not in config:
                self.log.info(
                    f"No specific season matched. Using general template: {config['file']}"
                )
                return config["file"]

            for start_month, start_day, end_month, end_day in config["date_ranges"]:
                try:
                    start_date = date(today.year, start_month, start_day)
                    end_date = date(today.year, end_month, end_day)

                    if start_date > end_date:  # Handles ranges crossing the new year
                        if (today >= start_date) or (today <= end_date):
                            self.log.info(
                                f"Date matched (crossover): {config['name']}. Using template: {config['file']}"
                            )
                            return config["file"]
                    else:  # Standard check for ranges within the same year
                        if start_date <= today <= end_date:
                            self.log.info(
                                f"Date matched: {config['name']}. Using template: {config['file']}"
                            )
                            return config["file"]
                except ValueError:
                    self.log.warning(
                        f"Invalid date in YAML for seasonal template '{config.get('name', 'Unknown')}'. Skipping."
                    )
                    continue

        # This fallback is for a malformed seasonal_configs list (e.g., no general entry)
        self.log.warning(
            "Fell through all seasonal checks. Using ultimate fallback template."
        )
        return ultimate_fallback_template

    def run(self):
        """
        Base Modules classe run method is overwritten here by this run method.
        """
        if self.before():
            self.set_running()

            email_styles_config = self.config_module.get("email_styles", [])
            if not email_styles_config:
                self.log.error(
                    "No 'email_styles' configuration found in EmailReady.yaml!"
                )
                self.set_stopped()
                return False

            dialog = TemplateSelectionDialog(email_styles_config)

            if dialog.exec_() == QDialog.Accepted:
                selected_style_id = dialog.get_selected_style_id()

                if not selected_style_id:
                    self.log.warning("No template style was selected from the dialog.")
                    self.set_stopped()
                    return False

                final_template_file = ""
                selected_config = next(
                    (
                        style
                        for style in email_styles_config
                        if style["id"] == selected_style_id
                    ),
                    None,
                )

                if not selected_config:
                    self.log.error(
                        f"Could not find configuration for selected style ID: {selected_style_id}"
                    )
                    self.set_stopped()
                    return False

                # Check the type and get the final template filename
                choice_type = selected_config.get("type")

                if choice_type == "random_choice":
                    templates = selected_config.get("templates", [])
                    if templates:
                        final_template_file = random.choice(templates)
                elif choice_type == "seasonal_choice":
                    final_template_file = self.get_seasonal_template_for_today()
                else:  # This is a standard, single-template style
                    final_template_file = selected_config.get("template")

                if not final_template_file:
                    self.log.error(
                        f"Could not determine a final template file to use for style '{selected_style_id}'."
                    )
                    self.set_stopped()
                    return False

                selected_template = final_template_file
                self.log.info(
                    f"User selected style: {selected_style_id}. Final template: {selected_template}"
                )

                self.log.debug(f"Trying to launch gedit")

                try:
                    payload_modules = {}
                    all = self.get_all()
                    for item in all.keys():
                        if f'_report_{self.now.strftime("%Y%m%d")}' in item:
                            payload_modules[item] = all[item]

                    gedit_launcher = GenerateEmailText(
                        module_config=self.config_module,
                        original_class_name=self.class_name,
                        log=self.log,
                        data=payload_modules,
                        username=self.username,
                    )

                    gedit_launcher.generate_emails_for_proposals(selected_template)

                except Exception as e:
                    self.log.error(f"Had an issue: {e}")
                finally:
                    self.set_stopped()
            else:
                # User clicked "Cancel"
                self.log.info("Email generation was cancelled by the user.")
                self.set_stopped()
                return False

        else:
            return False

        # Here some code just assess if this task ran successfully and set status to True/False
        status = True
        if status == False:
            self.set(f"{self.class_name}_status", status)
        return status


class GenerateEmailText(object):
    """
    Generates one email file per user proposal and opens them all for review.
    This is the fully corrected version with all logging restored.
    """

    def __init__(self, module_config, original_class_name, log, data, username):
        self.config = module_config
        self.original_class = original_class_name
        self.log = log

        self.log.info(
            f"Config keys: {list(self.config.keys())}, Class name: {self.original_class}"
        )

        self.payload_data = data
        self.fedid = username
        self.now = datetime.now()

        # --- Get beamline scientist with logging restored ---
        try:
            self.beamline_scientist_on_duty = self.get_current_user_full_name(
                self.fedid
            )
        except Exception as e:
            self.log.warning(f"Could not get username: {e}. Defaulting to 'i04staff'.")
            self.beamline_scientist_on_duty = "i04staff"

        self.beamline = "I04"

        self.log.info(
            f"EmailReady to be generated by {self.beamline_scientist_on_duty} for user {self.fedid}"
        )

        self.template_folder = os.path.join(os.getcwd(), "modules/EmailReady/templates")
        self.output_folder = (
            f"/var/tmp/{self.beamline}_{self.fedid}_beamline_emails_for_review"
        )

        try:
            os.makedirs(self.output_folder, exist_ok=True)
            self.log.info(f"Ensured output directory exists: {self.output_folder}")
        except OSError as e:
            self.log.error(
                f"Could not create or access output directory {self.output_folder}: {e}. Please check permissions."
            )
            raise e

        self.base_email_context = self._prepare_base_context()

    def get_current_user_full_name(self, fedid):
        """
        Gets the full name of the current user running the script.

        Returns:
            str: The user's full name, or the login username if the full name
                 cannot be found.
        """
        try:
            username = fedid
            user_info = pwd.getpwnam(username)
            # GECOS field is often "Full Name,RoomNumber,WorkPhone,HomePhone"
            # We just want the first part.
            return user_info.pw_gecos.split(",")[0]
        except (KeyError, IndexError):
            # Fallback to the username if lookup fails or GECOS is empty
            return username

    def _prepare_base_context(self):
        self.log.info(f"Raw payload keys: {list(self.payload_data.keys())}")
        if self.payload_data:
            payload_pretty_str = pprint.pformat(self.payload_data, indent=2, width=120)
            self.log.debug(f"Full content of self.payload_data:\n{payload_pretty_str}")
        else:
            self.log.debug("self.payload_data is empty or None.")

        data_for_template = {
            "beamline": self.beamline,
            "human_date": self.now.strftime("%a, %d %b %Y"),
            "i04_staff_member": self.beamline_scientist_on_duty,
            "test_data_available": False,
        }

        test_crystal_report_data = None
        if self.payload_data:
            for key, module_data in self.payload_data.items():
                if key.startswith("TestCrystal_report"):
                    test_crystal_report_data = module_data
                    # --- LOGGING RESTORED ---
                    self.log.info(f"Found TestCrystal report data under key: {key}")
                    break

        if (
            test_crystal_report_data
            and isinstance(test_crystal_report_data, dict)
            and "parameters" in test_crystal_report_data
        ):

            params = test_crystal_report_data["parameters"]

            def report_value(name):
                """The value of one parameter in today's report, or None.

                Only today's report is ever read here, so only the current key
                names apply - historical reports are renamed in place by the
                migration tool in dev/ rather than accommodated with fallbacks.
                Reports store either a bare value or {'value': ..., 'status': ...}.
                """
                entry = params.get(name)
                if entry is None:
                    return None
                return entry.get("value") if isinstance(entry, dict) else entry

            raw_rmeas = report_value("Aimless_Rmeas_low_res")
            raw_isa = report_value("ISa")

            # Name the sample that was actually mounted. Every template says the
            # same thing in different words, so all of them get the name; three
            # variables let each keep its own phrasing.
            #
            # "reference" is the fallback when the sample is not recognised - it
            # is the one word that reads correctly in all thirty-three ("on a
            # reference crystal", "our reference test data"). Users get their
            # normal email either way; an unrecognised sample is something for
            # staff to fix in the registry, not something to tell users about.
            sample = report_value("Test_sample")
            if not sample or sample == "not recognised":
                sample = "reference"
            sample = str(sample).strip()
            data_for_template["test_sample"] = sample.lower()
            data_for_template["test_sample_title"] = sample[:1].upper() + sample[1:]
            data_for_template["a_test_sample"] = (
                "an " if sample[:1].lower() in "aeiou" else "a "
            ) + sample.lower()

            if raw_rmeas is not None and raw_isa is not None:
                data_for_template["rmeas_lowres"] = str(
                    round(float(raw_rmeas) * 100, 2)
                )
                data_for_template["ISa"] = str(raw_isa).strip()
                data_for_template["test_data_available"] = True
                # --- LOGGING RESTORED ---
                self.log.info(
                    "Both Rmeas and ISa successfully processed and added to email context."
                )
            else:
                # --- LOGGING RESTORED ---
                self.log.warning(
                    "One or both Rmeas/ISa could not be processed. Test data section will be hidden."
                )
        else:
            # --- LOGGING RESTORED ---
            self.log.warning(
                "No TestCrystal report data found. Test data section will be hidden."
            )

        # --- LOGGING RESTORED ---
        self.log.info(
            f"Final 'test_data_available' flag for Jinja: {data_for_template['test_data_available']}"
        )
        return data_for_template

    def _select_template_file(self):
        available_templates = self.config.get(
            "template_files", ["email_template_A.jinja2"]
        )
        if not available_templates:
            # --- LOGGING RESTORED ---
            self.log.error("No template files are defined in the configuration!")
            raise ValueError("Configuration error: No template files specified.")

        selected_template = random.choice(available_templates)
        self.log.info(f"Using template file: {selected_template}")
        return selected_template

    def generate_emails_for_proposals(self, selected_template):
        """
        It first prepares a list of email "jobs", then executes them in a
        single loop, and finally opens all generated files at once.
        """
        try:
            # --- 1. Load Template ---
            j2_env = Environment(
                loader=FileSystemLoader(self.template_folder),
                trim_blocks=True,
                autoescape=False,
            )
            self.log.info(f"Using the user-selected template: {selected_template}")
            template = j2_env.get_template(selected_template)

            # --- 2. Prepare a List of Email Jobs ---
            email_jobs = []
            sample_load_data = next(
                (
                    v
                    for k, v in self.payload_data.items()
                    if k.startswith("SampleLoad_report")
                ),
                None,
            )
            processed_pucks = (
                sample_load_data.get("processed_pucks") if sample_load_data else None
            )

            if not processed_pucks:
                self.log.warning(
                    "No 'processed_pucks' data found. Preparing a single generic email."
                )
                # If no pucks, the job list contains one item for a generic email
                email_jobs.append({"proposal_id": "generic", "puck_info": None})
            else:
                # If pucks exist,Check that it is not commissioning, NOT a UDC puck, and not the fake comma entry
                for puck_info in processed_pucks:
                    proposal = puck_info.get("proposal")
                    if (
                        not puck_info.get("is_commissioning")
                        and not puck_info.get("is_udc")
                        and proposal != "fake_last_sans_comma"
                    ):

                        # Extract the names from a change dictionary structure so that I do not have to change all jinja2 templates
                        extracted_names = []
                        for p in puck_info.get("pucks", []):
                            if p.get("name"):
                                extracted_names.append(p.get("name"))

                        # Assign it to the key the Jinja templates are expecting
                        puck_info["puck_names"] = extracted_names
                        email_jobs.append(
                            {"proposal_id": proposal, "puck_info": puck_info}
                        )

            if not email_jobs:
                self.log.info("No valid user proposals or generic email to generate.")
                return

            # --- 3. Execute the Email Generation Jobs ---
            generated_files = []
            tips = self.config.get("extra_tips", ["Have a great experiment!"])

            for job in email_jobs:
                # Prepare a unique context for each email
                email_context = self.base_email_context.copy()
                email_context["puck_info"] = job["puck_info"]
                email_context["optional_tip"] = random.choice(tips)

                # Render the email body
                rendered_body = template.render(email_context)

                # Create the filename and save the file
                output_filename = (
                    f"email_for_{job['proposal_id']}_{self.now.strftime('%Y%m%d')}.txt"
                )
                output_filepath = os.path.join(self.output_folder, output_filename)

                with open(output_filepath, "w", encoding="utf-8") as f:
                    f.write(rendered_body)

                self.log.info(
                    f"Email for proposal '{job['proposal_id']}' saved to: {output_filepath}"
                )
                generated_files.append(output_filepath)

            # --- 4. Finalize by Opening All Generated Files ---
            if generated_files:
                self.log.info(
                    f"Attempting to open {len(generated_files)} file(s) with gedit..."
                )
                command = ["gedit"] + generated_files
                subprocess.Popen(command)
                self.log.info("Gedit launched with all email files.")

        except Exception as e:
            self.log.error(
                f"An error occurred during email generation: {e}", exc_info=True
            )
