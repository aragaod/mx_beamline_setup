# Config loader
# If changing from yaml to json or pickle function load_config needs changing as well
import yaml as config_loader

import logging
from logging.config import dictConfig

from beamline import ID
from beamline import redis

# import json as serialiser
import pickle as serialiser

from datetime import datetime


class Config(object):
    def __init__(self, reload_config=True, default_name=True, yaml_file="default"):
        # Setup Beamline
        self.ID = ID

        # Setting up loging with default class name or manually set name
        if default_name == True:
            self.log = logging.getLogger(self.__class__.__name__)
        else:
            self.log = logging.getLogger(default_name)

        # Read configuration from file
        if yaml_file == "default":
            self.log.debug("Getting default YAML configuration")
            config = "configure_blsetup.yaml"
        else:
            self.log.debug(f"Getting special YAML configuration: {yaml_file}")
            config = yaml_file

        self.log.debug(f"Configuration file set to: {config}")

        self.config = self.load_config(config)

        # Giving access to all subclasses to the redis database
        # Setting up redis database
        self.redis_hash = self.config["redis_hash"]["key"].format(BEAMLINE=self.ID)
        self.redis_expiry = self.config["redis_hash"]["expiry"]
        self.names = set(self.config["modules"].keys())
        self.nx_machines = self.config["nx_machines"][self.ID]

        # Load/Not load logging configuration
        if reload_config is not False:
            dictConfig(self.config["logging"])

    # -- the on-call log (F2) ---------------------------------------------
    #
    # This lives on Config rather than on a Base class because *both* of them
    # need it and they are siblings: base/Modules.py:Base is what modules
    # inherit, base/Application.py:Base is what the main window inherits, and
    # neither can see the other's methods. Putting it on the module Base meant
    # the main window crashed on startup the first time it was run -
    # `'BL_MainWindow' object has no attribute 'record_oncall'` - because that is
    # where the session-start timestamp is taken.
    #
    # Config is the right home anyway: it already owns the redis handle and the
    # beamline ID, and this is redis bookkeeping.

    ONCALL_KEY_SUFFIX = "BeamlineSetup:oncall"
    ONCALL_EXPIRY_SECONDS = 365 * 24 * 60 * 60

    def oncall_key(self):
        """The on-call hash, following the report hash into development.

        The report hash gets a `:dev` suffix from the development config so a
        debug run cannot touch production data. The on-call log has to honour the
        same split or testing the app would write test entries into the record
        someone claims overtime from - so the suffix is taken from whatever the
        report hash is actually using rather than assumed.
        """
        key = f"{self.ID}:{self.ONCALL_KEY_SUFFIX}"
        report_hash = getattr(self, "redis_hash", "") or ""
        if report_hash.endswith(":dev"):
            key += ":dev"
        return key

    def record_oncall(self, field, value, username=None, date=None):
        """Note one fact about today's setup session, for the overtime report.

        Staff claiming weekend overtime currently have to remember which days
        they were Local Contact. Two timestamps make that unnecessary: when the
        session was started and when the eLog post went out. Weekdays are recorded
        as well - useful for workload and fairness - but only weekends feed the
        claim.

        Kept deliberately small and append-only: one hash field per person per
        day, holding a dictionary. Nothing here should ever fail a setup, so any
        error is logged and swallowed.
        """
        try:
            from beamline import redis as redis_client

            username = username or getattr(self, "username", None) or "unknown"
            date = date or datetime.now().strftime("%Y%m%d")
            key = self.oncall_key()
            field_name = f"{date}_{username}"

            existing = redis_client.hget(key, field_name)
            try:
                entry = config_loader.safe_load(existing) if existing else None
            except config_loader.YAMLError:
                # A corrupt entry must not cost the day it was meant to record.
                entry = None
            if not isinstance(entry, dict):
                entry = {"date": date, "username": username}

            entry[field] = value
            entry.setdefault(
                "weekend", datetime.strptime(date, "%Y%m%d").weekday() >= 5
            )

            redis_client.hset(key, field_name, config_loader.safe_dump(entry))
            redis_client.expire(key, self.ONCALL_EXPIRY_SECONDS)
            self.log.debug(f"On-call log: {field_name} {field}={value}")
            return entry
        except Exception as error:
            # Never let bookkeeping break a setup.
            self.log.warning(f"Could not write the on-call log: {error}")
            return None

    def load_config(self, file):
        # Load config. TODO: not totally abstracted from yaml as we need to tell the yaml.loader. If changed to pickle,json code needs changing here
        self.log.debug(f"Loading configuration file from {file}")
        return config_loader.load(open(file, "r"), Loader=config_loader.FullLoader)

    def set(self, key, value):
        redis.hset(self.redis_hash, key, serialiser.dumps(value))
        self.set_redis_expiry()

    def get(self, key):
        try:
            return serialiser.loads(redis.hget(self.redis_hash, key))
        except Exception as e:
            self.log.warning(f"Could not get value for key {key}")
            return False

    def set_redis_expiry(self):
        return redis.expire(self.redis_hash, self.redis_expiry)

    def is_any_module_running(self):
        try:
            status = self.get("module_running")
        except TypeError:
            self.log.debug(
                "redis hash key for checking if modules are running does not exist. creating one as False"
            )
            self.set("module_running", False)

        return self.get("module_running")

    def get_all(self):
        dict_store = {}
        payload = redis.hgetall(self.redis_hash)
        for elem in payload.keys():
            self.log.debug(elem.decode())
            dict_store[elem.decode()] = self.get(elem)
        return dict_store

    def delete_redis_key(self):
        redis.delete(self.redis_hash)

    def get_previous_report_data(self, module_name):
        """
        Finds the most recent report for a given module from a previous day.
        """
        try:
            # redis-py returns byte strings, so we need to decode them
            all_keys = [k.decode("utf-8") for k in redis.hkeys(self.redis_hash)]
            today_str = datetime.now().strftime("%Y%m%d")

            report_keys = []
            for key in all_keys:
                if key.startswith(f"{module_name}_report_") and not key.endswith(
                    today_str
                ):
                    report_keys.append(key)

            if not report_keys:
                self.log.info(f"No previous reports found for module '{module_name}'.")
                return None

            # Sort keys alphabetically/chronologically to find the most recent
            report_keys.sort(reverse=True)
            latest_key = report_keys[0]

            self.log.info(
                f"Found previous report for '{module_name}' under key: {latest_key}"
            )

            # Use the existing self.get() method, which handles deserialization
            return self.get(latest_key)

        except Exception as e:
            self.log.error(f"Error getting previous report for '{module_name}': {e}")
            return None
