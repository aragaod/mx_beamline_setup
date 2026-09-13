"""Reading the eiger arming log.

Every time the detector is armed, `autowatch_eiger` pushes a record onto the
redis list `{BEAMLINE}:eiger:collections`. It is the only place that records what
the beam was actually doing at the moment of a collection - flux, energy, beam
size, exposure, and the master file the data went to - which makes it the input
for the dose calculation (B2b, F5) and the sample-identity cross-check.

The list is long (roughly a million entries) and holds far more than data
collections, so everything here is written to read a bounded window from the
head rather than the whole list.

Two modules already read this list, each in its own way, and one of them
addresses the record by integer position (`payload[5]`, `payload[7]`). That is
what `{BEAMLINE}:eiger:collections:schema` exists to prevent: the schema is
published alongside the list and zipped onto each entry, so a column added
upstream shifts nothing. Everything here goes through the schema.

Two things that will otherwise cost an afternoon
------------------------------------------------

**Every collection appears twice.** Once as `state_id 1` / `Acquire` and once as
`state_id 10` / `Aborted`. Summing both double-counts the dose. Filter on
`state_id == 1`.

**Old records are narrower than the schema.** The schema published in redis is
the *current* one, and the list holds four generations of record:

    18 fields   707,772 records   up to 2025-08-05
    31-39           16 records    2025-08-06, the transition
    40 fields    88,832 records   up to 2025-12-16
    42 fields   171,777 records   since

Fields have only ever been appended, so zipping the current schema onto an old
record names its columns correctly - it simply runs out. What that means for a
consumer is that **an old entry has no `transmission_pct`, `acquire_time_s`,
`beamsize_h_um`, `number_images`, `full_visit` or beamstop position at all**, and
`entry["transmission_pct"]` raises `KeyError` rather than returning something
wrong.

Use `.get()` with a default for anything past the first 18 columns, or filter with
`complete_only=True`, which drops records that predate the field you need. The
practical limits: no transmission or exposure before **6 August 2025**, and no
beamstop position before **16 December 2025**.

**`omega_vel_dps` is not the collection velocity.** It reads 180.0 on essentially
every record, including 3600-image 360-degree sweeps where the real velocity is
about 0.25 deg/s. It is the velocity at the moment of arming, before the motor
has been commanded to its collection speed. Do not derive a rotation range from
it - see `base/dose.py` for what is used instead.
"""

import json
import re
import time

# Only 1/Acquire is a real collection; 10/Aborted is the duplicate of the same one.
ACQUIRING_STATE_ID = 1

# X-ray centring shots go to their own subdirectory. They are real dose on the
# crystal and belong in any total, but they are not the dataset.
XRAY_CENTRING_MARKER = "xraycentring"

LIST_KEY = "{beamline}:eiger:collections"
SCHEMA_KEY = "{beamline}:eiger:collections:schema"

# One day of arming records comfortably; the list holds about a million entries
# in total, so an unbounded read is never what anyone wants.
#
# **It is a day, not a week.** Measured 2026-08-31: 5000 records reached back
# only to 6 August. Anything asking about an older collection must pass its own
# depth, or it will be told the arming record does not exist when it plainly
# does - which is what happened when a 30 July master file was selected and the
# report said "no arming record found for this collection".
DEFAULT_DEPTH = 5000


class EigerLog:
    """A bounded, schema-driven view of the arming log."""

    def __init__(self, redis_client, beamline="i04", log=None, depth=DEFAULT_DEPTH):
        self.redis = redis_client
        self.beamline = beamline
        self.log = log
        self.depth = depth
        self._schema = None

    def _note(self, level, message):
        if self.log is not None:
            getattr(self.log, level)(message)

    @property
    def schema(self):
        """Column names, read once and cached."""
        if self._schema is None:
            raw = self.redis.get(SCHEMA_KEY.format(beamline=self.beamline))
            if not raw:
                raise LookupError(
                    f"No schema at {SCHEMA_KEY.format(beamline=self.beamline)} - "
                    "the arming log cannot be read positionally on purpose"
                )
            self._schema = json.loads(raw)
        return self._schema

    # The first 18 columns have been present since the beginning. Anything beyond
    # them is missing from records written before 6 August 2025.
    ORIGINAL_FIELDS = 18

    def entries(self, depth=None, since=None, needs=()):
        """Records from the head of the list, newest first.

        `since` is a unix timestamp; the list is in time order, so the scan stops
        at the first record older than it rather than reading the rest.

        `needs` names fields the caller cannot work without; records that predate
        them are skipped rather than returned half-formed. Without it, an old
        record simply lacks those keys - see the schema note at the top.
        """
        schema = self.schema
        raw = self.redis.lrange(
            LIST_KEY.format(beamline=self.beamline), 0, (depth or self.depth) - 1
        )
        out = []
        for record in raw:
            try:
                entry = dict(zip(schema, json.loads(record)))
            except (ValueError, TypeError):
                # One malformed record must not cost the rest of the window.
                continue
            if since is not None and entry.get("unix_time", 0) < since:
                break
            if needs and any(field not in entry for field in needs):
                continue
            out.append(entry)
        return out

    def collections(self, depth=None, since=None, visit=None, needs=()):
        """Only the records that are a real, armed collection with a master file."""
        found = [
            entry
            for entry in self.entries(depth=depth, since=since, needs=needs)
            if entry.get("state_id") == ACQUIRING_STATE_ID and entry.get("master_file")
        ]
        if visit:
            found = [e for e in found if e.get("full_visit") == visit]
        return found

    def for_master(self, master_file, depth=None, since=None):
        """Every armed collection that wrote to one master file.

        Normally exactly one. More than one means the same master was armed
        repeatedly, and the crystal absorbed all of it.
        """
        return [
            entry
            for entry in self.collections(depth=depth, since=since)
            if entry.get("master_file") == master_file
        ]

    def around(self, master_file, window_s=3600, depth=None, since=None):
        """Everything the same crystal absorbed near one dataset.

        The X-ray centring shots fired at a crystal before its dataset are dose
        it keeps, whether or not the images are used. They are small - about
        0.0065 MGy against 1.5 MGy for a dataset - but leaving them out is wrong
        in principle, and the ratio does not hold for every strategy or beamline.
        """
        collections = self.collections(depth=depth, since=since)
        anchor = next(
            (e for e in collections if e.get("master_file") == master_file), None
        )
        if anchor is None:
            self._note("warning", f"No armed collection found for {master_file}")
            return []
        moment = anchor.get("unix_time", 0)
        return [
            entry
            for entry in collections
            if abs(entry.get("unix_time", 0) - moment) <= window_s
            and entry.get("full_visit") == anchor.get("full_visit")
            and entry.get("loaded_pin") == anchor.get("loaded_pin")
        ]


def is_xray_centring(entry):
    return XRAY_CENTRING_MARKER in (entry.get("filepath") or "").lower()


# Directories that hold collections from whatever crystal happened to be on the
# goniometer, so the directory name says nothing about which one it was.
GENERIC_DIRECTORIES = {
    "test-shots",
    "test_shots",
    "test_shot",
    "manual",
    "bs",
    "screening",
    "grid",
    "xrc",
}


def crystal_name(entry):
    """Best-effort crystal name for one collection.

    There is no single naming convention, and pretending otherwise gives a wrong
    lifetime dose rather than an obviously missing one. Across the commissioning
    visits of 2026 the same crystal reached the arming log as all of:

        .../20260710/TestThaumatin/Sethau4/TestThaumatin_Sethau4_1_master.h5
        .../20260731/test-shots/Sethau4_1_master.h5
        .../xraycentring/20260710/TestThaumatin/Sethau4/TestThaumatin_Sethau4_1_...

    The directory holding the file is the most meaningful name when it is a real
    sample directory, which it usually is. When it is one of the shared buckets
    above, the name is taken from the filename instead - which is where those
    31 July and 2 August collections keep it, and those are the two days worth
    finding.
    """
    master = entry.get("master_file") or ""
    parts = [p for p in master.split("/") if p]
    if len(parts) < 2:
        return ""
    directory = parts[-2]
    if directory.lower() not in GENERIC_DIRECTORIES:
        return directory
    stem = re.sub(r"_\d+_master\.h5$", "", parts[-1])
    stem = re.sub(r"_master\.h5$", "", stem)
    # `TestThaumatin_Sethau4` names the protein then the crystal; a bare
    # `Sethau4` is already the crystal.
    return stem.split("_")[-1].strip("_")


def crystal_key(entry):
    """How a crystal is identified across a run.

    Sample names are only unique **within a visit** - across visits they collide -
    so the key has to carry the visit. `loaded_pin` is a useful cross-check
    because it survives a dewar clean, but `loaded_puck` does not: a puck comes
    back to a different position after the dewar is warmed and refilled.
    """
    return (entry.get("full_visit") or "", crystal_name(entry).lower())


def mentions_crystal(entry, name):
    """Whether a collection belongs to a named crystal.

    A plain substring test is not safe here: `Sethau1` is a substring of
    `Sethau13`, and both were real crystals on i04 in 2026. The name has to sit
    on token boundaries.
    """
    if not name:
        return False
    pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
    return re.search(pattern, entry.get("master_file") or "", re.IGNORECASE) is not None


def history_for_crystal(entries, name, visit=None, until=None):
    """Every collection on one crystal, in time order.

    Matching on the path rather than on `crystal_name` alone, because the same
    crystal is named differently in different directories and its whole life has
    to be found for a lifetime dose to mean anything.
    """
    found = [
        entry
        for entry in entries
        if mentions_crystal(entry, name)
        and (visit is None or entry.get("full_visit") == visit)
        and (until is None or entry.get("unix_time", 0) <= until)
    ]
    return sorted(found, key=lambda e: e.get("unix_time", 0))


def collection_time(entry):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.get("unix_time", 0)))
