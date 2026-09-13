"""Local sessions are not remote users (B5).

Since the NoMachine upgrade, the console sessions on the beamline machines
themselves appear in the same `nxserver --list` output as real remote users. For example:

    bl-ws001   1     consoleuser               -               <- console
    bl-ws002   0     gdm                       -               <- console
    bl-ws002   1002  remoteuser                192.0.2.1       <- genuinely remote

All three were listed together, so the table read as though three people were
connected from outside. The discriminator is the remote address: nxserver prints
"-" when there is not one.
"""

import logging

import pytest

from modules.RemoteAccess.RA_ssh import Manage_NX_Connections


@pytest.fixture
def manager():
    return Manage_NX_Connections(
        "testuser", [], "", logging.getLogger("remote-access-tests")
    )


def test_both_lists_start_with_the_same_header(manager):
    assert manager.sessions[0] == manager.HEADER
    assert manager.local_sessions[0] == manager.HEADER
    assert (
        manager.sessions[0] is not manager.local_sessions[0]
    ), "separate lists, or appending to one would show up in the other"


def test_nothing_found_means_header_only(manager):
    assert not manager.has_remote_sessions()
    assert not manager.has_local_sessions()


def test_a_row_makes_the_list_non_empty(manager):
    manager.sessions.append(["bl-ws002", "1002", "testuser"])
    assert manager.has_remote_sessions()
    assert not manager.has_local_sessions()


def test_a_local_session_is_recognised_by_its_missing_address():
    """The only thing distinguishing them in the nxserver output."""
    for address in ("-", "", "  "):
        assert address.strip() in ("-", ""), f"{address!r} should read as local"
    assert "192.0.2.1".strip() not in ("-", "")


def test_local_sessions_are_not_looked_up():
    """ipinfo.io was being asked about a literal hyphen, once per local session,
    and returning 404 every time."""
    import inspect

    source = inspect.getsource(Manage_NX_Connections.get_list_of_sessions)
    assert "is_local" in source
    guard = source[source.index("is_local =") :]
    assert guard.index("if is_local") < guard.index(
        "get_info_from_ip"
    ), "the local test must come before the geolocation lookup"
    assert guard.index("if is_local") < guard.index(
        "gethostbyaddr"
    ), "and before the reverse DNS lookup"


def test_the_module_reports_them_separately():
    import inspect

    from modules.RemoteAccess.RemoteAccess import RemoteAccess

    source = inspect.getsource(RemoteAccess)
    assert '"local_sessions"' in source
    assert '"nx_connections"' in source
    assert (
        "no_remote_message" in source
    ), "an empty remote table should say nobody is connected, not just be empty"
