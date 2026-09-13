from BeamstopAnalysis import BeamstopAnalyzer
import yaml
import logging
import os

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Test")

# Load Configuration
with open("GUI_BeamstopAlignment.yaml") as f:
    config = yaml.safe_load(f)

# Override depth for testing so we find the files you collected
config["search_depth"] = 1500
# Ensure we check the right timeframe (48h covers yesterday and today)
config["search_hours"] = 48

analyzer = BeamstopAnalyzer(log)
results = analyzer.find_best_datasets(config)

print("\n--- DATASET SEARCH RESULTS ---")
print(list(results.keys()))

print("\n--- STARTING ANALYSIS ---")
output_dir = os.getcwd()

# 1. Extract Plot Options from YAML
plot_options = config.get("plot_options", {})

for label, dataset_entry in results.items():
    if dataset_entry:
        # 2. Pass plot_options to the function
        stats, img = analyzer.analyze_dataset(
            label, dataset_entry, output_dir, plot_options
        )
        print(f"Processed {label}:")
        print(f"  Stats: {stats}")
        print(f"  Image: {img}")
