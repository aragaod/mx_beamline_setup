from base import MOD_Base


class Close(MOD_Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.log.info(f"Loading Close_MD module/instance")

    def run(self):
        """
        Run method for close class. This overwrites the MOD_Base upstream run method
        """

        # Log
        self.log.debug(
            "Close button has been pressed. I could gather and store some information if I wish here. Look for Close.py module"
        )

        # Not doing anything. At least store the date the BL was closed although the date of the post to elog and email to users is more important
        self.gather_data()

        # The update widget function is attached to this module on the beamline_setup.py. It is not inherited.
        # The update on the case of the Close button is to kill the app while on other buttons might be to click a CB or a update the date on a DE
        self.update_widget(task=self.class_name, status=2, value="current")

        return True

    def gather_data(self):
        pass
