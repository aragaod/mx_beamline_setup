# Changelog

Thirteen years of `beamline_setup`: from Nathan Cowieson's wxPython application on
the Australian Synchrotron's MX beamlines in 2013, through a PyQt5 rewrite begun at
Diamond in 2019, to the application i04 runs every morning.

## Why it exists

David Aragao's account, recorded here because it explains most of the design
decisions that follow.

He was trained on setup and regular maintenance by the Principal Beamline
Scientist, **Tom Caradoc-Davies**, and asked to shadow the other senior instrument
scientists to learn how each of them troubleshot problems. Everyone did things a
little differently. Everyone kept their own notebook, or their own file, to
remember what needed doing.

The consequence was that the beamline was delivered to users a little different
every day — sometimes better, sometimes worse. That part is unavoidable: a
beamline depends on the machine and on a great many hardware and software
components, and no one keeps it at its best continuously.

What was avoidable was that **nobody could tell when a given task had last been
done**. So each morning came down to a guess, in one of two directions:

> Do it, because I do not trust when it was last done.
>
> Don't do it, because I am not the first in this week, so someone must already
> have done it.

And it was not fair to users. Diligent staff handed over a beamline in a better
state; less diligent staff handed over a worse one — with no threshold anywhere
that said whether what was being handed over cleared a minimum worth giving to
someone who had travelled to use it.

Nathan Cowieson overheard David making this argument to the PBS, and said: *"oh,
David is right, let me see what I can do to fix this."* He then went and did it.
The beamline setup application came out of that conversation, with Nathan as the
main developer and David contributing the requirements, ideas and small pieces of
code.

Both halves of the complaint became features, and both are still the point of the
application thirteen years later:

| the complaint, 2013 | the answer, and where it is now |
|---|---|
| nobody knows when a task was last done | run indicators beside every button, `*_lastrun` timestamps in redis, and a dated report per morning |
| no threshold for what is good enough to hand to a user | the good / warning / danger assessment on every parameter, added in June 2025 |

The second took twelve years to arrive.

The pre-2019 section is reconstructed from a 2013 source snapshot, because no
history exists to reconstruct from — see that section. Everything after is from 261 commits plus the
stored report archive. **Where the two
disagree, the commits win**: the redis hash has been deleted and has expired more
than once, so it under-reports early use and cannot show anything before June
2025 at all. That gap is why the archive is now something worth backing up (F16
in `PROGRESS.md`).

Versions here are eras, not tags. The project has never used release numbers; the
boundaries are where the application changed character.

---

## Before this repository — 2013 to 2019, the Australian Synchrotron

**Original author: Nathan Cowieson.** `beamline_setup.py` carries its own
provenance in the first lines of its docstring:

```
version 0.1
by Nathan Cowieson 10/04/13
```

Written for the two macromolecular crystallography beamlines, **MX1 and MX2**, at
the Australian Synchrotron, in **Python 2.7 and wxPython** (GTK on Linux). It ran
there for six years, from 2013 to 2019, and it worked.

The GitHub copy is a single upload made on 24 October 2013 and never added to;
development carried on at the Australian Synchrotron in a local repository that
was never pushed back. So what is described here is the application as it stood
in **October 2013**, six months after `version 0.1` — not as David inherited it,
and not as it was when it stopped running in 2019. The eleven modules are the
2013 set; there may well have been more by the end.

David Aragao contributed from the start — the requirements, ideas, and small
pieces of code — and later took over maintaining it. He is also in the staff
picker, alongside Tom Caradoc-Davies, Santosh Panjikar, Jason Price, Rachel
Williamson, Alan Riboldi-Tunnicliffe,  Daniel Eriksson, Jun Ashima, Stephen Harrop,
Christine Gee and Nathan himself.

Other contributors over the six years were making operational updates from MX1
and MX2 rather than changing the design. Nathan later moved to Diamond and is now
a colleague again.

### What was already there in 2013

More than is comfortable to admit. The rewrite changed the technology and the
organisation, but a fair bit of the design came straight across:

| 2013 | today |
|---|---|
| One module per task, each standalone | one directory per module |
| Buttons with indicators showing whether a step had been run | the tick/status system |
| `RedisHashMap('mx1_beamline_setup')`, keyed on `blconfig.ID` | `{BEAMLINE}:BeamlineSetup:hash` |
| `from beamline import variables as blconfig` | `from beamline import ID, redis` |
| "WHO ARE YOU?" staff picker | the login module |
| `FormatReport.py` — HTML with embedded images, pushed to an electronic logbook | `CreateReport` |
| `AlignBeam`, `RotationAxis`, `TestCrystal`, `CreateDirs` | same modules, same names |
| Images montaged and datestamped into a calibration directory | the per-module report folders |

Two details are worth pointing at directly.

**Redis was there from the start, and it was David's idea.** The modules needed to
talk to each other, and the obvious 2013 answer — write files and have the next
module read them — meant a mess of paths and permissions for what was really just
a handful of values. David argued for an in-memory database instead and wrote the
first examples of it. Nathan took the idea and built it in, settling on a redis
hash per beamline keyed on the beamline ID.

That arrangement is still here, and it is what made fourteen months of trend
analysis possible in 2026. The 2013 README lists it among the dependencies without
ceremony: *"A redis database holds variables to allow persistence across
sessions."*

**`RotationAxis.py` rotated through 270 degrees taking an image every 90**, and
analysed them to find the rotation axis relative to the camera cross-hairs. That
is the same four images the module still collects — and B4, in August 2026,
finally turned them back into a number after seven years of the Qt rewrite
storing them for a person to look at.

### What was lost in the rewrite, and is coming back

Three of the eleven modules present in October 2013 have no Qt equivalent, and two
are now on the backlog:

- **`CryoJet.py`** — cryojet alignment, with set points and the time of the last
  check logged. This is **F14**, proposed independently in 2026 before anyone
  looked at the 2013 source.
- **`SnapShot.py`** — harvested most of the process variables defining the state
  of the beamline and archived them. `Graphical_User_Interface_2025.py` in this
  repository still has a `Snapshot` entry where `RobotSamples` sits in the live
  UI, which is probably a half-finished attempt to bring it back.
- **`MakeComment.py`** — free-text staff comments pushed to the logbook with the
  report, deliberately not saved to the user's own directories.

`BeamCentre.py` — 628 lines of Fit2d-driven direct-beam, distance, pitch and yaw
calibration — has no Qt equivalent either. It is the largest single module of the
2013 system.

## v0 — 2019: the skeleton (June to November 2019, 32 commits)

David Aragao, alone, at Diamond — starting the PyQt5 rewrite of the Australian
Synchrotron system he had been running. A wxPython screenshot in the first README
gives away what it was a port *of*: Nathan's application, still in production at
MX1 and MX2 at the time.

Everything structural that the application still runs on was decided here:

- **One directory per module**, each with its own GUI class, logic class and YAML.
  Committed 6 September 2019 as an explicit reorganisation away from a single
  `modules` folder. Nine modules later, this has not needed changing.
- **Staff login**, and the `BLrelease` split between a production and a
  development configuration (5 November 2019). Still exactly how the two
  environments are separated.
- **Zoom-level crosshair configuration** read from `display.configuration`
  (6 September 2019) — the same file the rotation-axis work of 2026 reads.

Then it stopped. **2020 to 2023 produced seven commits in four years**, all
maintenance: an SSSD/LDAP change breaking username lookup (April 2022), and NX
starting to emit a licence-expiry banner that broke the session parsing
(January 2023, Jira SC-3701).

## v1 — 2024: it becomes a reporting tool (March to June 2024, 92 commits)

**The turning point, and it was a visitor who turned it.** Kate Smith was at
Diamond on sabbatical from SLS and committed from **15 March to 7 June 2024** —
61 commits, alongside David's 31. March and April 2024 remain the busiest two
months in the project's history.

Before this the application was a checklist that helped staff remember things.
After it, the checklist produced a record.

- **Reports to the eLog.** Kate's first commit is literally "initial commit —
  hard coded elog" (15 March). By 21 March there was a Jinja2 template, and
  images in the eLog the same day.
- **Redis as the join between modules.** David, 20 March: modules write their
  data and image paths to redis, and a reporting module collects all of it. This
  is what later made fourteen months of trend analysis possible.
- **Deployed to production on 19 April 2024** — Kate's commit "deploy to
  production and make icon". This is the date the application became a thing
  staff ran rather than a thing being written.
- Wizard pop-ups, `argparse` for prod/dev deployment, NX machines moved out of
  the code into YAML, and beamstop alignment groundwork from Ralf's suggestions.

Housekeeping that followed: `-X` added to SSH for the RHEL 8 upgrade (June 2024)
and **migration from Python 3.7 to 3.12** (26 June 2024).

## v2 — mid 2025: samples, emails and traffic lights (June 2025, 32 commits)

A second burst, David alone, and the point at which the report started making
judgements rather than only recording values.

- **SampleLoad** — fetches the latest robot dewar picture, overlays it, and reads
  which pucks are loaded.
- **EmailReady** — generates the email to users from the setup's own data, with a
  choice of template styles so that users who see it every visit keep reading it.
  Seasonal and industrial variants followed within the month.
- **Traffic lights.** 28 June 2025, "Major upgrade to add a green tick, warning or
  critical to the tables". Everything in the 2026 validation work descends from
  this commit.
- **Redis expiry raised from about 7 days to 2 months** (21 June 2025). Without
  this there would be no archive at all.
- Posting to the production eLog, with the server auto-selected by environment.

**The archive starts here**: the first stored report is SampleLoad on
**4 June 2025**, with TestCrystal the next day and AlignBeam, RotationAxis and
RemoteAccess by 12 June. Everything before is lost.

## v3 — August 2025: making it survive a bad morning (14 commits)

Small, unglamorous, and the reason the tool is trusted.

- Timeouts on the SSH connection and NX command for when a remote machine is down.
- Age checks on `proposal_positions.json` and the dewar picture, with pop-ups when
  they are stale — and, at Marco's request, pop-ups made harder to ignore.
- Hardcoded YAML paths removed from every module.
- Zoom driven to 7.5× for the pictures, after several setups had been recorded at
  1.0×.

## v4 — December 2025: beamstop alignment (20 commits)

`BeamstopAlignment` arrives with a montage, a table, its own assessment rules and
comparison against the previous setup. **First stored report 17 December 2025**,
which matches the commits to the day.

Images from here on are uploaded twice — low quality inline for email and
browsing, high quality behind a link.

## v5 — 2026: the audit, and making it measurable (August 2026, ~80 commits)

The largest body of work since 2024, and different in kind: rather than adding
modules, it went back over what the existing ones were actually asserting.

**One assessment engine.** Four divergent dispatchers were replaced by a single
`CHECK_SPECS` table. Replaying 200 stored day-pairs took danger rows from **641
to 68** — most of the reduction being checks that had been reporting danger every
morning for over a year, including `FLUX`, which had done so since 12 June 2025
because it was given one limit where the check needed two.

**Tests, from none to 869.** With a `tests/README.md` table saying what each file
would catch. Several bugs were found by writing them rather than by hitting them.

**Layered per-beamline YAML** — `<Module>.yaml` plus `<Module>.<beamline>.yaml`,
verified to resolve byte-identically for i04 before merging. This is the keystone
for the i04-1 port.

**A migration tool** for the fourteen months of stored reports, so consumers need
not read two shapes forever.

**Things the reports could not previously say**, added across August 2026:
sections in checklist order with skipped modules named; modules that find nothing
saying so; re-runs no longer overwriting the previous image; local NoMachine
sessions separated from genuinely remote users; AlignBeam refusing to photograph
a beamline with no beam on it; an on-call log for overtime claims.

**Absorbed dose beside ISa and Rmeas.** The test crystal's ISa fell from about 41
to 31 over July and August 2026 and the report presented it as the beamline
degrading; against cumulative dose, r = −0.84. Roughly 70% of it was the crystal
ageing as it should.

**The archive turned into an instrument.** `dev/trends.py` plots any stored
parameter against any other. On its first run it closed a question that had been
open since the audit — machine steering does not explain the beamstop position,
103 paired days, r = −0.013 — and found that the beamstop X drifts steadily with
time instead, about 50 µm over 103 days.

**A figure of merit for the rotation axis**, from the four images the module had
been collecting since 2019 without producing a number from them.

---

## When staff actually started using it

Two dates, and they are three years apart:

| | |
|---|---|
| First run by staff as a deployed tool | **19 April 2024** |
| First day still recoverable from redis | **4 June 2025** |

Since the archive begins, **210 distinct days** carry a report, over fourteen
months. That is roughly one morning in two — the beamline does not run a setup
every day, and the archive has lost stretches to expiry.

| month | days with a report | | month | days with a report |
|---|---|---|---|---|
| 2025-06 | 19 | | 2026-02 | 24 |
| 2025-07 | 17 | | 2026-03 | 11 |
| 2025-08 | 12 | | 2026-04 | 13 |
| 2025-09 | 14 | | 2026-05 | 15 |
| 2025-10 | 14 | | 2026-06 | 6 |
| 2025-11 | 9 | | 2026-07 | 20 |
| 2025-12 | 17 | | 2026-08 | 7 |
| 2026-01 | 12 | | | |

The February 2026 peak (24 days) and the June 2026 trough (6) track the run
schedule rather than anything about the application. August 2026 is low because
the beamline entered shutdown.

## Contributors

| | | when |
|---|---|---|
| **Nathan Cowieson** | original author | Australian Synchrotron, from 10 April 2013 |
| David Aragao | 225 commits | June 2019 to present, and the AS system before it |
| Kate Smith | 61 commits | 15 March to 7 June 2024, on sabbatical from SLS |

This table credits **design**, not commit count, and the two do not track each
other. Commit counts cover this repository only, which begins in 2019 and so
cannot represent Nathan's six years of authorship. Others have made small
operational changes at both facilities — bug fixes, text, behaviour tweaks — and
are in the git history rather than here.
