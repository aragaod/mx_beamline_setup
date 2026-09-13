import os
import json
import getpass
from jinja2 import Environment, FileSystemLoader
from .posters import ElogPoster
from datetime import datetime
from PIL import Image  # <--- Added for resizing


class Submit_Logbook:
    """
    Class for preparation and submission of beamline setup logbook entries
    """

    def __init__(self, module_config, original_class_name, log, data, username):
        self.config = module_config
        self.original_class = original_class_name
        self.log = log
        self.log.info(
            f"Config is {self.config.keys()} and class name is {self.original_class}"
        )
        self.payload_data = data
        self.beamline_scientist = getpass.getuser()
        self.beamline = "I04"
        self.fedid = username
        self.now = datetime.now()
        self.log.info(f"Logbook entry performed by {self.beamline_scientist}")
        bl_release_env = os.environ.get("BLrelease", "production").lower()
        is_production = bl_release_env == "production"
        self.log.info(
            f"BLrelease environment is '{bl_release_env}'. eLog poster set to production mode: {is_production}"
        )
        self.logbook = ElogPoster(
            beamline=self.beamline, poster=self.fedid, production_server=is_production
        )
        self.data = self.data_parsing()

    def prepare_images(self, image_dictionary):
        """
        ELOG requires images to be pre-uploaded and the URL to be assigned for inclusion in posts.
        """
        image_links = self.logbook.upload_multiple_files(image_dictionary)
        return image_links

    def prepare_image(self, image_path):
        """
        Generates a small JPG thumbnail for email compatibility, uploads both,
        and returns links for both the thumbnail and the full-res version.
        """
        if not os.path.exists(image_path):
            self.log.error(f"Image not found: {image_path}")
            return {"image": "", "full_link": ""}

        # 1. Define Thumbnail Path (saved in same folder as original)
        folder, filename = os.path.split(image_path)
        basename, ext = os.path.splitext(filename)
        thumb_path = os.path.join(folder, f"{basename}_thumb.jpg")

        # 2. Generate Thumbnail using PIL
        try:
            with Image.open(image_path) as img:
                # Convert to RGB (handles PNG transparency issues)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Resize if larger than 600px width (standard email width)
                max_width = 600
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                # Save compressed JPG
                img.save(thumb_path, "JPEG", quality=60)
                self.log.info(f"Generated thumbnail: {thumb_path}")
        except Exception as e:
            self.log.error(f"Thumbnail generation failed: {e}. Using original.")
            thumb_path = image_path

        # 3. Upload Thumbnail (For display in email/log)
        # We use key 'image' because the template expects that key for the src
        link_thumb = self.logbook.upload_file_get_link("image", thumb_path)
        url_thumb = link_thumb.get("image", "")

        # 4. Upload Original (For the hyperlink)
        link_full = self.logbook.upload_file_get_link("full_image", image_path)
        url_full = link_full.get("full_image", "")

        return {
            "image": url_thumb,  # Used in <img src="...">
            "full_link": url_full,  # Used in <a href="...">
        }

    def data_parsing(self):
        self.log.info(f"Redis payload keys are: {self.payload_data.keys()}")
        self.date = self.now.strftime("%Y%m%d")
        self.datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.human_readable_date = self.now.strftime("%A, %d %B %Y")
        self.log.info(f"self.date is {self.date}")
        self.data = {
            "beamline": self.beamline,
            "date": self.date,
            "human_readable_date": self.human_readable_date,
            "beamline_scientist": self.beamline_scientist,
            "image_width_px": 600,
            "modules": self.payload_data,
        }
        for module in self.data["modules"]:
            module_data = self.data["modules"][module]

            if "images" in module_data.keys() and module_data["images"]:
                module_data["image_url"] = self.prepare_image(module_data["images"][0])

            # Process puck images from the local disk
            if "processed_pucks" in module_data:
                module_data["puck_elog_images"] = {}
                for puck_group in module_data["processed_pucks"]:
                    for puck in puck_group.get("pucks", []):
                        puck_name = puck.get("name")
                        local_path = puck.get("local_path")

                        if puck_name and local_path and os.path.exists(local_path):
                            if puck_name not in module_data["puck_elog_images"]:
                                elog_links = self.prepare_image(local_path)
                                module_data["puck_elog_images"][puck_name] = elog_links

        return self.data

    def prepare_logbook_entry(
        self,
        templates_folder="modules/CreateReport/templates",
        template_file="beamline_logbook_template.jinja2",
    ):
        THIS_DIR = os.path.join(os.getcwd(), templates_folder)
        self.log.debug(f"Templates for beamline setup in {THIS_DIR}")
        j2_env = Environment(loader=FileSystemLoader(THIS_DIR), trim_blocks=True)
        return j2_env.get_template(template_file).render(data=self.data)

    def submit_logbook(self, title, content):
        response = self.logbook.post(title, content)
        return response
