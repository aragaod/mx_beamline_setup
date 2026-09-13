"""The on-call log that feeds the monthly overtime report (F2).

Staff claiming weekend overtime have to remember, weeks later, which days they
were Local Contact. Every setup already knows. These tests cover the recording
side - one hash field per person per day, weekends flagged, and above all a
failure that never reaches the setup running around it.

The reading side lives in dev/oncall_report.py and is exercised here too, since
a report that miscounts weekends is worse than no report.
"""

import importlib.util
import os
import sys
import types
from datetime import datetime

import pytest
import yaml

from conftest import REPO_ROOT

sys.path.insert(0, REPO_ROOT)
from base.Config import Config  # noqa: E402


class FakeRedis:
    """Just enough of the redis hash interface, plus a way to make it fail."""

    def __init__(self, fail=False):
        self.hashes = {}
        self.expiries = {}
        self.fail = fail

    def hget(self, key, field):
        if self.fail:
            raise ConnectionError("redis is down")
        return self.hashes.get(key, {}).get(field)

    def hset(self, key, field, value):
        if self.fail:
            raise ConnectionError("redis is down")
        self.hashes.setdefault(key, {})[field] = value

    def hgetall(self, key):
        if self.fail:
            raise ConnectionError("redis is down")
        return {k.encode(): v for k, v in self.hashes.get(key, {}).items()}

    def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)

    def expire(self, key, seconds):
        self.expiries[key] = seconds


class Recorder:
    """A module stripped down to what record_oncall actually touches."""

    ID = "i04"
    # Taken from Config, which is where both Base classes inherit it from.
    ONCALL_KEY_SUFFIX = Config.ONCALL_KEY_SUFFIX
    ONCALL_EXPIRY_SECONDS = Config.ONCALL_EXPIRY_SECONDS
    oncall_key = Config.__dict__["oncall_key"]
    record_oncall = Config.__dict__["record_oncall"]

    def __init__(self, username="operator1"):
        self.username = username
        self.log = types.SimpleNamespace(
            debug=lambda *a, **k: None,
            warning=lambda *a, **k: self.warnings.append(a[0] if a else ""),
        )
        self.warnings = []


@pytest.fixture
def redis_and_module(monkeypatch):
    """record_oncall imports beamline.redis at call time, so stub the module."""

    def build(fail=False, username="operator1"):
        fake = FakeRedis(fail=fail)
        monkeypatch.setitem(
            sys.modules, "beamline", types.SimpleNamespace(redis=fake, ID="i04")
        )
        return fake, Recorder(username)

    return build


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def test_a_session_is_recorded_under_the_person_and_the_day(redis_and_module):
    redis, module = redis_and_module()
    module.record_oncall("session_started", "2026-08-29 08:12:00", date="20260829")

    stored = redis.hashes["i04:BeamlineSetup:oncall"]
    assert list(stored) == ["20260829_operator1"]
    entry = yaml.safe_load(stored["20260829_operator1"])
    assert entry["session_started"] == "2026-08-29 08:12:00"
    assert entry["username"] == "operator1"
    assert entry["date"] == "20260829"


def test_the_second_timestamp_joins_the_first_rather_than_replacing_it(
    redis_and_module,
):
    """Session start and report posted are one day's record, written far apart."""
    redis, module = redis_and_module()
    module.record_oncall("session_started", "08:12:00", date="20260829")
    module.record_oncall("report_posted", "11:47:00", date="20260829")

    entry = yaml.safe_load(
        redis.hashes["i04:BeamlineSetup:oncall"]["20260829_operator1"]
    )
    assert entry["session_started"] == "08:12:00"
    assert entry["report_posted"] == "11:47:00"


def test_two_people_on_the_same_day_get_separate_records(redis_and_module):
    """Setups get handed over; both people did the work."""
    redis, first = redis_and_module(username="operator1")
    second = Recorder(username="abc12345")
    first.record_oncall("session_started", "08:00:00", date="20260829")
    second.record_oncall("session_started", "14:00:00", date="20260829")

    assert sorted(redis.hashes["i04:BeamlineSetup:oncall"]) == [
        "20260829_abc12345",
        "20260829_operator1",
    ]


@pytest.mark.parametrize(
    "date,expected",
    [
        ("20260829", True),  # Saturday
        ("20260830", True),  # Sunday
        ("20260831", False),  # Monday
        ("20260828", False),  # Friday
    ],
)
def test_weekends_are_flagged_because_only_those_feed_a_claim(
    redis_and_module, date, expected
):
    redis, module = redis_and_module()
    module.record_oncall("session_started", "08:00:00", date=date)
    entry = yaml.safe_load(redis.hashes["i04:BeamlineSetup:oncall"][f"{date}_operator1"])
    assert entry["weekend"] is expected


def test_the_key_is_given_a_year_to_live(redis_and_module):
    """The report hash expires after 60 days; a claim cycle needs longer."""
    redis, module = redis_and_module()
    module.record_oncall("session_started", "08:00:00", date="20260829")
    assert redis.expiries["i04:BeamlineSetup:oncall"] == 365 * 24 * 60 * 60


def test_the_log_is_separate_from_the_report_hash():
    """Sharing the report key would inherit its 60-day expiry."""
    assert Config.ONCALL_KEY_SUFFIX == "BeamlineSetup:oncall"
    assert Config.ONCALL_KEY_SUFFIX != "BeamlineSetup:hash"


def test_a_missing_username_does_not_lose_the_day(redis_and_module):
    redis, module = redis_and_module()
    del module.username
    module.record_oncall("session_started", "08:00:00", date="20260829")
    assert "20260829_unknown" in redis.hashes["i04:BeamlineSetup:oncall"]


def test_the_date_defaults_to_today(redis_and_module):
    redis, module = redis_and_module()
    module.record_oncall("session_started", "08:00:00")
    today = datetime.now().strftime("%Y%m%d")
    assert f"{today}_operator1" in redis.hashes["i04:BeamlineSetup:oncall"]


# --------------------------------------------------------------------------
# Failure must never reach the setup
# --------------------------------------------------------------------------


def test_a_dead_redis_does_not_stop_a_setup(redis_and_module):
    """This runs at login. Bookkeeping must not be able to block the morning."""
    _, module = redis_and_module(fail=True)
    assert module.record_oncall("session_started", "08:00:00") is None
    assert module.warnings, "the failure should still be logged"


def test_corrupt_existing_data_is_replaced_not_propagated(redis_and_module):
    redis, module = redis_and_module()
    redis.hashes["i04:BeamlineSetup:oncall"] = {"20260829_operator1": "not: [a, dict"}
    module.record_oncall("session_started", "08:00:00", date="20260829")
    entry = yaml.safe_load(
        redis.hashes["i04:BeamlineSetup:oncall"]["20260829_operator1"]
    )
    assert entry["session_started"] == "08:00:00"


def test_a_stored_scalar_does_not_become_an_attribute_error(redis_and_module):
    """Anything that is not a dictionary starts a fresh record."""
    redis, module = redis_and_module()
    redis.hashes["i04:BeamlineSetup:oncall"] = {"20260829_operator1": "42"}
    module.record_oncall("session_started", "08:00:00", date="20260829")
    entry = yaml.safe_load(
        redis.hashes["i04:BeamlineSetup:oncall"]["20260829_operator1"]
    )
    assert isinstance(entry, dict)
    assert entry["session_started"] == "08:00:00"


# --------------------------------------------------------------------------
# Both timestamps are actually wired up
# --------------------------------------------------------------------------


def test_the_main_window_can_actually_record_the_session_start():
    """The check that was missing, and it cost a crash on startup.

    The old version of this test read `beamline_setup.py` and asserted the call
    was in the source. It was - and the application still died on launch with

        AttributeError: 'BL_MainWindow' object has no attribute 'record_oncall'

    because there are two sibling Base classes. Modules inherit
    base/Modules.py:Base; the main window inherits base/Application.py:Base; and
    neither can see the other's methods. The method now lives on Config, which
    both inherit, and this asserts that on the real class rather than on its text.
    """
    from beamline_setup import BL_MainWindow

    assert hasattr(BL_MainWindow, "record_oncall")
    assert hasattr(BL_MainWindow, "oncall_key")


def test_both_base_classes_can_record_on_call():
    """Whichever half of the application wants to write a timestamp, it can."""
    from base.Application import Base as ApplicationBase
    from base.Config import Config
    from base.Modules import Base as ModuleBase

    for owner in (Config, ApplicationBase, ModuleBase):
        assert hasattr(owner, "record_oncall"), owner


def test_the_session_start_is_recorded_at_login():
    source = open(os.path.join(REPO_ROOT, "beamline_setup.py")).read()
    assert 'record_oncall(\n            "session_started"' in source


def test_the_report_post_is_recorded_only_on_success():
    """A failed eLog post is not a finished setup, so it must not be stamped."""
    source = open(
        os.path.join(REPO_ROOT, "modules", "CreateReport", "CreateReport.py")
    ).read()
    posted = source.index('record_oncall(\n                        "report_posted"')
    guard = source.rindex("if response.status_code == 200:", 0, posted)
    assert "else" not in source[guard:posted]


# --------------------------------------------------------------------------
# The reporting tool
# --------------------------------------------------------------------------


@pytest.fixture
def report_tool(monkeypatch):
    """Import dev/oncall_report.py against a fake beamline module."""
    fake = FakeRedis()
    monkeypatch.setitem(
        sys.modules, "beamline", types.SimpleNamespace(redis=fake, ID="i04")
    )
    path = os.path.join(REPO_ROOT, "dev", "oncall_report.py")
    spec = importlib.util.spec_from_file_location("oncall_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return fake, module


def add(redis, date, username, weekend=None, **fields):
    entry = {"date": date, "username": username, **fields}
    entry["weekend"] = (
        weekend
        if weekend is not None
        else datetime.strptime(date, "%Y%m%d").weekday() >= 5
    )
    redis.hashes.setdefault("i04:BeamlineSetup:oncall", {})[f"{date}_{username}"] = (
        yaml.safe_dump(entry)
    )


def test_the_report_narrows_to_one_month(report_tool):
    redis, tool = report_tool
    add(redis, "20260829", "operator1")
    add(redis, "20260901", "operator1")
    assert [e["date"] for e in tool.load(month="2026-08")] == ["20260829"]


def test_the_report_narrows_to_one_person(report_tool):
    redis, tool = report_tool
    add(redis, "20260829", "operator1")
    add(redis, "20260829", "abc12345")
    assert [e["username"] for e in tool.load(user="operator1")] == ["operator1"]


def test_sessions_come_back_in_date_order(report_tool):
    redis, tool = report_tool
    for date in ("20260830", "20260828", "20260829"):
        add(redis, date, "operator1")
    assert [e["date"] for e in tool.load()] == ["20260828", "20260829", "20260830"]


def test_the_month_filter_accepts_the_hyphenated_form(report_tool):
    """--month is typed as 2026-08 but the stored dates are 20260829."""
    redis, tool = report_tool
    add(redis, "20260829", "operator1")
    assert len(tool.load(month="2026-08")) == 1


def test_a_corrupt_entry_is_skipped_rather_than_crashing_the_report(report_tool):
    redis, tool = report_tool
    add(redis, "20260829", "operator1")
    redis.hashes["i04:BeamlineSetup:oncall"]["broken"] = "not: [valid"
    redis.hashes["i04:BeamlineSetup:oncall"]["scalar"] = "7"
    assert len(tool.load()) == 1


def test_the_default_month_is_the_one_just_gone(report_tool):
    """A claim is made in arrears, so the useful default is last month."""
    _, tool = report_tool
    month = tool.previous_month()
    now = datetime.now()
    expected = (
        f"{now.year}-{now.month - 1:02d}" if now.month > 1 else f"{now.year - 1}-12"
    )
    assert month == expected


def test_the_report_prints_the_weekend_count(report_tool, capsys):
    redis, tool = report_tool
    add(redis, "20260829", "operator1", session_started="2026-08-29 08:00:00")  # Sat
    add(redis, "20260830", "operator1", session_started="2026-08-30 08:00:00")  # Sun
    add(redis, "20260831", "operator1", session_started="2026-08-31 08:00:00")  # Mon
    tool.report(tool.load())
    printed = capsys.readouterr().out
    assert "3 setups, 2 at the weekend" in printed


def test_a_setup_with_no_report_posted_still_appears(report_tool, capsys):
    """An abandoned setup is still time worked, and worth seeing."""
    redis, tool = report_tool
    add(redis, "20260829", "operator1", session_started="2026-08-29 08:00:00")
    tool.report(tool.load())
    printed = capsys.readouterr().out
    assert "not posted" in printed
    assert "20260829" in printed


# --------------------------------------------------------------------------
# Development must not write into the production record
# --------------------------------------------------------------------------


def test_a_development_run_writes_to_its_own_key(redis_and_module):
    """Otherwise testing the app puts test entries in someone's overtime claim."""
    redis, module = redis_and_module()
    module.redis_hash = "i04:BeamlineSetup:hash:dev"
    module.record_oncall("session_started", "08:00:00", date="20260829")
    assert list(redis.hashes) == ["i04:BeamlineSetup:oncall:dev"]


def test_a_production_run_writes_to_the_plain_key(redis_and_module):
    redis, module = redis_and_module()
    module.redis_hash = "i04:BeamlineSetup:hash"
    module.record_oncall("session_started", "08:00:00", date="20260829")
    assert list(redis.hashes) == ["i04:BeamlineSetup:oncall"]


def test_no_report_hash_at_all_still_gives_a_key(redis_and_module):
    _, module = redis_and_module()
    assert module.oncall_key() == "i04:BeamlineSetup:oncall"
