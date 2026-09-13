# RemoteAccess

Lists who is connected to the beamline workstations over NoMachine, so the staff
member can see who is on before handing over.

## Files

| File | What it does |
|---|---|
| `RemoteAccess.py` | Builds the session table. |
| `RA_ssh.py` | SSHes to each NX machine and runs `nxserver --list`. |
| `GUI_RemoteAccess.py` | Wizard pages and the table. |
| `GUI_RemoteAccess.yaml` | Wizard text and the session table layout. |

The YAML is named after the GUI file, so the GUI class sets `config_basename`.

## How it works

It SSHes to each machine in `nx_machines` (from the top-level config) as the
logged-in user and parses `nxserver --list`, then resolves each client IP to a
hostname and each username to a real name.

## Things that will catch you out

- **The password reaches the remote command line.** `RA_ssh.py:56` builds
  `echo '<password>' | sudo -S ...`, so it is visible in the remote process table
  and unescaped. Worth fixing.
- **Host keys are auto-accepted** (`AutoAddPolicy`).
- **Client IPs are sent to `ipinfo.io`** to resolve institutions. That is a
  third-party service receiving user IP addresses and is waiting on a data
  protection ruling.

## Open work

**B5** — since the NoMachine upgrade the list includes local sessions alongside
remote ones, which makes it misleading. The agreed fix is two tables,
discriminating on `Remote IP == "-"`.
