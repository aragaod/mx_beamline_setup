from base import MOD_Base


class TestStream(MOD_Base):
    def __init__(self, needs_folder_to_write=False):
        MOD_Base.__init__(self, needs_folder_to_write)
        self.log.info(f"Loading {self.class_name}_MD module/instance")

        # Define the widget type to update when finalised with the job
        # self.widget2update = 'CB' # THIS HAS BEEN MOVED TO THE CONFIGURATION FILE

    def run(self):
        """
        Base Modules classe run method is overwritten here by this run method.
        """
        if self.before():
            self.set_running()
            self.log.debug(
                f"Trying to trigger run method on {self.class_name} module class. To be coded"
            )
            import time

            time.sleep(5)
            self.set_stopped()
        else:
            return False
        # Here some code just assess if this task ran successfully and set status to True/False
        status = True
        if status == False:
            self.set(f"{self.class_name}_status", status)
        return status
