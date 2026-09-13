from BeamstopAnalysis import BeamstopAnalyzer
import logging
import yaml

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Test")

# Config mocking
config = {
    # Point to the real file for the test
    "beamline_parameters_path": "/dls_sw/i04/software/daq_configuration/domain/beamlineParameters"
}

analyzer = BeamstopAnalyzer(log)
is_consistent, msg = analyzer.check_consistency(config)

print(f"\nResult: {is_consistent}")
print(f"Message: {msg}")
