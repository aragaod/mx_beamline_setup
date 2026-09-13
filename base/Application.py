# Other imports
import importlib
from base.Config import Config


class Base(Config):
    def __init__(self, reload_config=True, yaml_file="default"):
        """
        Basic Application functionality for BeamlineSetup
        Here we read the configuration file (Default YAML) and import all the classes defined in config from the modules folder
        (stores them as self.__classes__) as well as instantiate those modules into instances ready for use stored under
        properties to this class under the dictionary self.MD. If config file does not define classes for all GUI objects a dummy one is setup.
        """
        # read configuration file
        self.yaml_file = yaml_file
        Config.__init__(self, reload_config=reload_config, yaml_file=self.yaml_file)
        print(
            f"Loaded configuration for Application using config file: {self.yaml_file}"
        )  # FIXME so LOG works here
        # Import modules from config file. If module file in folder modules/ does not exist load basic from base/Modules.py
        self.import_modules()

    def import_modules(self):
        # This should import the different modules as a attribute to the main class
        self.__classes__ = {}
        print(
            f"Modules to load are {list(self.config['modules'].keys())}"
        )  # FIXME so that logging works here instead
        for item in self.config["modules"]:
            self.log.debug(f"{item}:")
            try:
                self.log.debug(f"Trying to load {item}")
                # importing a class with name of item from a file named item inside a folder called /modules/
                self.log.debug(f"modules.{item}")
                self.__classes__[item] = importlib.import_module(
                    f"modules.{item}.{item}"
                )
                self.log.debug(f"Loaded {self.__classes__[item]}")
                self.__classes__[f"{item}_CL"] = getattr(self.__classes__[item], item)
                self.log.debug(f"Loaded {item} class inside .py")
                # Now create an instance of that class
                self.log.debug(
                    f"Instantiating next: class {item} has instance {item}_MD"
                )
                if self.config["modules"][item]["needs_folder_to_write"]:
                    self.log.debug(
                        f"{item}_MD: Oh needs a folder to write as set in config file"
                    )
                setattr(
                    self,
                    f"{item}_MD",
                    self.__classes__[f"{item}_CL"](
                        needs_folder_to_write=self.config["modules"][item][
                            "needs_folder_to_write"
                        ],
                        yaml_file=self.yaml_file,
                    ),
                )
                # setattr(self,f'{item}_MD',self.__classes__[f'{item}_CL'](needs_folder_to_write=True))

            except Exception as e:
                print(
                    f"Fix the issue with the module that failed to load: {item}  with error {e}"
                )
                import sys

                sys.exit()
                self.import_dummy()

    def import_dummy(self):
        # import code
        # code.interact(local = locals())

        # Importing a class with name 'Base' from a file named Modules.py inside a folder called base
        self.__classes__["MOD_Base"] = importlib.import_module(f"base.Modules")
        self.__classes__[f"MOD_Base_CL"] = getattr(self.__classes__["MOD_Base"], "Base")
        setattr(self, f"{item}_MD", self.__classes__[f"MOD_Base_CL"](default_name=item))

        # Get the log for the correct class
        new_item = getattr(self, f"{item}_MD")
        # Get the log instance for the correct class
        new_item_log = getattr(new_item, "log")
        # print(new_item_log)
        # Send the log with the correct class that is being instantiated
        getattr(new_item_log, "warning")(
            f"Instantiated class Basic module instead and now we have instance {item}_MD"
        )
