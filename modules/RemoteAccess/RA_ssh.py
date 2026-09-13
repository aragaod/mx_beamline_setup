"""
Placeholder implementation for NX Remote Access session management.

In production at Diamond, this module connects to beamline workstations via SSH
to query NoMachine (NX) server sessions for active users.

For public and external use, facility-specific implementations should adapt
Manage_NX_Connections to query their local remote display infrastructure
(e.g., NoMachine NX, Apache Guacamole, FastX, or ThinLinc).
"""


class Manage_NX_Connections(object):
    def __init__(self, fedid, hostnames, password, log):
        self.fedid = fedid
        self.pw = password
        self.nx_machines = hostnames
        self.log = log
        self.sessions = [
            [
                "Beamline Machine",
                "NX connection ID",
                "FedID",
                "Name",
                "IP address",
                "City",
                "Country",
                "Remote Hostname",
            ]
        ]

    def get_list_of_sessions(self):
        """
        Return the list of current remote sessions.
        Returns the header table; RemoteAccess module gracefully handles
        the absence of active sessions.
        """
        self.log.info(
            "Manage_NX_Connections: placeholder active - returning empty session list."
        )
        return self.sessions
