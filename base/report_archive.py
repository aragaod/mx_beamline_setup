"""Reading the stored reports back as a table, for trend analysis (F8).

Every module writes a report per day into the beamline's redis hash, under
`<Module>_report_<YYYYMMDD>`. Fourteen months of them are sitting there. Read one
at a time they are a record of what happened on a morning; read together they are
the only long-baseline measurement of the beamline this group has.

The questions that motivated this, all of which need the same machinery:

  * Does machine steering explain the beamstop realignments? (The pairing was
    reconstructed after the fact and there was not enough of it.)
  * Where is the ISa knee against dose, so test crystals are replaced on
    evidence rather than at the Garman limit?
  * Is anything drifting that nobody has noticed?

Read-only. Nothing here writes to redis or touches hardware.

Two things about the archive itself
-----------------------------------

**Reports have a format version.** `format_version` 2 is the current shape;
anything without the stamp predates it and may hold numbers as display strings
("1.234 mm") rather than numbers. `dev/migrate_redis_reports.py` rewrites the
history; until it has been run on a key, `numeric()` below is what makes an old
report comparable with a new one.

**A status is not a measurement.** What a report said on the day is an audit
trail of what staff saw. Analysis recomputes from values and never from the
stored status, so that a threshold changed later does not rewrite history.
"""

import re
from datetime import datetime

# `<Module>_report_<YYYYMMDD>`, with the date the only variable part.
REPORT_KEY = re.compile(r"^(?P<module>\w+?)_report_(?P<date>\d{8})$")

# Leading number in something like "1.234 mm" or "-0.45".
LEADING_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")


def numeric(value):
    """A float if one can be had honestly, otherwise None.

    Deliberately does not treat True/False as 1/0: a feedback loop being on is
    not a quantity, and averaging it would produce a number that means nothing.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = LEADING_NUMBER.match(value)
        if match:
            return float(match.group(1))
    return None


def parse_key(name):
    """(module, date) for a report key, or None for anything else in the hash."""
    match = REPORT_KEY.match(name)
    if not match:
        return None
    return match.group("module"), match.group("date")


class ReportArchive:
    """Every stored report, as rows of (date, module, parameter, value)."""

    def __init__(self, redis_client, hash_key, deserialise, log=None):
        self.redis = redis_client
        self.hash_key = hash_key
        # The app stores with a serialiser; the caller passes its loads().
        self.deserialise = deserialise
        self.log = log
        self._reports = None

    def reports(self):
        """{(module, date): payload}, read once and cached."""
        if self._reports is not None:
            return self._reports
        found = {}
        for raw_name, raw_value in self.redis.hgetall(self.hash_key).items():
            name = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
            parsed = parse_key(name)
            if not parsed:
                continue
            try:
                payload = self.deserialise(raw_value)
            except Exception:
                # A report that will not deserialise is one report, not a reason
                # to abandon fourteen months of them.
                if self.log:
                    self.log.warning(f"Could not read {name}")
                continue
            if isinstance(payload, dict):
                found[parsed] = payload
        self._reports = found
        return found

    def modules(self):
        return sorted({module for module, _ in self.reports()})

    def dates(self, module=None):
        return sorted(
            {date for name, date in self.reports() if module is None or name == module}
        )

    def series(self, module, parameter):
        """{date: value} for one parameter, numeric only, oldest first.

        The stored shape is `{"parameters": {name: {"value": ..., "status": ...}}}`.
        Older reports sometimes hold the bare value instead of a dictionary, so
        both are accepted.
        """
        out = {}
        for (name, date), payload in self.reports().items():
            if name != module:
                continue
            parameters = payload.get("parameters") or {}
            if parameter not in parameters:
                continue
            cell = parameters[parameter]
            raw = cell.get("value") if isinstance(cell, dict) else cell
            value = numeric(raw)
            if value is not None:
                out[date] = value
        return dict(sorted(out.items()))

    def parameters(self, module):
        """Every parameter name that module has ever reported."""
        names = set()
        for (name, _), payload in self.reports().items():
            if name == module:
                names.update((payload.get("parameters") or {}).keys())
        return sorted(names)

    def numeric_parameters(self, module, minimum_points=3):
        """Only the parameters with enough numeric history to plot."""
        return sorted(
            name
            for name in self.parameters(module)
            if len(self.series(module, name)) >= minimum_points
        )

    def paired(self, module_a, parameter_a, module_b, parameter_b):
        """Values for the days on which both were recorded.

        Returns (dates, xs, ys). Pairing on the date is the whole point: the
        steering-vs-beamstop question failed before because the two modules ran
        on different subsets of days and the overlap was never made explicit.
        """
        left = self.series(module_a, parameter_a)
        right = self.series(module_b, parameter_b)
        dates = sorted(set(left) & set(right))
        return dates, [left[d] for d in dates], [right[d] for d in dates]


def pearson(xs, ys):
    """Correlation coefficient, or None when it is not defined.

    Written out rather than pulled from scipy because this has to run wherever
    the app runs, and it is six lines.
    """
    n = len(xs)
    if n < 3:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denominator = (sum(v * v for v in dx) * sum(v * v for v in dy)) ** 0.5
    if not denominator:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denominator


def linear_fit(xs, ys):
    """(slope, intercept), or None. Least squares, same reasoning as above."""
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    variance = sum((x - mean_x) ** 2 for x in xs)
    if not variance:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / variance
    return slope, mean_y - slope * mean_x


def as_date(stamp):
    return datetime.strptime(stamp, "%Y%m%d")
