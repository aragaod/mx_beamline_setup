import yaml as config_loader
from base import Config
import json, re
from pprint import pprint
import os
import shutil
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Shared assessment engine
#
# Every module used to carry its own copy of the dispatcher that turns
# `assessment_rules` from a module YAML into good/warning/danger. The four
# copies disagreed with each other: `range` in one and `in_range` in another for
# the same helper, four different behaviours for an unknown check type, three
# policies for what to do with no previous report, and one module that
# reimplemented the deadband comparison inline. A rule naming a check type its
# own module did not implement was a silent no-op.
#
# Everything below is that dispatcher, once. Two rules it must keep:
#
#   * A configuration mistake must never look like a beamline fault. Previously
#     a malformed `limits` raised ValueError inside a helper and was caught by a
#     blanket `except`, which returned "danger" - indistinguishable from a real
#     alarm, and the reason the flux check read red for 201 consecutive setups.
#     Bad configuration now returns no status at all, plus a loud log line.
#   * Not being able to assess is not the same as passing. No previous report
#     means no status, not "good".
# ---------------------------------------------------------------------------


# Stamped into every report written from now on. Analysis code should branch on
# this rather than on a remembered deployment date - i04 and i04-1 will not deploy
# on the same day, so a date in a comment would be wrong for one of them.
#
#   (absent) legacy. Feedback_good held only XBPM2; Rmerge and Aimless_Rmeas
#            carried no _low_res suffix; numeric PVs were stored as display
#            strings, so their precision is gone and cannot be recovered.
#   1        the same reports after the migration tool in dev/ renames the keys
#            and converts numbers to floats. Fields that never existed stay
#            absent, so a reader must tolerate missing keys.
#   2        written by this version of the application: full precision, the
#            per-image and identity fields, and hidden parameters.
REPORT_FORMAT_VERSION = 2


def _ascending(limits):
    """good <= warning, e.g. less_than and the deadband family."""
    return limits[0] <= limits[1]


def _descending(limits):
    """good >= warning, e.g. greater_than."""
    return limits[0] >= limits[1]


def _range_ordered(limits):
    """[good_min, good_max, warn_min, warn_max] with the warning band outside."""
    good_min, good_max, warn_min, warn_max = limits
    return warn_min <= good_min <= good_max <= warn_max


def _fmt(value):
    """Compact number for the criterion column: 9e+11, 0.03, 30, 1e-05."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != 0 and (abs(number) >= 1e5 or abs(number) < 1e-3):
        return f"{number:.3g}"
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


# name -> how many limits, how they must be ordered, and how to describe the rule
# in the report. `needs_previous` marks the checks that compare with yesterday.
CHECK_SPECS = {
    "greater_than": {
        "n_limits": 2,
        "order": _descending,
        "order_text": "good limit must be >= warning limit",
        "criterion": lambda r: f">= {_fmt(r['limits'][0])}",
    },
    "less_than": {
        "n_limits": 2,
        "order": _ascending,
        "order_text": "good limit must be <= warning limit",
        "criterion": lambda r: f"<= {_fmt(r['limits'][0])}",
    },
    "in_range": {
        "n_limits": 4,
        "order": _range_ordered,
        "order_text": "must be [good_min, good_max, warn_min, warn_max] with the "
        "warning band enclosing the good band",
        "criterion": lambda r: f"{_fmt(r['limits'][0])}-{_fmt(r['limits'][1])}",
    },
    "equals": {
        # `mismatch_status` chooses what a mismatch means. It defaults to danger,
        # which is right for a feedback loop that is off. Some equality checks are
        # not alarms though - a test sample the registry does not recognise is
        # something to fix in configuration, not a fault on the beamline - so those
        # rules set it to "warning" and stay visible without crying wolf.
        "n_limits": 0,
        "needs_good_value": True,
        "criterion": lambda r: f"= {r.get('good_value')}",
    },
    "equals_previous": {
        "n_limits": 0,
        "needs_previous": True,
        "criterion": lambda r: "= yesterday",
    },
    "deadband_absolute": {
        "n_limits": 2,
        "order": _ascending,
        "order_text": "good limit must be <= warning limit",
        "needs_previous": True,
        # A zero good-limit is not a tolerance, it is change detection, and
        # saying "delta <= 0" instead of "= yesterday" makes the machine steering
        # rows read like a rounding statement.
        "criterion": lambda r: (
            "= yesterday"
            if float(r["limits"][0]) == 0
            else f"delta <= {_fmt(r['limits'][0])} vs yest"
        ),
    },
    "deadband_percent": {
        "n_limits": 2,
        "order": _ascending,
        "order_text": "good limit must be <= warning limit",
        "needs_previous": True,
        "criterion": lambda r: (
            "= yesterday"
            if float(r["limits"][0]) == 0
            else f"delta <= {_fmt(r['limits'][0])}% vs yest"
        ),
    },
    "time_since": {
        "n_limits": 2,
        "order": _ascending,
        "order_text": "warning limit must be <= danger limit",
        "criterion": lambda r: f"< {_fmt(r['limits'][0])} h ago",
    },
    "abs_limit_and_change": {
        # V4: an absolute ceiling on |value| combined with change detection.
        # good  = unchanged since yesterday and within the good limit
        # warn  = changed, but still below the danger limit
        # danger= |value| >= danger limit, whether or not it changed
        "n_limits": 2,
        "order": _ascending,
        "order_text": "good limit must be <= warning limit",
        "needs_previous": True,
        "criterion": lambda r: (
            f"|v| <= {_fmt(r['limits'][0])}, = yest"
            + (
                f" (default {_fmt(r['default'])})"
                if r.get("default") is not None
                else ""
            )
        ),
    },
    "custom_flux": {
        "n_limits": 2,
        "order": _ascending,
        "order_text": "good limit must be <= warning limit",
        "needs_previous": True,
        "criterion": lambda r: f"delta <= {_fmt(r['limits'][0])}% vs yest, at 100% trans",
    },
    "custom_slits": {
        "n_limits": 2,
        "order": _descending,
        "order_text": "good limit must be >= danger limit",
        "criterion": lambda r: f">= {_fmt(r['limits'][0])}",
    },
}

# Spellings that mean the same check. `range` was AlignBeam's name for what
# RotationAxis called `in_range`; both are accepted so neither YAML has to change.
CHECK_ALIASES = {"range": "in_range", "less_than_abs": "abs_limit_and_change"}


class Base(Config):
    def __init__(
        self,
        needs_folder_to_write=False,
        reload_config=False,
        default_name=True,
        yaml_file="default",
    ):
        Config.__init__(self, reload_config, default_name, yaml_file)

        if default_name == True:
            self.class_name = self.__class__.__name__
            self.log.debug(f"Keeping default name as {self.class_name}")
        else:
            self.class_name = default_name

        self.needs_folder = needs_folder_to_write

        # Defined the widget type to update when finalised with the job
        try:
            #            if self.class_name in ["SampleLoad"]:
            #                pprint(self.config["modules"])

            self.widget2update = self.config["modules"][self.class_name][
                "widget2update"
            ]
        except Exception as e:
            self.log.warning(
                f"Failed to obtained widget2update for {self.class_name} with error {e}. Setting it to UNK"
            )
            self.widget2update = "UNK"
        try:
            self.criteria2expire = self.config["modules"][self.class_name][
                "criteria2expire"
            ]
        except Exception as e:
            self.log.warning(
                f"Failed to get criteria2expire for {self.class_name} with error {e}. Going to set it to 0 seconds"
            )
            self.criteria2expire = [0, "second"]

    def load_config(self, file):
        # Load config. TODO: not totally abstracted from yaml as we need to tell the yaml.loader. If changed to pickle,json code needs changing here
        return config_loader.load(open(file, "r"), Loader=config_loader.FullLoader)

    def before(self):
        if self.needs_folder:
            result = self.check_folder_is_setup()
            if not result:
                # if check_folder_is_setup is False (failed) then throw failure and stop here
                return False

        if self.get("module_running"):
            self.log.warning(
                "Cannot start a job because another already running. If you sure nothing is running you can cd /dls/science/groups/i04/Python/applications/beamline_setup/dev and run ./delete_running.sh twice"
            )
            return False
        else:
            return True

    def check_folder_is_setup(self):
        try:
            directories = self.get("directories")
        except:
            directories = {}
            self.set("directories", directories)
            self.log.warning(f"Directories have not been stored in redis")
            self.log.warning(
                f"Can't run {self.class_name} task because folders have not been setup first"
            )
            return False

        if directories.get(self.class_name):
            self.log.debug(f"Ok. We have setup a folder for {self.class_name}")
            return True
        else:
            self.log.warning(f"Needs folder setup. Run Create directories first")
            return False

    def run(self):
        """
        Basic run method that is called by clicking the respective module button.
        This method calls a GUI if the method exists. Create a launch_GUI method on the inherited respective module class if you wish this.
        """
        if self.before():
            self.set_running()
            try:
                self.log.debug(
                    f"Trying to trigger run method on {self.class_name} module class"
                )

                # Launch module new window if any. Won't work if module class has not overwritten the launch_GUI function
                self.launch_GUI()
                self.log.debug("GUI launched")

            except Exception as e:
                self.log.critical(f"Failed with error {e}")
            finally:
                self.set_stopped()
                return True
        else:
            return False

    def set_running(self):
        self.set("module_running", True)
        self.set(f"{self.class_name}_running", True)

    def set_stopped(self):
        self.set("module_running", False)
        self.set(f"{self.class_name}_running", False)

    def set_status(self, status=True):
        """
        Updated the check box or date with succesfully delivered the result of the module
        """
        self.status = status
        self.log.debug(f"STATUS IS: {self.status}")
        self.set(f"{self.class_name}_status", status)

        if status == True:
            CB = 2
        elif status == False:
            CB = 0
        else:
            CB = 1
        # The update widget function is added to this module on the beamline_setup.py. It is not inherited.
        self.update_widget(task=self.class_name, status=CB, value="current")

        # print(f'STATUS IS: {self.status}')
        return status

    def set_status_true(self):
        return self.set_status(True)

    def set_status_false(self):
        return self.set_status(False)

    def launch_GUI(self):
        """
        This function needs to be overwritten to launch a new GUI for that particular module. If the module does not have a GUI this is just a place holder and will do nothing
        """
        pass

    # The on-call log lives in its own redis key with its own expiry, because a
    # monthly overtime claim needs the record to outlive the 60 days the main
    # report hash keeps. One year, so a claim cycle can never outrun it.
    def displace_existing(self, destination):
        """Rename anything already at `destination` so it is not lost.

        Split out of `store_versioned` because not every module copies a finished
        image into place - `TestCrystal` builds its montage **directly at the
        final path**, and `SampleLoad` and `BeamstopAlignment` write theirs the
        same way. Those three were not covered by B6 at all, so a second run
        overwrote the first run's image, which is exactly the image worth keeping:
        the reason for re-running is usually that something was wrong.

        The archived name carries the time the displaced file was *written*, not
        now, so the name says when the image was made.
        """
        if not os.path.exists(destination):
            return None
        stem, extension = os.path.splitext(destination)
        written = datetime.fromtimestamp(os.path.getmtime(destination))
        archived = f"{stem}_{written.strftime('%H%M%S')}{extension}"
        counter = 2
        while os.path.exists(archived):
            archived = f"{stem}_{written.strftime('%H%M%S')}_{counter}{extension}"
            counter += 1
        os.rename(destination, archived)
        self.log.info(f"Kept the previous image as {os.path.basename(archived)}")
        return archived

    def store_versioned(self, source, destination, group="mx_staff"):
        """Copy an image into the report folder without destroying the last one.

        Image filenames are fixed per module - beam_at_sample.png,
        rotationaxis_montage.png - so running a module twice in a day used to
        overwrite the first run's image with the second. That matters because the
        reason for re-running is usually that something was wrong the first time,
        which is exactly the image worth keeping.

        The canonical name always holds the newest, so the report and the eLog
        upload need no changes. Anything displaced is renamed with the time it
        was written - taken from the file itself, not from now, so the name says
        when the image was made rather than when it was pushed aside.
        """
        try:
            self.displace_existing(destination)

            shutil.copy2(source, destination)
            shutil.chown(destination, group=group)
            self.log.info(f"Storing image {source} to {destination}")
            return destination
        except Exception as error:
            self.log.critical(f"Could not copy image to {destination}: {error}")
            return None

    def store_report(self, payload, module_name=None):
        """Write today's report for this module, stamped with the format version.

        Replaces four hand-built keys that disagreed about their own date: some
        modules kept `self.now` as a preformatted string and others as a datetime,
        so the same expression worked in one module and raised in another. Taking
        the date here means a module cannot get it wrong, and gives one place to
        stamp the format version.
        """
        name = module_name or self.class_name
        key = f"{name}_report_{datetime.now().strftime('%Y%m%d')}"
        stamped = dict(payload)
        stamped["format_version"] = REPORT_FORMAT_VERSION
        self.set(key, stamped)
        self.log.info(f"Storing data for report under redis hash key {key}")
        return key

    def _get_previous_report_data(self):
        """A helper method to easily get the last report data for the current module."""
        return self.get_previous_report_data(self.class_name)

    def assess_threshold(self, value, limits, check_type="greater_than"):
        """
        Generic assessment based on thresholds.

        Args:
            value (float): The value to check.
            limits (list): A list of two thresholds [warning_limit, danger_limit].
            check_type (str): 'greater_than' (good if >) or 'less_than' (good if <).

        Returns:
            str: 'good', 'warning', or 'danger'.
        """
        try:
            value = float(value)
            warn_lim, danger_lim = limits

            if check_type == "greater_than":
                if value < danger_lim:
                    return "danger"
                if value < warn_lim:
                    return "warning"
                return "good"
            elif check_type == "less_than":
                if value > danger_lim:
                    return "danger"
                if value > warn_lim:
                    return "warning"
                return "good"
            else:
                return None  # Default, no status
        except (ValueError, TypeError):
            return "danger"  # If value isn't a number, it's a problem

    def assess_deadband(
        self, current_value, previous_value, limits, check_type="percent"
    ):
        """
        Compares a value to a previous value and checks if it's outside a deadband.

        Args:
            limits (list): [good_threshold, warning_threshold]
            check_type (str): 'percent' or 'absolute'
        """
        if previous_value is None:
            return None  # Cannot assess if there's no previous value

        try:
            current = float(current_value)
            previous = float(previous_value)
            good_lim, warn_lim = limits

            if check_type == "percent":
                if previous == 0:
                    # Avoid division by zero, check for absolute change instead
                    change = abs(current)
                else:
                    change = (abs(current - previous) / abs(previous)) * 100
            else:  # absolute
                change = abs(current - previous)

            if change <= good_lim:
                return "good"
            if change <= warn_lim:
                return "warning"
            return "danger"
        except (ValueError, TypeError, ZeroDivisionError):
            return "danger"

    def assess_greater_than(self, value, limits):
        """
        Assesses if a value is good/warning/danger based on being 'greater than' thresholds.

        Args:
            value (float): The value to check.
            limits (list): A list of two thresholds [good_limit, warning_limit].

        Returns:
            str: 'good', 'warning', or 'danger'.
        """
        try:
            value = float(value)
            good_lim, warn_lim = limits

            if value >= good_lim:
                return "good"
            if value >= warn_lim:
                return "warning"
            return "danger"
        except (ValueError, TypeError):
            return "danger"

    def assess_less_than(self, value, limits):
        """
        Assesses if a value is good/warning/danger based on being 'less than' thresholds.
        """
        try:
            value = float(value)
            good_lim, warn_lim = limits

            if value <= good_lim:
                return "good"
            if value <= warn_lim:
                return "warning"
            return "danger"
        except (ValueError, TypeError):
            return "danger"

    def assess_in_range(self, value, limits):
        """
        Assesses if a value is good/warning/danger based on being within a range.
        - good: good_min <= value <= good_max
        - warning: warn_min <= value < good_min OR good_max < value <= warn_max
        - danger: value < warn_min OR value > warn_max
        """
        try:
            value = float(value)
            good_min, good_max, warn_min, warn_max = limits

            if good_min <= value <= good_max:
                return "good"
            if warn_min <= value <= warn_max:
                return "warning"
            return "danger"
        except (ValueError, TypeError):
            return "danger"

    def assess_equals(self, value, good_value):
        """
        Assesses if a value is equal to a specific required value.
        Tries to compare as floats first, falls back to string comparison.
        """
        try:
            if float(value) == float(good_value):
                return "good"
            else:
                return "danger"
        except (ValueError, TypeError):
            # Fallback to string comparison if not a number
            if str(value).strip() == str(good_value).strip():
                return "good"
            else:
                return "danger"

    def assess_equals_previous(self, current_value, previous_value):
        """
        Assesses if a value is the same as the previous report's value.
        """
        if previous_value is None:
            return None  # Cannot assess

        # Compare as numbers when both sides are numbers, and only fall back to
        # text otherwise. A string comparison alone reports a change whenever the
        # two sides are merely written differently - "-0.00006" against -6e-05 is
        # the same gain, but not the same string. That matters on the first run
        # after any change to how a value is stored, and it is why the sibling
        # assess_equals has always tried float() first.
        try:
            return (
                "good" if float(current_value) == float(previous_value) else "warning"
            )
        except (TypeError, ValueError):
            pass

        if str(current_value).strip() == str(previous_value).strip():
            return "good"
        else:
            return "warning"

    # -- shared assessment engine (see CHECK_SPECS at the top of this module) --

    def resolve_check_type(self, check_type):
        """Map a YAML spelling onto a canonical check name, or None if unknown."""
        canonical = CHECK_ALIASES.get(check_type, check_type)
        return canonical if canonical in CHECK_SPECS else None

    def validate_assessment_rule(self, name, rule):
        """Return a list of problems with one rule. Empty list means it is usable.

        This exists because a malformed rule used to be indistinguishable from a
        beamline fault: `good, warn = limits` on a one-element list raised
        ValueError, the helper's blanket except turned that into "danger", and
        nothing was logged. Checking up front means we can report the parameter
        as unassessed and say why.
        """
        problems = []
        raw_type = rule.get("check_type")
        if raw_type is None:
            return [f"{name}: no check_type"]

        check_type = self.resolve_check_type(raw_type)
        if check_type is None:
            return [
                f"{name}: unknown check_type {raw_type!r} "
                f"(known: {', '.join(sorted(CHECK_SPECS))})"
            ]

        spec = CHECK_SPECS[check_type]
        limits = rule.get("limits", [])
        expected = spec["n_limits"]

        if expected:
            if not isinstance(limits, (list, tuple)) or len(limits) != expected:
                problems.append(
                    f"{name}: {raw_type} needs {expected} limits, got {limits!r}"
                )
            else:
                try:
                    numeric = [float(v) for v in limits]
                except (TypeError, ValueError):
                    problems.append(f"{name}: limits are not all numbers: {limits!r}")
                else:
                    if "order" in spec and not spec["order"](numeric):
                        problems.append(
                            f"{name}: limits {limits!r} out of order - "
                            f"{spec['order_text']}"
                        )

        if spec.get("needs_good_value") and rule.get("good_value") is None:
            problems.append(f"{name}: {raw_type} needs a good_value")

        return problems

    def validate_assessment_rules(self, rules, where=""):
        """Validate a whole assessment_rules block. Returns {name: [problems]}."""
        broken = {}
        for name, rule in (rules or {}).items():
            problems = self.validate_assessment_rule(name, rule or {})
            if problems:
                broken[name] = problems
                for problem in problems:
                    self.log.error(f"Assessment rule error {where}: {problem}")
        return broken

    def describe_criterion(self, rule):
        """Short human-readable form of a rule, for the report's criterion column."""
        check_type = self.resolve_check_type(rule.get("check_type"))
        if check_type is None:
            return ""
        try:
            return CHECK_SPECS[check_type]["criterion"](rule)
        except Exception as error:  # a malformed rule should never break the report
            self.log.warning(f"Could not describe criterion for {rule!r}: {error}")
            return ""

    def assess_abs_limit_and_change(self, value, previous_value, limits):
        """V4: absolute ceiling on |value|, combined with change detection.

        danger  |value| >= the warning limit, regardless of any change
        warning changed since the previous report but still under that limit
        good    unchanged and within the good limit
        """
        try:
            magnitude = abs(float(value))
            good_limit, danger_limit = float(limits[0]), float(limits[1])
        except (TypeError, ValueError, IndexError):
            return None

        if magnitude >= danger_limit:
            return "danger"

        changed = None
        if previous_value is not None:
            try:
                changed = float(value) != float(previous_value)
            except (TypeError, ValueError):
                changed = str(value).strip() != str(previous_value).strip()

        if magnitude > good_limit:
            return "warning"
        if changed:
            return "warning"
        return "good"

    def assess_one(self, value, rule, previous_value=None):
        """Apply a single validated rule. Returns 'good'/'warning'/'danger' or None.

        None means "not assessed" - no previous report to compare against, or a
        value that is not there. It never means "passed".
        """
        check_type = self.resolve_check_type(rule.get("check_type"))
        if check_type is None:
            return None

        limits = rule.get("limits", [])
        spec = CHECK_SPECS[check_type]

        if spec.get("needs_previous") and previous_value is None:
            return None

        if check_type == "greater_than":
            return self.assess_greater_than(value, limits)
        if check_type == "less_than":
            return self.assess_less_than(value, limits)
        if check_type == "in_range":
            return self.assess_in_range(value, limits)
        if check_type == "equals":
            status = self.assess_equals(value, rule.get("good_value"))
            if status == "danger":
                return rule.get("mismatch_status", "danger")
            return status
        if check_type == "equals_previous":
            return self.assess_equals_previous(value, previous_value)
        if check_type == "deadband_absolute":
            return self.assess_deadband(value, previous_value, limits, "absolute")
        if check_type == "deadband_percent":
            return self.assess_deadband(value, previous_value, limits, "percent")
        if check_type == "time_since":
            return self.assess_time_since(
                value,
                limits,
                format=rule.get("format", "%Y-%m-%d %H:%M"),
                unit=rule.get("unit", "hours"),
            )
        if check_type == "abs_limit_and_change":
            return self.assess_abs_limit_and_change(value, previous_value, limits)
        if check_type == "custom_slits":
            value_status = self.assess_greater_than(value, limits)
            change_status = self.assess_equals_previous(value, previous_value)
            if value_status == "danger":
                return "danger"
            if value_status == "warning" or change_status == "warning":
                return "warning"
            return "good"
        # custom_flux needs two parameters at once, so it is handled by the caller.
        return None

    @staticmethod
    def _plain_value(entry):
        """Reports store either a bare value or {'value': ..., 'status': ...}."""
        if isinstance(entry, dict):
            return entry.get("value")
        return entry

    def assess_parameters(
        self, raw_params, rules, previous_params=None, where="", hidden=None
    ):
        """Assess a whole parameter dictionary against a rules block.

        Returns {name: {'value': ..., 'status': ..., 'criterion': ...}}. A rule
        that fails validation leaves the parameter without a status and adds a
        'note' saying why, so a configuration error is visibly not an alarm.

        `hidden` names parameters that are stored but not shown. Everything
        written to redis used to be rendered into the report table and posted to
        the eLog, so there was no way to record something for later analysis
        without putting it in front of staff every morning. A hidden parameter is
        still stored, still assessed and still logged - it is only kept out of the
        rendered table.
        """
        structured = {key: {"value": value} for key, value in raw_params.items()}
        previous_params = previous_params or {}
        rules = rules or {}

        broken = self.validate_assessment_rules(rules, where=where or self.class_name)

        for name, rule in rules.items():
            if name not in structured:
                continue
            if name in broken:
                structured[name]["note"] = "; ".join(broken[name])
                continue

            value = structured[name]["value"]
            previous_value = self._plain_value(previous_params.get(name))
            status = self.assess_one(value, rule, previous_value)

            if status is not None:
                structured[name]["status"] = status
            elif CHECK_SPECS[self.resolve_check_type(rule["check_type"])].get(
                "needs_previous"
            ):
                structured[name]["note"] = "no previous report to compare against"

            criterion = self.describe_criterion(rule)
            if criterion:
                structured[name]["criterion"] = criterion

        # The report shows `display`; `value` stays raw so tomorrow's comparison
        # is made against the full-precision reading.
        for entry in structured.values():
            entry["display"] = self.format_value(entry["value"])

        for name in hidden or []:
            if name in structured:
                structured[name]["hidden"] = True
            else:
                self.log.warning(
                    f"{where or self.class_name}: hidden_parameters names "
                    f"{name!r}, which this module does not produce"
                )

        return structured

    def format_value(self, value, significant_figures=6):
        """Render a value for the report without losing what it means.

        Numeric PVs are read raw so that comparisons with yesterday see the
        number the IOC holds, not the rounded number the EDM screen shows. Raw
        floats are unreadable in a report though - a transmission of exactly 20%
        arrives as 19.999984741210938 - so the stored value stays raw and this
        produces the version staff see. Six significant figures is enough to keep
        a gain of 0.000108 distinct from 0.00011 while turning that transmission
        back into "20".
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        if isinstance(value, int):
            return str(value)
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        return f"{value:.{significant_figures}g}"

    def format_scientific(self, value, precision=2):
        """Formats a float into scientific notation with a given precision."""
        try:
            return f"{float(value):.{precision}e}"
        except (ValueError, TypeError):
            return str(value)

    def check_file_age(self, file_path, max_age_config):
        """
        Checks if a file is older than a duration specified in a config dictionary.

        Args:
            file_path (str): The full path to the file.
            max_age_config (dict): A dictionary, e.g., {'unit': 'hours', 'value': 12}
        """
        if not os.path.exists(file_path):
            self.log.warning(f"File not found for age check: {file_path}")
            return False

        try:
            # Extract unit and value from the config, with safe defaults
            unit = max_age_config.get("unit", "hours").lower()
            value = max_age_config.get("value", 12)

            # Create a timedelta object based on the unit
            if "day" in unit:
                max_age = timedelta(days=value)
            elif "hour" in unit:
                max_age = timedelta(hours=value)
            elif "minute" in unit:
                max_age = timedelta(minutes=value)
            elif "second" in unit:
                max_age = timedelta(seconds=value)
            else:
                self.log.warning(f"Unknown time unit '{unit}'. Defaulting to hours.")
                max_age = timedelta(hours=value)

            file_mod_time = os.path.getmtime(file_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_mod_time)

            self.log.info(
                f"Checking age of {os.path.basename(file_path)}. Age: {file_age}, Max allowed: {max_age}"
            )

            if file_age > max_age:
                self.log.warning(
                    f"File {os.path.basename(file_path)} is older than {value} {unit}!"
                )
                return False  # File is too old
            else:
                self.log.info(f"File {os.path.basename(file_path)} is recent enough.")
                return True  # File is recent

        except Exception as e:
            self.log.error(f"Could not check file age for {file_path}: {e}")
            return False

    def check_age_from_filename(self, filename, max_age_config):
        """
        Parses a YYYYMMDD date string from a filename and checks if it's too old,
        using a configurable unit of time (days, hours, etc.).
        """
        match = re.search(r"(\d{8}T\d{6})", filename)
        if not match:
            self.log.warning(
                f"Could not find a YYYYMMDDTHHMMSS date stamp in filename: {filename}"
            )
            return False

        try:
            datetime_str = match.group(1)
            file_datetime = datetime.strptime(datetime_str, "%Y%m%dT%H%M%S")
            file_age = datetime.now() - file_datetime

            unit = max_age_config.get("unit", "hours").lower()
            value = max_age_config.get("value", 12)

            if "day" in unit:
                max_age = timedelta(days=value)
            elif "hour" in unit:
                max_age = timedelta(hours=value)
            elif "minute" in unit:
                max_age = timedelta(minutes=value)
            else:  # Default to hours if unit is unknown
                max_age = timedelta(hours=value)

            self.log.info(
                f"Checking date in filename '{filename}'. Age: {file_age}, Max allowed: {max_age}"
            )

            if file_age > max_age:
                self.log.warning(f"Image file {filename} is older than {value} {unit}!")
                return False

            return True

        except (ValueError, TypeError) as e:
            self.log.error(f"Error processing date from filename '{filename}': {e}")
            return False

    def assess_time_since(self, value, limits, format="%Y-%m-%d %H:%M", unit="hours"):
        """
        Assesses if a timestamp string is older than limits.
        value: Date string (e.g. "2025-12-17 12:00")
        limits: [warning_limit, danger_limit]
        format: Format of the date string
        """
        try:
            # Handle cases where value might be empty or None
            if not value:
                return "danger"

            event_time = datetime.strptime(str(value).strip(), format)
            diff = datetime.now() - event_time

            if unit == "days":
                elapsed = diff.total_seconds() / 86400
            elif unit == "minutes":
                elapsed = diff.total_seconds() / 60
            else:  # hours
                elapsed = diff.total_seconds() / 3600

            warn_lim, danger_lim = limits

            if elapsed < warn_lim:
                return "good"
            if elapsed < danger_lim:
                return "warning"
            return "danger"
        except Exception as e:
            self.log.warning(f"Time assessment failed for {value}: {e}")
            return "danger"
