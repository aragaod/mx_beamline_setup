#!/dls/science/groups/b21/PYTHON3/bin/python3

from beamline import detector
from beamline import redis
import glob
import json
import os
import re
import statistics
import pandas as pd
import argparse
import logging
from logging.config import dictConfig


class QualityControl:

    def __init__(self):
        self.programs = {
            "fast_dp": {"procpath": "fast_dp", "software": self.parse_fastdp},
            # xia2 results are not in the daily table - see XIA2_PIPELINES.
            "xia2": {"procpath": "xia2", "software": self.parse_xia2},
            "all": {"procpath": "all", "software": self.parse_all_pipelines},
        }
        #        to re-add these you need to put parameter back into __init__ as argument
        #        self.last = int(parameter['last'])
        #        self.number = int(parameter['number'])
        #        self.debug = parameter['debug']
        self.redis_database = "i04:eiger:collections"
        self.special_collections = ["xraycentring"]

        ### LOGGING BIT
        ERROR_FORMAT = "%(levelname)s: %(asctime)s in %(funcName)s in %(filename)s at line %(lineno)d: %(message)s\n"
        DEBUG_FORMAT = "%(asctime)s [%(levelname)s] in %(funcName)s in %(filename)s at line %(lineno)d: %(message)s"
        LOG_CONFIG = {
            "version": 1,
            "formatters": {
                "error": {"format": ERROR_FORMAT},
                "debug": {"format": DEBUG_FORMAT},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "error",
                    "level": logging.ERROR,
                },
                "file": {
                    "class": "logging.FileHandler",
                    "filename": "QualityControl.log",
                    "formatter": "debug",
                    "level": logging.DEBUG,
                },
            },
            "root": {"handlers": ("console", "file")},
        }

        # logging.basicConfig()
        # logging.config.dictConfig(LOG_CONFIG)

        # self.log = logging.getLogger(self.__class__.__name__)

        # self.log.setLevel(logging.INFO)

    def get_masters(self, last, number):
        # returns the name of the master file for the n collections preceeding (and including) the last

        start = last
        end = last + number - 1

        masters = []

        for collection in redis.lrange("i04:eiger:collections", start, end * 10):

            # unix_time,new_state,filepath_rbv,filename_rbv, new_master,new_state_msg,new_status_msg,detector_ROI,
            # detector_ROIMode, time_to_injection,omega, new_energy,new_current, new_distance,new_flux,
            # gonibase_x_vel,gonibase_y_vel,gonibase_z_vel

            payload = json.loads(collection.decode("utf"))

            if (
                payload[5] == "Acquire"
                and payload[7] != "4M"
                and not "screening" in payload[2].split("/")
            ):
                # print('+++++++', payload)
                masters.insert(0, f"{json.loads(collection.decode('utf'))[4]}")

        last_collections = masters[1 : number + 1]

        return masters[len(masters) - number - last + 1 : len(masters) - last + 1]

    def get_processed_dir(self, masterfile):
        # returns the visit directory, that of the data collection,
        # the name of the processed dir (different if xrc) and a tag to identify non-rotation datasets

        split_path = masterfile.split("/")

        visit_dir = "/".join(split_path[0:6])
        sub_path = "/".join(split_path[6:])

        dataset_id = sub_path.split("_master")[0]
        processed_dir = visit_dir + "/processed/" + dataset_id

        if "xraycentring" in masterfile:
            special_tag = 1
        else:
            special_tag = 0

        return processed_dir

    def extract_quality_parameters(
        self, masterfile, processing_pipeline="fast_dp", registry=None
    ):
        # opens the output of the specific pipeline and returns the results from the appropriate log files
        payload = {}

        #        if processing_pipeline.keys():
        #            self.log.error(f"extracting data from {processing_pipeline.keys()}")

        #        print(f"Master file is {masterfile}")

        payload["masterfile"] = masterfile
        processing_directory = self.get_processed_dir(masterfile)

        #        for processing_software in processing_pipeline:

        #            if self.debug:
        #                self.log.info(f'[DEBUG]: analysing log files from {processing_software}')

        software = self.programs[processing_pipeline]["software"]

        if registry and software == self.parse_fastdp:
            # Harvest everything, because the identity check needs the raw
            # Space_group_number and Unit_cell_constants - and those are working
            # values, not report rows, so the reported subset does not carry them.
            # Reading the filtered result here was the bug: they had been parsed
            # and then dropped before anything could use them.
            harvested = self.parse_fastdp(processing_directory, all_fields=True)
            payload.update(
                {key: harvested[key] for key in self.REPORT_FIELDS if key in harvested}
            )
            payload.update(
                self.check_test_sample(
                    masterfile,
                    registry,
                    harvested.get("Space_group_number"),
                    harvested.get("Unit_cell_constants"),
                )
            )
        else:
            if not registry:
                self.log.info(
                    "No test sample registry supplied, so the sample cannot be "
                    "identified and the indexing cannot be checked."
                )
            to_add = software(processing_directory)
            if to_add:
                payload.update(to_add)

        return payload

    # Both fast_dp.log and aimless.log report each statistic in three columns:
    #
    #     Overall | InnerShell (low resolution) | OuterShell (high resolution)
    #
    # Which column a value came from used to be decided by a fixed character
    # slice - [-6:], [43:48], [53:58], [-19:-13], [-12:-6] - so it was invisible
    # from the code, and a change in either program's output would have produced
    # a wrong number rather than an error. Rmerge, for instance, read the inner
    # shell purely as a side effect of where [-12:-6] happened to land.
    #
    # Columns are now named, and the shell each statistic wants is stated.
    OVERALL, INNER_SHELL, OUTER_SHELL = 0, 1, 2

    # label in fast_dp.log -> (payload key, which shell)
    FASTDP_FIELDS = {
        "High resolution": ("Resolution", OUTER_SHELL),
        "Multiplicity": ("Multiplicity", OVERALL),
        "Rmerge": ("Rmerge_low_res", INNER_SHELL),
        "Completeness": ("Completeness", OVERALL),
        "CC 1/2": ("CChalf", OVERALL),
        "I/sigma": ("IoverSigma", OVERALL),
    }

    # label in aimless.log -> (payload key, which shell)
    # Rmeas is the one ISPyB shows, and the one the wizard text judges on
    # ("Rmeas low resolution <= 3.5 %"), so it is the R-factor to keep.
    AIMLESS_FIELDS = {
        "Rmeas (all I+ & I-)": ("Aimless_Rmeas_low_res", INNER_SHELL),
        "High resolution limit": ("Aimless_Resolution", OVERALL),
        "Mn(I) half-set correlation CC(1/2)": ("Aimless_CChalf", OVERALL),
        "Completeness": ("Aimless_Completeness", OVERALL),
        "Rmerge  (within I+/I-)": ("Aimless_Rmerge_low_res", INNER_SHELL),
    }

    @staticmethod
    def _trailing_numbers(line, count=3):
        """The last `count` numeric fields on a line, as floats.

        Both logs put the label first and the three shell columns last, so taking
        the numbers off the end works for either format and survives a label
        being reworded or re-indented.
        """
        numbers = []
        for token in reversed(line.split()):
            try:
                numbers.append(float(token))
            except ValueError:
                break
            if len(numbers) == count:
                break
        numbers.reverse()
        return numbers if len(numbers) == count else None

    def _parse_shell_table(self, path, fields, payload):
        """Pull `fields` out of a three-column log, taking the named shell."""
        if not os.path.exists(path):
            self.log.warning(f"Cannot read statistics, file not found: {path}")
            return

        seen = set()
        with open(path, errors="replace") as logfile:
            for line in logfile:
                line = line.rstrip("\n")
                for label, (key, column) in fields.items():
                    # Anchor on the label starting the line so that a label which
                    # is a substring of another cannot claim it, and so a later
                    # matching line cannot silently overwrite an earlier one.
                    if key in seen or not line.strip().startswith(label):
                        continue
                    values = self._trailing_numbers(line)
                    if values is None:
                        continue
                    payload[key] = values[column]
                    seen.add(key)

        missing = set(key for key, _ in fields.values()) - seen
        if missing:
            self.log.warning(
                f"Not found in {os.path.basename(path)}: {', '.join(sorted(missing))}"
            )

    def _parse_space_group_and_cell(self, path, payload):
        """Space group number and refined cell from fast_dp.log.

        The summary prints "Happy with sg# 89" followed by the six cell
        constants on the next line, which is the assignment the statistics were
        computed under - the value worth checking against the sample's usual one.
        """
        if not os.path.exists(path):
            return
        lines = open(path, errors="replace").read().splitlines()
        for index, line in enumerate(lines):
            if "Happy with sg#" not in line:
                continue
            try:
                payload["Space_group_number"] = int(line.split("#", 1)[1].strip())
            except (ValueError, IndexError):
                return
            for following in lines[index + 1 : index + 4]:
                fields = following.split()
                if len(fields) == 6:
                    try:
                        payload["Unit_cell_constants"] = [float(v) for v in fields]
                    except ValueError:
                        continue
                    return
            return

    def _parse_isa(self, path, payload):
        """ISa comes from CORRECT.LP and has no equivalent in the other logs."""
        if not os.path.exists(path):
            self.log.warning(f"Cannot read ISa, file not found: {path}")
            return
        with open(path, errors="replace") as logfile:
            lines = logfile.read().splitlines()
        for index, line in enumerate(lines[:-1]):
            if line.strip().endswith("ISa"):
                values = self._trailing_numbers(lines[index + 1], count=1)
                if values:
                    payload["ISa"] = values[0]
                return
        self.log.warning(f"ISa not found in {os.path.basename(path)}")

    # Harvest widely, report narrowly. The field tables above pull everything the
    # logs conveniently offer, because that costs nothing and makes a new check
    # cheap later. The daily QC report shows only these, one row per distinct
    # measurement.
    #
    # The report used to carry ten rows for five measurements. `aimless.log` is
    # read from inside fast_dp/, so it is fast_dp's *own* scaling step - fast_dp
    # runs XDS, then pointless, then aimless - and every Aimless_* row duplicated
    # a fast_dp number rather than cross-checking an independent pipeline. On the
    # 186 reports carrying both resolutions they never differed by more than
    # 0.005 A.
    #
    # Rmeas rather than Rmerge, because Rmeas is the redundancy-independent
    # statistic, it is what ISPyB displays, and it is what the wizard text
    # already judges on ("Rmeas low resolution <= 3.5 %").
    REPORT_FIELDS = (
        "ISa",
        "Resolution",
        "Aimless_Rmeas_low_res",
        "CChalf",
        "Completeness",
        # Per-image diagnostics (F10): these look inside the collection, where
        # the summary statistics above average everything away.
        # Identity first: these decide whether the numbers above mean anything.
        "Test_sample",
        "Test_sample_identified",
        "Sample_looks_like",
        "Space_group",
        "Space_group_expected",
        "Space_group_match",
        "Unit_cell",
        "Unit_cell_deviation_pct",
        "Multiplicity",
        "Scale_step_pct",
        "Scale_step_at",
        "Rmerge_worst_batch_ratio",
        "Spot_prediction_sd_px",
        "Goniometer_speed_sd_deg",
    )

    # ---- per-image diagnostics (F10) ------------------------------------
    #
    # A dataset's summary statistics can look fine while something went wrong
    # during part of the collection - a beam dump, a shutter glitch, ice, the
    # crystal slipping. Averaged over 3600 images that disappears. INTEGRATE.LP
    # reports one row per image, which is where it does not.
    #
    #  IMAGE IER    SCALE     NBKG NOVL NEWALD NSTRONG  NREJ   SIGMAB   SIGMAR
    #      1   0    0.980    37888    0   8235     497     1  0.02593  0.13363
    #
    # Note what is NOT used here: the deviation of the per-image scale from its
    # median. That was the obvious metric and it does not work. Measured across
    # 55 datasets spanning many dates and crystals, the median dataset already
    # has a maximum deviation of 16%, and a fifth of all images sit more than
    # 10% off the median - because the scale legitimately swings as absorption
    # changes with the crystal's rotation. A sustained 19% excursion is an
    # ordinary dataset, not an event.
    #
    # What does discriminate is the *step*: absorption varies smoothly as the
    # crystal turns, so it makes large excursions out of small steps, while a
    # beam dump or a shutter glitch is a discontinuity. Across the same 55
    # datasets the largest step between adjacent windows has a median of 2.4%
    # and a 90th percentile of 4.0%, which is a usable band.
    SCALE_WINDOW = 25  # images per window; ~2.5 degrees at 0.1 deg per image

    def _parse_per_image(self, path):
        """One row per image from INTEGRATE.LP: (image, scale, nrej, sigmab, sigmar).

        Anchored on the block header, because INTEGRATE.LP contains other
        ten-column tables that would otherwise be picked up as image rows.
        """
        rows, in_block = [], False
        if not os.path.exists(path):
            self.log.warning(f"No per-image statistics, file not found: {path}")
            return rows
        with open(path, errors="replace") as logfile:
            for line in logfile:
                if "IMAGE IER" in line and "SCALE" in line:
                    in_block = True
                    continue
                if not in_block:
                    continue
                fields = line.split()
                if len(fields) == 10 and fields[0].isdigit():
                    try:
                        rows.append(
                            (
                                int(fields[0]),
                                float(fields[2]),
                                int(fields[7]),
                                float(fields[8]),
                                float(fields[9]),
                            )
                        )
                    except ValueError:
                        pass
                elif not fields or not fields[0].isdigit():
                    in_block = False
        return rows

    def _parse_block_deviations(self, path):
        """The two per-block error metrics INTEGRATE.LP reports as it goes."""
        if not os.path.exists(path):
            return [], []
        text = open(path, errors="replace").read()
        spot = [
            float(value)
            for value in re.findall(
                r"STANDARD DEVIATION OF SPOT\s+POSITION \(PIXELS\)\s+([\d.]+)", text
            )
        ]
        spindle = [
            float(value)
            for value in re.findall(
                r"STANDARD DEVIATION OF SPINDLE POSITION \(DEGREES\)\s+([\d.]+)", text
            )
        ]
        return spot, spindle

    def _scale_step(self, scales):
        """Largest jump between adjacent windows, as a percentage of the median.

        Returns the size of the step and the image number where it happened, so
        the report can name the images worth looking at rather than only saying
        that something happened.
        """
        median_scale = statistics.median(scales)
        window = self.SCALE_WINDOW
        if not median_scale or len(scales) < 2 * window:
            return None, None
        windows = [
            (index, statistics.median(scales[index : index + window]))
            for index in range(0, len(scales) - window + 1, window)
        ]
        worst_step, worst_index = 0.0, None
        for (_, before), (index, after) in zip(windows, windows[1:]):
            step = abs(after - before) / median_scale * 100
            if step > worst_step:
                worst_step, worst_index = step, index
        return worst_step, worst_index

    def _parse_per_batch_rmerge(self, path):
        """Rmerge per batch from aimless.log's "Analysis against all Batches".

        Batches are binned in groups of ten images, about one degree. Note this
        is Rmerge, not Rmeas: aimless reports Rmeas per resolution shell but only
        Rmerge per batch, so an R-factor against rotation angle can only be
        Rmerge. The overall Rmeas is still reported separately.
        """
        if not os.path.exists(path):
            return []
        lines = open(path, errors="replace").read().splitlines()
        start = next(
            (
                n
                for n, line in enumerate(lines)
                if "Analysis against all Batches" in line
            ),
            None,
        )
        if start is None:
            return []
        header = next(
            (
                n
                for n in range(start, min(start + 25, len(lines)))
                if lines[n].strip().startswith("N ")
            ),
            None,
        )
        if header is None:
            return []
        columns = lines[header].split()
        if "Rmerge" not in columns:
            return []
        index = columns.index("Rmerge")
        values = []
        for line in lines[header + 1 :]:
            fields = line.split()
            if not fields or not fields[0].isdigit():
                break
            if len(fields) > index:
                try:
                    value = float(fields[index])
                except ValueError:
                    continue
                if value > 0:
                    values.append(value)
        return values

    def parse_per_image_diagnostics(self, processing_directory, oscillation=None):
        """Figures of merit that look inside a collection rather than across it."""
        payload = {}
        integrate_lp = os.path.join(processing_directory, "fast_dp", "INTEGRATE.LP")
        rows = self._parse_per_image(integrate_lp)
        if not rows:
            return payload

        scales = [row[1] for row in rows]
        rejects = [row[2] for row in rows]
        mosaicity = [row[4] for row in rows]

        step, at_index = self._scale_step(scales)
        if step is not None:
            payload["Scale_step_pct"] = round(step, 2)
            if at_index is not None:
                first_image = rows[at_index][0]
                where = f"images {first_image}-{first_image + self.SCALE_WINDOW}"
                if oscillation:
                    where += f" (phi {first_image * oscillation:.0f} deg)"
                payload["Scale_step_at"] = where

        batch_rmerge = self._parse_per_batch_rmerge(
            os.path.join(processing_directory, "fast_dp", "aimless.log")
        )
        if len(batch_rmerge) >= 20:
            median_rmerge = statistics.median(batch_rmerge)
            if median_rmerge:
                payload["Rmerge_worst_batch_ratio"] = round(
                    max(batch_rmerge) / median_rmerge, 2
                )

        median_mosaicity = statistics.median(mosaicity)
        if median_mosaicity:
            payload["Mosaicity_spread"] = round(max(mosaicity) / median_mosaicity, 2)

        spot, spindle = self._parse_block_deviations(integrate_lp)
        if spot:
            # How well the prediction model fits the observed spots. Rising
            # values mean the detector position, the beam or the crystal moved.
            payload["Spot_prediction_sd_px"] = max(spot)
        if spindle:
            # Whether omega turned at a constant speed. If it runs fast or slow
            # the reflection appears at a different angle than predicted. This is
            # a rotation *speed* check, not a rotation axis alignment check.
            payload["Goniometer_speed_sd_deg"] = max(spindle)

        return payload

    def parse_fastdp(self, processing_directory, all_fields=False):
        """Read the diffraction statistics from a fast_dp run.

        Returns the daily-check subset by default. Pass all_fields=True to get
        everything the parser understands, which is what a trend analysis over
        the report archive would want.
        """
        harvested = {}
        fast_dp_dir = os.path.join(processing_directory, "fast_dp")

        self.correct_lp = os.path.join(fast_dp_dir, "CORRECT.LP")
        self.fastdp_log = os.path.join(fast_dp_dir, "fast_dp.log")
        self.aimless_log = os.path.join(fast_dp_dir, "aimless.log")

        self._parse_isa(self.correct_lp, harvested)
        self._parse_space_group_and_cell(self.fastdp_log, harvested)
        self._parse_shell_table(self.fastdp_log, self.FASTDP_FIELDS, harvested)
        self._parse_shell_table(self.aimless_log, self.AIMLESS_FIELDS, harvested)
        harvested.update(self.parse_per_image_diagnostics(processing_directory))

        if all_fields:
            return harvested
        return {key: harvested[key] for key in self.REPORT_FIELDS if key in harvested}

    # ---- test sample identity ------------------------------------------
    #
    # The wizard text says "insulin", but i04 rotates through at least six test
    # proteins. Knowing which one was mounted matters for two reasons.
    #
    # First, it makes the statistics meaningful. If indexing assigned the wrong
    # space group the ISa and Rmeas that follow describe a bad interpretation of
    # the data, not a bad beamline - and that happens: across the archive
    # thaumatin was indexed away from its usual space group on 2 of 236 runs,
    # carbonic anhydrase on 3 of 116 and thermolysin on 1 of 27. On those days the
    # report blamed the beamline for an indexing failure.
    #
    # Second, it lets the report and the user email name the sample that was
    # actually used rather than whichever one the template was written around.

    def identify_test_sample(self, masterfile, registry):
        """Which test protein this dataset is, from the master file path.

        Matches aliases against the whole path rather than a single filename
        token, because the naming is not consistent: SeThau2/_SeThau2_1_master.h5
        puts the name in a directory while TestInsulin_6_1_master.h5 puts it in
        the filename with a trailing number. Matching the path identifies 187 of
        188 stored reports; the one miss is not a test crystal.
        """
        if not masterfile or not registry:
            return None
        lowered = str(masterfile).lower()
        for name, entry in registry.items():
            for alias in (entry or {}).get("aliases", []):
                if str(alias).lower() in lowered:
                    return name
        self.log.info(f"Test sample not recognised from {masterfile}")
        return None

    @staticmethod
    def _normalise_space_group(value):
        """Compare space group names without caring about spacing.

        The pipelines write the same group differently - "P 41 21 2",
        "P41212" - so the text is squashed before comparison.
        """
        return "".join(str(value).split()).upper()

    def check_space_group(self, assigned, entry, source="fast_dp"):
        """Is this assignment consistent with what the sample normally gives?

        Two forms have to be handled, because the pipelines report differently:

        * **fast_dp gives a number**, and it is the *point group* - 89 for
          thaumatin, not the 92 of P41212 - so it is compared against
          `space_group_number`.
        * **xia2.dials and xia2.3dii give a full space group as text**, and even
          within one pipeline the same protein comes back as more than one name:
          dials assigns thaumatin "P 41 21 2" on some runs and "P 4 21 2" on
          others, the second being the point group with the screw axis not
          resolved. Neither is wrong, so the registry holds a list of accepted
          names rather than one expected value.

        Anything outside that list is the signal worth having - it means the
        statistics that follow describe a different interpretation of the data.
        """
        if assigned is None:
            return None

        if isinstance(assigned, (int, float)) or str(assigned).strip().isdigit():
            expected = entry.get("space_group_number")
            if expected is None:
                return None
            return "yes" if int(assigned) == int(expected) else "no"

        accepted = entry.get("accepted_space_groups") or []
        if entry.get("space_group"):
            accepted = [entry["space_group"]] + list(accepted)
        if not accepted:
            self.log.info(
                f"No accepted space groups listed for this sample, so the "
                f"{source} assignment {assigned!r} cannot be checked"
            )
            return None
        normalised = {self._normalise_space_group(name) for name in accepted}
        return "yes" if self._normalise_space_group(assigned) in normalised else "no"

    def _cell_deviation(self, measured, expected):
        """Largest deviation of a, b or c from an expected cell, as a percentage."""
        if not measured or not expected or len(measured) < 3:
            return None
        deviations = [
            abs(m - e) / e * 100 for m, e in zip(measured[:3], expected[:3]) if e
        ]
        return round(max(deviations), 2) if deviations else None

    def identify_by_fingerprint(self, registry, space_group, unit_cell, tolerance=5.0):
        """Which registered sample this space group and cell look like, if any.

        This is a cross-check, never the primary identification. Identity comes
        from the file path, which is independent of the processing - and that
        independence is the point. Inferring identity from the space group would
        be circular: a thaumatin that indexed as P 1 would read as "unknown
        sample" instead of "thaumatin indexed wrong", destroying exactly the
        signal the space group check exists to produce, on precisely the days it
        matters.

        Used the other way round it answers a different and useful question. If
        the path says thaumatin but the cell matches insulin cleanly, then the
        wrong sample was mounted or it was mislabelled - which is worth telling
        staff, while the users still get their normal email, because a good test
        crystal was collected and the data is fine.
        """
        if not unit_cell:
            return None
        for name, entry in (registry or {}).items():
            entry = entry or {}
            if self.check_space_group(space_group, entry) == "no":
                continue
            deviation = self._cell_deviation(unit_cell, entry.get("unit_cell"))
            if deviation is not None and deviation <= tolerance:
                return name
        return None

    def check_test_sample(self, masterfile, registry, space_group, unit_cell):
        """Identify the test sample and check the indexing against what it gives.

        Always records what was observed, even when the sample is not recognised.
        An unrecognised sample is not a failure to report nothing about - the
        space group and cell are exactly the values someone needs in order to add
        it to the registry, so they are stored with no verdict attached rather
        than thrown away.
        """
        payload = {}
        name = self.identify_test_sample(masterfile, registry)

        # Recorded whether or not the sample is known, so the row is visibly
        # there every day until someone either adds the sample or corrects the
        # naming. It is a configuration gap, not a beamline fault, so the rule
        # for it warns rather than alarms.
        payload["Test_sample_identified"] = "yes" if name else "no"
        payload["Test_sample"] = (
            (registry.get(name) or {}).get("protein", name)
            if name
            else "not recognised"
        )
        if space_group is not None:
            payload["Space_group"] = space_group
        if unit_cell and len(unit_cell) >= 3:
            payload["Unit_cell"] = " ".join(f"{value:.1f}" for value in unit_cell[:3])

        if not name:
            self.log.info(
                "Test sample not recognised, so the space group and cell are "
                "recorded without being checked. Add it to test_samples in "
                "TestCrystal.yaml to have it checked from now on."
            )
            return payload

        entry = registry.get(name) or {}

        match = self.check_space_group(space_group, entry)
        if match is not None:
            payload["Space_group_expected"] = (
                entry.get("space_group_number")
                if isinstance(space_group, (int, float))
                else entry.get("space_group")
            )
            payload["Space_group_match"] = match

        deviation = self._cell_deviation(unit_cell, entry.get("unit_cell"))
        if deviation is not None:
            payload["Unit_cell_deviation_pct"] = deviation

        # Does the crystal look like something else entirely? Only meaningful
        # when the fingerprint matches a *different* registered sample well; a
        # fingerprint matching nothing is a misindexing, which the checks above
        # already cover.
        looks_like = self.identify_by_fingerprint(registry, space_group, unit_cell)
        if looks_like and looks_like != name:
            payload["Sample_looks_like"] = (registry.get(looks_like) or {}).get(
                "protein", looks_like
            )
            self.log.warning(
                f"The file name says {name} but the space group and cell match "
                f"{looks_like}. The wrong sample may have been mounted, or it "
                f"may be mislabelled. The data itself is fine."
            )

        return payload

    # ---- xia2 pipelines (V3b) -------------------------------------------
    #
    # xia2.dials and xia2.3dii run on every dataset and sit beside fast_dp in the
    # processing tree, under stable named symlinks as well as UUID directories.
    #
    # They are NOT reported in the daily table, and that is deliberate. fast_dp is
    # named for being the fast one, and the module is run the moment staff see it
    # finish, so when beamline setup reads the directory the xia2 results very
    # often do not exist yet. A missing pipeline here is normal, not an error.
    # This exists as a tool for looking back over datasets after the fact.
    #
    # Reading them is worth it because they genuinely disagree with fast_dp, and
    # with each other. On the 2026-07-08 SeThau2 dataset the high resolution limit
    # was 1.26 A from fast_dp, 1.18 from 3dii and 1.08 from dials, with outer
    # shell I/sigma of 3.60, 0.5 and 0.2: fast_dp stops while I/sigma is still
    # high, dials cuts on CC(1/2) following the XDS paper. Each pipeline therefore
    # needs its own limits, and a resolution from one must never be judged against
    # another's threshold.
    XIA2_PIPELINES = {"dials": "xia2-dials", "3dii": "xia2-3dii"}

    # Straight from the JSON's "overall" block, at full precision. No column
    # slicing and no shell ambiguity, unlike the fast_dp and aimless logs.
    XIA2_FIELDS = {
        "r_meas": "Rmeas",
        "r_merge": "Rmerge",
        "r_pim": "Rpim",
        "cc_one_half": "CChalf",
        "i_over_sigma_mean": "IoverSigma",
        "completeness": "Completeness",
        "multiplicity": "Multiplicity",
    }

    @staticmethod
    def _resolution_from_d_star_sq(d_star_sq):
        """The JSON gives 1/d^2; the number people quote is d."""
        try:
            value = float(d_star_sq)
        except (TypeError, ValueError):
            return None
        return round(value**-0.5, 2) if value > 0 else None

    def _parse_xia2_spacegroup(self, pipeline_directory):
        """Space group from xia2-summary.dat.

        Worth having because the pipelines can disagree: on the 2026-07-08
        dataset 3dii assigned P 1 21 1 where dials assigned P 41 21 2, and for
        thaumatin the latter is right. A disagreement between pipelines on the
        same data is itself a quality signal.
        """
        summary = os.path.join(pipeline_directory, "xia2-summary.dat")
        if not os.path.exists(summary):
            return None
        for line in open(summary, errors="replace"):
            if line.strip().startswith("Spacegroup:"):
                return line.split(":", 1)[1].strip()
        return None

    def parse_xia2_pipeline(self, processing_directory, pipeline="dials"):
        """Merging statistics from one xia2 pipeline, or {} if it has not run.

        Keys are prefixed with the pipeline name, because these numbers must not
        be confused with fast_dp's - they are cut at a different resolution and
        carry different thresholds.
        """
        payload = {}
        directory_name = self.XIA2_PIPELINES.get(pipeline)
        if directory_name is None:
            self.log.warning(f"Unknown xia2 pipeline requested: {pipeline}")
            return payload

        pipeline_directory = os.path.join(processing_directory, directory_name)
        matches = glob.glob(
            os.path.join(pipeline_directory, "LogFiles", "*merging-statistics.json")
        )
        if not matches:
            # Expected when the module runs shortly after fast_dp finishes.
            self.log.info(
                f"No {directory_name} results yet in {processing_directory}; skipping."
            )
            return payload

        try:
            with open(matches[0]) as handle:
                statistics_json = json.load(handle)
        except (OSError, ValueError) as error:
            self.log.warning(f"Could not read {matches[0]}: {error}")
            return payload

        overall = statistics_json.get("overall", {})
        for json_key, name in self.XIA2_FIELDS.items():
            if json_key in overall:
                payload[f"{pipeline}_{name}"] = overall[json_key]

        # Beware: in the "overall" block the min/max refer to *d*, not to d*, so
        # they read inverted against the binned arrays of the same names.
        # d_star_sq_min = 0.857769 is 1.08 A, the HIGH resolution limit, and
        # d_star_sq_max = 0.000343 is 53.99 A, the low one. Taking the obvious
        # key here reports the low resolution limit as the resolution.
        resolution = self._resolution_from_d_star_sq(overall.get("d_star_sq_min"))
        if resolution is not None:
            payload[f"{pipeline}_Resolution"] = resolution

        spacegroup = self._parse_xia2_spacegroup(pipeline_directory)
        if spacegroup:
            payload[f"{pipeline}_Spacegroup"] = spacegroup

        return payload

    def parse_xia2(self, processing_directory):
        """Every xia2 pipeline that has produced results, merged into one dict."""
        payload = {}
        for pipeline in self.XIA2_PIPELINES:
            payload.update(self.parse_xia2_pipeline(processing_directory, pipeline))
        return payload

    def parse_all_pipelines(self, processing_directory):
        """fast_dp plus whichever xia2 pipelines have finished.

        For looking back over datasets, not for the daily report - see the note
        on XIA2_PIPELINES. Where the pipelines disagree on space group, that is
        recorded as its own entry rather than left for the reader to spot.
        """
        payload = self.parse_fastdp(processing_directory, all_fields=True)
        payload.update(self.parse_xia2(processing_directory))

        spacegroups = {
            key: value
            for key, value in payload.items()
            if key.endswith("_Spacegroup") and value
        }
        if len(set(spacegroups.values())) > 1:
            payload["Spacegroup_disagreement"] = "; ".join(
                f"{key.split('_')[0]}={value}"
                for key, value in sorted(spacegroups.items())
            )
        return payload

    def logging(self, message):
        # needs a better way of logging
        self.log.error(f"[DEBUG]: analyzing {message}")
        #         self.log.append(f'[DEBUG]: analyzing {message}')
        return

    def full_analysis(self):
        print()

        if self.debug:
            self.log.info("running in DEBUG mode")

            self.log.info("FULL ANALYSIS REPORT\n\n")

        counter = 1

        for dataset in self.get_masters(self.last, self.number):

            if self.debug:
                self.log.info(f"{counter}/{self.number} - masterfile: {dataset}")
                self.log.info(
                    f"[DEBUG]: a{counter}/{self.number} - processed directory: {self.get_processed_dir(dataset)}"
                )

                self.log.info(f"[DEBUG]: analyzing {dataset}")

            result = self.extract_quality_parameters(dataset, self.programs)

            print(result)
            if self.debug == True:
                if result != {}:
                    print(f"AUTOPROCESSING RESULTS: {result}\n")
                else:
                    print("no result")
            counter += 1

        return result


def check_parameters():
    # reads the input parameters for the executable

    parser = argparse.ArgumentParser(
        description="Dataset quality check",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-l", dest="last", action="store", type=int, help="last dataset"
    )
    parser.add_argument(
        "-n",
        dest="number",
        action="store",
        type=int,
        help="number of datasets before the last",
    )
    parser.add_argument("-d", dest="debug", action="store_true", help="debug mode")
    args = parser.parse_args()
    config = vars(args)

    return config


class TestCrystalResults:
    def __init__(self, masterfile, registry=None):
        self.masterfile = masterfile
        # The test sample registry from the module YAML. Without it the statistics
        # are still parsed, but nothing knows which protein they came from.
        self.registry = registry
        self.qc = QualityControl()

    def get_results(self):
        """Return a dictionary of processing results for a specific masterfile"""
        return self.qc.extract_quality_parameters(
            self.masterfile, registry=self.registry
        )


if __name__ == "__main__":

    arguments = check_parameters()
    qc = QualityControl(arguments)

    qc.full_analysis()
