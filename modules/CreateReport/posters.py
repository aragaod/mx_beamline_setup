import socket

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from requests_toolbelt import user_agent

import json
from jinja2 import Environment, FileSystemLoader
import os


class ElogPoster:
    # This class is to be used in automated scripts to post to elog
    def __init__(
        self,
        beamline,
        poster="",
        keyword="Automated",
        production_server=True,
    ):

        # Store file and IP where this is running from
        self.script = "BLibrary"
        self.ip = socket.gethostname().split(".")[0]
        self.file = __file__

        # The below can be changed at a laster stage after the instance of the class was created as they are class variables
        self.logid = f"BL{beamline.capitalize()}"
        self.groupid = self.logid
        # self.userid = f'{self.script} script ran from {self.ip}'
        self.userid = poster

        self.keyword = keyword

        if production_server:
            # Entry points - configure for your facility's electronic logbook
            self.fileposturl = (
                "http://elog.example.org/php/elog/cs_logonlyimageupload_ext_bl.php"
            )
            self.elogposturl = (
                "http://elog.example.org/php/elog/cs_logentryext_bl.php"
            )
            self.entrytype = "48"
        else:
            # Test server for development
            self.fileposturl = "http://elog.example.org/devl/php/elog/cs_logonlyimageupload_ext_bl.php"
            self.elogposturl = (
                "http://elog.example.org/devl/php/elog/cs_logentryext_bl.php"
            )
            self.entrytype = "54"

        # Define standard payload
        self.payload = {
            "txtLOGBOOKID": self.logid,
            "txtGROUPID": self.groupid,
            "txtENTRYTYPEID": self.entrytype,
            "txtUSERID": self.userid,
        }

    def post(self, title, text):
        # For a simple post of html to elog use this function
        self.payload["txtTITLE"] = title
        self.payload["txtCONTENT"] = text

        # --- NEW DEBUGGING CODE ---
        # Print the exact payload we are sending to the server
        print("\n--- [DEBUG] ELOG PAYLOAD BEING SENT ---")
        import pprint

        pprint.pprint(self.payload)
        print("-------------------------------------\n")
        # --- END DEBUGGING ---

        request = requests.post(self.elogposturl, self.payload)

        # --- NEW DEBUGGING CODE ---
        # Print the full text of the server's response, even if the status is 200
        print(f"\n--- [DEBUG] ELOG SERVER RESPONSE (Status: {request.status_code}) ---")
        print(request.text)
        print("-----------------------------------------\n")
        # --- END DEBUGGING ---

        return request

    def upload_file_get_link(self, name, file_location):
        # To upload an image to elog and obtain a link to build the html use this function
        self.files = {"userfile1": open(file_location, "rb")}

        self.data = {"txtUSERID": self.userid}

        self.r = requests.post(self.fileposturl, files=self.files, data=self.data)

        results = self.r.text
        return {name: results[results.find("https://") :]}

    def upload_multiple_files(self, dict_of_files_to_upload):
        # To upload a dictionary of multiple uploads containtaining the key as a name and
        # the value as a filesystem path

        dict_to_return = {}
        for name, path in dict_of_files_to_upload.items():
            dict_to_return[name] = self.upload_file_get_link(name, path)[name]

        # Returns a dictionary where the key is the name and the value is the elog URL
        return dict_to_return

    def generate_html_doc(self, dict_for_template, templates_folder, template_file):
        # Use jinja2 templates to generate html for elog (required elog_post_template.html in special folder)

        # Capture our current directory
        THIS_DIR = templates_folder

        # Create the jinja2 environment.
        # Notice the use of trim_blocks, which greatly helps control whitespace.
        j2_env = Environment(loader=FileSystemLoader(THIS_DIR), trim_blocks=True)
        # return formatted html
        return j2_env.get_template(template_file).render(**dict_for_template)


class SlackPoster:
    def __init__(self, beamline, username, key="defaultMX", icon_emoji=":monkey_face:"):
        if key == "defaultMX":
            # Specify Slack webhook key in configuration
            key = ""
        self.url = "https://hooks.slack.com/services/%s" % (key)
        self.channel = beamline
        self.icon_emoji = icon_emoji
        self.username = "%s_%s" % (beamline, username)
        self.text = ""

    def set_payload(self):
        self.payload = {
            "channel": self.channel,
            "username": self.username,
            "text": self.text,
            "icon_emoji": self.icon_emoji,
        }

    def generate_markup_doc(self, dict_for_template, templates_folder, template_file):
        # Use jinja2 templates to generate markup for slack (required elog_post_template.html in a folder to be defined in templates folder)

        # Capture our current directory
        THIS_DIR = os.path.join(templates_folder, "/")
        # Create the jinja2 environment.
        # Notice the use of trim_blocks, which greatly helps control whitespace.
        j2_env = Environment(loader=FileSystemLoader(THIS_DIR), trim_blocks=True)
        # return formatted slack markup
        return j2_env.get_template(template_file).render(**dict_for_template)

    def post(self, text):
        self.text = text
        self.set_payload()
        return requests.post(self.url, json.dumps(self.payload))


# Example usage without the jinja templates funtion. Better if you can use the jinja2 for the formating the HTML
#
# epost = ElogPoster(beamline='MX2'
# img1 = '/data/home/blctl/Robotmountsperhour.png'
# img2 = '/data/home/blctl/Timebetweenrobotmounts.png'
# list_of_links = []
# list_of_links.append(epost.upload_file_get_link('mounts_per_hour',img1))
# list_of_links.append(epost.upload_file_get_link('time_between_mounts',img2))
# html = ' <b>Robout mounts per hour for EPN %s </b><br><img src=%s width=400> </img><br> <b> Time it took between each robot mount<br> </b> <img src=%s width=400 > </img>' %(variables.EPN,list_of_links[0]['mounts_per_hour'],list_of_links[1]['time_between_mounts'])
# epost.post(title='Testing posting Kate python',text=html)


if __name__ == "__main__":
    epost = ElogPoster(beamline="I04")
    link = epost.upload_file_get_link(
        "test",
        "/Users/smith_k/code/dls/beamline_setup/20240315/AlignBeam/beam_at_sample.png",
    )
    epost.post("test link", f"<img src={link['test']} width=400px>")
    # epost.post("test post","testing.. testing.. 1, 2, 3...")
