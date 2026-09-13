#!/bin/bash
# Beamline Setup Launcher script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

export BLrelease=${1:-production}
export NESTED_RUN=${2}

echo "Launching ${BLrelease} beamline setup QC from ${SCRIPT_DIR}"

# If a custom environment script is specified, source it
if [[ -n "${BEAMLINE_SETUP_ENV}" && -f "${BEAMLINE_SETUP_ENV}" ]]; then
    echo "Sourcing environment from ${BEAMLINE_SETUP_ENV}"
    source "${BEAMLINE_SETUP_ENV}"
fi

python3 -u beamline_setup.py

unset BLrelease
unset NESTED_RUN
