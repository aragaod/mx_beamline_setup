"""Absorbed dose in MGy, from the arming log and the RADDOSE-3D service.

Why this exists
---------------
TestCrystal reports ISa and Rmeas as a measure of how the beamline is doing. Over
July and August 2026 the test crystal's ISa fell from about 41 to about 31, and
the module presented that as the beamline degrading. It was not: cumulative dose
against ISa over those 17 setups gives Pearson r = -0.84, slope -0.26 ISa per
MGy. Roughly 70% of the decline was the crystal ageing exactly as it should.
Without a dose column the assessment is actively misleading.

A second finding came out of the same analysis and argues for this independently
of the ageing trend. On 31 July and 2 August the setup collections ran at 71%
transmission instead of the usual 35%, delivering just over double the intended
dose in one shot - 6.4 MGy of the crystal's 33.4 MGy lifetime came from those two
days, and nobody noticed at the time. A per-collection dose figure checked
against the 1.5 MGy the module actually asks for would have caught both the same
morning.

How it is calculated
--------------------
RADDOSE-3D is already wrapped as a FastAPI service (`applications/autodose`);
nothing here reimplements the physics.

Dose is linear in both flux and exposure time, so the service is asked once per
distinct beam configuration - energy, beam size, oscillation range - at a nominal
flux for one second, and every collection sharing that configuration is
arithmetic:

    dose_MGy = rate_MGy_per_s * (flux / NOMINAL_FLUX) * total_exposure_time

Measured on 2026-08-29: 0.0174 MGy/s at 13 keV, 30.13 x 18.68 um, nominal
3.0e10 ph/s. Cross-checked against a direct call at the real flux and exposure -
agreement 0.83%. All 47 armed collections in a month-long series shared one
configuration, so the whole month needed a single call. `verify_scaling()` below
re-runs that cross-check on demand.

Two things the API will do to you
---------------------------------
`oscillation_start=0` returns HTTP 500. Use 1, which is what the shared
`DoseClient` defaults to. It is documented nowhere.

The oscillation range is **not** taken from `omega_vel_dps` in the arming record,
which reads 180.0 on essentially every record regardless of the real collection
speed - see `base/eiger_log.py`. A standard MX sweep is assumed instead, which is
what the shared client and GDA both do; pass explicit values for anything else.

Which number is "the dose"
--------------------------
`Max Dose`, which is the service's own default and what GDA uses. The Garman
limit of 30 MGy that staff judge a test crystal against is quoted on the same
basis.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

# What the service is asked for. GDA's dose_utils uses the same nominal flux.
NOMINAL_FLUX = 3.0e10
DOSE_FIELD = "Max Dose"

# A standard sweep. oscillation_start must not be 0 - the service returns 500.
DEFAULT_OSCILLATION = (1.0, 360.0)

# The development instance, on a workstation. The production service at
# i04-raddose serves GDA continuously and beamline setup has no business adding
# load to it, so development work points here by default.
DEV_API = "http://localhost:8000/api/v1.0"
PRODUCTION_API = "http://localhost:8000/api/v1.0"

# The module instructs staff to collect the test crystal at this dose. A
# collection well above it means the transmission was not what was intended.
TARGET_DOSE_MGY = 1.5

# Beyond this a test crystal is past the Garman limit and due for replacement.
GARMAN_LIMIT_MGY = 30.0


class DoseUnavailable(Exception):
    """The service could not be reached, or answered with something unusable."""


class DoseCalculator:
    """Dose for arming-log records, with one API call per beam configuration.

    Not thread-safe, and not meant to be: it is a per-run cache.
    """

    def __init__(self, api_url=DEV_API, timeout=30, log=None, crystal=None):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.log = log
        # Real parameters for a known test crystal give a better absolute number.
        # The service otherwise fills in generic defaults (78/78/36, 200
        # residues, 1 monomer). The trend is unaffected either way.
        self.crystal = crystal or {}
        self._rates = {}
        self.calls = 0

    def _note(self, level, message):
        if self.log is not None:
            getattr(self.log, level)(message)

    # -- the service ------------------------------------------------------

    def _get(self, params):
        query = urllib.parse.urlencode(params)
        url = f"{self.api_url}/getdose?{query}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 500 and float(params.get("oscillation_start", 1)) == 0:
                raise DoseUnavailable(
                    "oscillation_start=0 makes the service return 500; use 1"
                )
            raise DoseUnavailable(f"{url} returned HTTP {error.code}")
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise DoseUnavailable(f"Could not reach {self.api_url}: {error}")

        if DOSE_FIELD not in payload:
            raise DoseUnavailable(f"No '{DOSE_FIELD}' in the reply: {sorted(payload)}")
        return payload

    def rate(self, energy_kev, beam_x_um, beam_y_um, oscillation=DEFAULT_OSCILLATION):
        """MGy per second at NOMINAL_FLUX for one beam configuration.

        Rounded before it becomes a cache key: the beam size readback wobbles in
        the third decimal between collections that are otherwise identical, and
        without rounding every collection would be its own API call.
        """
        key = (
            round(float(energy_kev), 3),
            round(float(beam_x_um), 2),
            round(float(beam_y_um), 2),
            round(float(oscillation[0]), 2),
            round(float(oscillation[1]), 2),
        )
        if key in self._rates:
            return self._rates[key]

        params = {
            "flux": f"{NOMINAL_FLUX:.4g}",
            "beam_size_x": key[1],
            "beam_size_y": key[2],
            "energy_kev": key[0],
            "oscillation_start": key[3],
            "oscillation_end": key[4],
            "total_exposure_time": 1.0,
        }
        params.update(self.crystal)
        self.calls += 1
        rate = float(self._get(params)[DOSE_FIELD])
        self._rates[key] = rate
        self._note("debug", f"Dose rate for {key}: {rate:.6f} MGy/s")
        return rate

    # -- arming-log records ----------------------------------------------

    def exposure_seconds(self, entry):
        """Total X-ray exposure, which is what dose scales with.

        Deliberately `acquire_time_s` and not `acquire_period_s`: the period
        includes the detector's dead time between images, during which the
        crystal is still in the beam but the calculation the service performs is
        about delivered photons.
        """
        images = float(entry.get("number_images") or 0)
        each = float(entry.get("acquire_time_s") or 0)
        return images * each

    def dose(self, entry, oscillation=DEFAULT_OSCILLATION):
        """Dose in MGy for one armed collection.

        Raises DoseUnavailable rather than returning a wrong number: a dose that
        silently reads 0 because the flux was missing is worse than no column,
        because it would be summed into a lifetime total.
        """
        flux = float(entry.get("flux") or 0)
        exposure = self.exposure_seconds(entry)
        if flux <= 0:
            raise DoseUnavailable(
                f"No flux recorded for {entry.get('master_file')} - "
                "dose cannot be calculated from this record"
            )
        if exposure <= 0:
            raise DoseUnavailable(
                f"No exposure recorded for {entry.get('master_file')}"
            )

        rate = self.rate(
            float(entry["energy_ev"]) / 1000.0,
            float(entry["beamsize_h_um"]),
            float(entry["beamsize_v_um"]),
            oscillation,
        )
        return rate * (flux / NOMINAL_FLUX) * exposure

    def dose_for_collections(self, entries, oscillation=DEFAULT_OSCILLATION):
        """Per-collection doses and their total, skipping what cannot be read.

        Returns (rows, total, skipped). A record that cannot be calculated is
        reported rather than silently treated as zero.
        """
        rows, skipped = [], []
        for entry in entries:
            try:
                value = self.dose(entry, oscillation)
            except DoseUnavailable as error:
                skipped.append((entry.get("master_file"), str(error)))
                continue
            rows.append((entry, value))
        return rows, sum(value for _, value in rows), skipped

    # -- the cross-check the worked example used --------------------------

    def verify_scaling(self, entry, oscillation=DEFAULT_OSCILLATION):
        """Compare the scaled dose against a direct call at the real values.

        The whole tool rests on dose being linear in flux and exposure. This is
        how that was established, kept so it can be re-run rather than trusted.
        Returns (scaled, direct, percentage difference).
        """
        scaled = self.dose(entry, oscillation)
        params = {
            "flux": f"{float(entry['flux']):.6g}",
            "beam_size_x": round(float(entry["beamsize_h_um"]), 2),
            "beam_size_y": round(float(entry["beamsize_v_um"]), 2),
            "energy_kev": round(float(entry["energy_ev"]) / 1000.0, 3),
            "oscillation_start": oscillation[0],
            "oscillation_end": oscillation[1],
            "total_exposure_time": self.exposure_seconds(entry),
        }
        params.update(self.crystal)
        self.calls += 1
        direct = float(self._get(params)[DOSE_FIELD])
        difference = abs(scaled - direct) / direct * 100 if direct else float("nan")
        return scaled, direct, difference
