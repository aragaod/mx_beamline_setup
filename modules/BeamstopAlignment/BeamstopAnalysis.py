import json
import logging
import os
import time
import h5py
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from matplotlib.ticker import MaxNLocator, FormatStrFormatter
from beamline import redis
from PIL import Image
import hdf5plugin
from datetime import datetime
import re

# --- SILENCE NOISY LIBRARIES ---
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("h5py").setLevel(logging.WARNING)


def get_scalar(h5_dataset):
    value = h5_dataset[()]
    if isinstance(value, np.ndarray):
        return value.item()
    return value


class MontageGenerator:
    """Generates analysis plots matching original beamstop-qc layout."""

    def __init__(self, master_filepath, log):
        self.log = log
        if not os.path.exists(master_filepath):
            raise FileNotFoundError(
                f"The specified file does not exist: {master_filepath}"
            )

        self.master_filepath = master_filepath
        self.beam_info = {}
        self.constants = {}
        self.image_array = None
        self._load_data()

    def _load_data(self):
        self.log.info(f"Processing file: {self.master_filepath}")
        PATHS = {
            "data": "/entry/data/data",
            "beam_center_x": "/entry/instrument/detector/beam_center_x",
            "beam_center_y": "/entry/instrument/detector/beam_center_y",
            "det_distance": "/entry/instrument/detector_z/det_z",
            "wavelength": "/entry/instrument/beam/incident_wavelength",
            "pixel_size_y": "/entry/instrument/detector/y_pixel_size",
        }
        with h5py.File(self.master_filepath, "r") as hf:
            self.beam_info = {
                "beam_x_px": get_scalar(hf[PATHS["beam_center_x"]]),
                "beam_y_px": get_scalar(hf[PATHS["beam_center_y"]]),
            }
            self.beam_info["beam_x_int"] = int(round(self.beam_info["beam_x_px"]))
            self.beam_info["beam_y_int"] = int(round(self.beam_info["beam_y_px"]))
            try:
                pixel_size_m = get_scalar(hf[PATHS["pixel_size_y"]])
                pixel_size_mm = pixel_size_m * 1000
            except KeyError:
                pixel_size_mm = 0.075
            self.constants = {
                "det_dist_mm": get_scalar(hf[PATHS["det_distance"]]),
                "wavelength_a": get_scalar(hf[PATHS["wavelength"]]),
                "PIXEL_SIZE_MM": pixel_size_mm,
            }
            self.image_array = hf[PATHS["data"]][0, :, :]

        if self.image_array.dtype == np.int32:
            self.constants["GAP_SENTINEL"] = 2**31 - 1
        elif self.image_array.dtype == np.int16:
            self.constants["GAP_SENTINEL"] = 2**15 - 1
        else:
            self.constants["GAP_SENTINEL"] = -1

    def plot_1d_profile(self, ax, slice_type):
        beam_x_int, beam_y_int = (
            self.beam_info["beam_x_int"],
            self.beam_info["beam_y_int"],
        )
        GAP_SENTINEL = self.constants["GAP_SENTINEL"]
        det_dist_mm = self.constants["det_dist_mm"]
        wavelength_a = self.constants["wavelength_a"]
        PIXEL_SIZE_MM = self.constants["PIXEL_SIZE_MM"]

        profile_slice = np.array([])
        title = ""
        try:
            if slice_type == "vertical":
                title = "Vertical Profile (Downwards)"
                profile_slice = self.image_array[beam_y_int:, beam_x_int]
            elif slice_type == "horizontal":
                title = "Horizontal Profile (Rightwards)"
                profile_slice = self.image_array[beam_y_int, beam_x_int:]
            elif slice_type == "diagonal":
                title = "Diagonal Profile"
                end_x, end_y = (
                    self.image_array.shape[1] - 1,
                    self.image_array.shape[0] - 1,
                )
                num = int(np.hypot(end_x - beam_x_int, end_y - beam_y_int))
                x_idx = np.linspace(beam_x_int, end_x, num).astype(int)
                y_idx = np.linspace(beam_y_int, end_y, num).astype(int)
                profile_slice = self.image_array[y_idx, x_idx]
        except IndexError:
            return

        x_axis = np.arange(len(profile_slice))
        valid_mask = profile_slice < GAP_SENTINEL

        ax.plot(
            x_axis[valid_mask],
            profile_slice[valid_mask],
            label="Intensity",
            linewidth=1.5,
        )

        gap_indices = np.where(~valid_mask)[0]
        if gap_indices.size > 0:
            contiguous_gaps = np.split(
                gap_indices, np.where(np.diff(gap_indices) > 1)[0] + 1
            )
            for i, gap_group in enumerate(contiguous_gaps):
                label = "Detector Gaps" if i == 0 else None
                if gap_group.size > 0:
                    ax.axvspan(
                        gap_group[0],
                        gap_group[-1],
                        color="lightgray",
                        alpha=0.5,
                        label=label,
                    )

        ax.set_title(title, fontsize=12, weight="bold", pad=35)
        ax.set_yscale("log")
        ax.set_ylabel("Intensity")
        ax.set_xlabel("Radial Distance from Beam Center (pixels)")
        ax.grid(True, linestyle="--", alpha=0.5)
        if gap_indices.size > 0:
            ax.legend(fontsize=9, loc="upper right")

        def resolution_to_pixel(res):
            try:
                if res <= 0:
                    return -1
                sintheta = wavelength_a / (2 * res)
                if sintheta > 1:
                    return -1
                theta = np.arcsin(sintheta)
                r_mm = det_dist_mm * np.tan(2 * theta)
                return r_mm / PIXEL_SIZE_MM
            except:
                return -1

        ax.text(
            0.5,
            1.05,
            "Resolution (d-spacing) [Å]",
            ha="center",
            va="bottom",
            transform=ax.transAxes,
            fontsize=10,
        )
        resolution_ticks = [100, 10, 3.5, 2.0, 1.5, 1.0, 0.8]
        xmin, xmax = ax.get_xlim()
        for res_value in resolution_ticks:
            px = resolution_to_pixel(res_value)
            if xmin <= px <= xmax:
                ax.axvline(x=px, color="gray", linestyle=":", linewidth=1, zorder=0)
                label = f"{res_value:.1f}" if res_value < 10 else f"{res_value:.0f}"
                bbox_props = dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    alpha=0.7,
                    edgecolor="none",
                )
                ax.text(
                    px,
                    0.99,
                    label,
                    ha="center",
                    va="top",
                    transform=ax.get_xaxis_transform(),
                    fontsize=8,
                    bbox=bbox_props,
                )

    def plot_2d_center(self, ax, options):
        beam_x_px, beam_y_px = self.beam_info["beam_x_px"], self.beam_info["beam_y_px"]
        GAP_SENTINEL = self.constants["GAP_SENTINEL"]

        box_width = options.get("box_width", 60)
        box_height = options.get("box_height", 70)
        low_intensity_threshold = options.get("threshold", 8)
        bin_size = options.get("bin_size", 2)
        ann_threshold = options.get("annotation_threshold", 75)

        box_half_width, box_half_height = box_width // 2, box_height // 2
        beam_x_int, beam_y_int = (
            self.beam_info["beam_x_int"],
            self.beam_info["beam_y_int"],
        )

        img_h, img_w = self.image_array.shape
        y_start, y_end = max(0, beam_y_int - box_half_height), min(
            img_h, beam_y_int + box_half_height
        )
        x_start, x_end = max(0, beam_x_int - box_half_width), min(
            img_w, beam_x_int + box_half_width
        )

        roi_data = self.image_array[y_start:y_end, x_start:x_end]
        roi_data_filtered = roi_data.astype(float)
        roi_data_filtered[
            (roi_data_filtered >= GAP_SENTINEL)
            | (roi_data_filtered <= low_intensity_threshold)
        ] = np.nan

        vmin = low_intensity_threshold + 1
        with np.errstate(all="ignore"):
            vmax = np.nanmax(roi_data_filtered)

        im = None
        if not np.isnan(vmax) and vmax > vmin:
            cmap_name = options.get("cmap", "Greys")
            try:
                cmap = plt.get_cmap(cmap_name)
            except:
                cmap = plt.get_cmap("Greys")
            cmap.set_bad(color="white")
            im = ax.imshow(
                roi_data_filtered, cmap=cmap, norm=LogNorm(vmin=vmin, vmax=vmax)
            )

            for r in range(0, roi_data.shape[0], bin_size):
                for c in range(0, roi_data.shape[1], bin_size):
                    block = roi_data[r : r + bin_size, c : c + bin_size]
                    valid = block[block < GAP_SENTINEL]
                    if valid.size > 0:
                        mean_val = np.mean(valid)
                        if mean_val > ann_threshold:
                            color = "white" if cmap_name == "Greys" else "red"
                            ax.text(
                                c + bin_size / 2,
                                r + bin_size / 2,
                                f"{mean_val:.0f}",
                                ha="center",
                                va="center",
                                color=color,
                                fontsize=6,
                            )

        center_x_in_roi, center_y_in_roi = beam_x_px - x_start, beam_y_px - y_start
        ax.plot(
            center_x_in_roi, center_y_in_roi, "r+", markersize=12, label="Beam Center"
        )

        title = f"Beam Center ({box_width}x{box_height})"
        ax.text(
            0.5,
            1.15,
            title,
            ha="center",
            va="bottom",
            transform=ax.transAxes,
            fontsize=12,
            weight="bold",
        )

        ax.set_xlabel("X Pixel (relative)")
        ax.set_ylabel("Y Pixel (relative)")
        ax.legend(loc="lower left", fontsize=8, framealpha=0.7)
        return im, vmin, vmax

    def create_montage(self, options, timestamp_str=None):
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(16, 6),
            gridspec_kw={"width_ratios": [1, 2.5], "wspace": 0.25},
        )

        im, vmin, vmax = self.plot_2d_center(axes[0], options)
        if im:
            cbar = fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.04)
            cbar.locator = MaxNLocator(nbins=3)
            cbar.update_ticks()

        profile_type = options.get("montage_type", "diagonal")
        self.plot_1d_profile(axes[1], profile_type)

        fig.suptitle(os.path.basename(self.master_filepath), fontsize=14, y=1.05)
        plt.subplots_adjust(left=0.05, right=0.95, top=0.80, bottom=0.15)

        if timestamp_str:
            fig.text(
                0.99,
                0.01,
                f"Collected: {timestamp_str}",
                ha="right",
                va="bottom",
                fontsize=8,
                color="gray",
            )

        formatted_path = self.master_filepath
        try:
            parts = self.master_filepath.split("/")
            if len(parts) > 5 and parts[1] == "dls":
                parts[5] = r"$\bf{" + parts[5] + "}$"
                formatted_path = "/".join(parts)
        except Exception:
            pass

        fig.text(
            0.01, 0.01, formatted_path, ha="left", va="bottom", fontsize=8, color="gray"
        )

        return fig


class BeamstopAnalyzer:
    def __init__(self, log_handle):
        self.log = log_handle
        self.redis = redis

    def find_best_datasets(self, config):
        definitions = config.get("beamstop_definitions", {})
        list_key = config.get("redis_list_key", "i04:eiger:collections")
        schema_key = config.get("redis_schema_key", "i04:eiger:collections:schema")

        search_hours = config.get("search_hours", 12)
        cutoff_time = time.time() - (search_hours * 3600)
        depth = config.get("search_depth", 500)
        valid_states = config.get("valid_state_ids", [1])

        self.log.info(
            f"Redis Query: Depth={depth}, MaxAge={search_hours}h, ValidStates={valid_states}"
        )

        try:
            schema_json = self.redis.get(schema_key)
            if not schema_json:
                return {}
            headers = json.loads(schema_json)
            raw_entries = self.redis.lrange(list_key, 0, depth - 1)
        except Exception as e:
            self.log.error(f"Redis Error: {e}")
            return {}

        parsed_collections = []
        for raw in raw_entries:
            try:
                entry = dict(zip(headers, json.loads(raw.decode("utf-8"))))
                if entry.get("unix_time", 0) < cutoff_time:
                    continue
                parsed_collections.append(entry)
            except:
                continue

        found_datasets = {}
        for def_key, def_val in definitions.items():
            target_dist = def_val["approx_distance"]
            tol = def_val["distance_tolerance"]
            patterns = def_val.get("filename_patterns", [])
            if not patterns and "filename_pattern" in def_val:
                patterns = [def_val["filename_pattern"]]
            req_trans = def_val.get("required_transmission", 100.0)

            candidates = []
            for col in parsed_collections:
                if col.get("state_id") not in valid_states:
                    continue
                if abs(col.get("transmission_pct", 0) - req_trans) > 0.1:
                    continue
                if abs(col.get("beamstop_z_pos", -999) - target_dist) > tol:
                    continue

                fname = col.get("filename", "")
                if any(p in fname for p in patterns) and col.get("master_file"):
                    candidates.append(col)

            if candidates:
                candidates.sort(key=lambda x: x.get("unix_time", 0), reverse=True)
                found_datasets[def_key] = candidates[0]
                ts = candidates[0]["unix_time"]
                readable_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
                self.log.info(
                    f"[{def_key}] Match: {candidates[0]['filename']} ({readable_time})"
                )
            else:
                self.log.warning(f"[{def_key}] No match found in last {search_hours}h")

        return found_datasets

    def analyze_dataset(self, label, dataset_entry, output_dir, config_options):
        master_file_path = dataset_entry.get("master_file")
        self.log.info(f"Analyzing {label}: {master_file_path}")

        defaults = {
            "box_width": 90,
            "box_height": 70,
            "threshold": 8,
            "cmap": "Greys",
            "annotation_threshold": 75,
            "bin_size": 2,
            "montage_type": "diagonal",
        }
        plot_options = {**defaults, **config_options}

        stats = {}
        image_path = ""

        try:
            raw_x = dataset_entry.get("beamstop_x_pos", "N/A")
            raw_y = dataset_entry.get("beamstop_y_pos", "N/A")
            stats[f"BS_X_{label}"] = raw_x
            stats[f"BS_Y_{label}"] = raw_y
            stats[f"BS_Z_{label}"] = dataset_entry.get("beamstop_z_pos", "N/A")

            unix_ts = dataset_entry.get("unix_time", time.time())
            ts_str = datetime.fromtimestamp(unix_ts).strftime("%d-%b-%Y %H:%M")

            gen = MontageGenerator(master_file_path, self.log)
            fig = gen.create_montage(plot_options, timestamp_str=ts_str)

            def fmt(val):
                return f"{val:.2f}" if isinstance(val, (int, float)) else str(val)

            title_str = f"{label} ({os.path.basename(master_file_path)}) - X:{fmt(raw_x)}, Y:{fmt(raw_y)}"
            fig.suptitle(title_str, fontsize=14, fontweight="bold", y=0.98)

            filename = f"{label}_beamstop.png"
            image_path = os.path.join(output_dir, filename)
            fig.savefig(image_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
        except Exception as e:
            self.log.error(f"Failed to analyze {master_file_path}: {e}")

        return stats, image_path

    def stitch_images(self, image_list, output_path):
        """Combines images vertically (Top to Bottom)."""
        try:
            images = [Image.open(p) for p in image_list if os.path.exists(p)]
            if not images:
                return None

            # For Vertical stacking:
            # Max width is the width of the widest image
            max_width = max(i.size[0] for i in images)
            # Total height is the sum of all heights
            total_height = sum(i.size[1] for i in images)

            new_im = Image.new("RGB", (max_width, total_height), color=(255, 255, 255))

            y_offset = 0
            for im in images:
                # Center images horizontally or left align? Left align is simpler (0, y)
                new_im.paste(im, (0, y_offset))
                y_offset += im.size[1]

            new_im.save(output_path)
            return output_path
        except Exception as e:
            self.log.error(f"Stitching failed: {e}")
            return None

    def check_consistency(self, config):
        """Checks beamlineParameters for HighRes/Standard consistency."""
        bl_params_file = config.get(
            "beamline_parameters_path",
            "/dls_sw/i04/software/daq_configuration/domain/beamlineParameters",
        )
        self.log.info(f"Checking consistency in: {bl_params_file}")

        if not os.path.exists(bl_params_file):
            return False, f"File not found: {bl_params_file}"

        params = {}
        keys_to_find = [
            "in_beam_x_STANDARD",
            "in_beam_y_STANDARD",
            "in_beam_x_HIGHRES",
            "in_beam_y_HIGHRES",
        ]

        try:
            with open(bl_params_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    clean_line = line.split("#")[0].strip()
                    for key in keys_to_find:
                        if key in clean_line:
                            match = re.search(
                                rf"{key}\s*=\s*([-+]?\d*\.\d+|\d+)", clean_line
                            )
                            if match:
                                params[key] = float(match.group(1))

            missing = [k for k in keys_to_find if k not in params]
            if missing:
                return False, f"Missing values: {', '.join(missing)}"

            x_match = (
                abs(params["in_beam_x_STANDARD"] - params["in_beam_x_HIGHRES"]) < 0.001
            )
            y_match = (
                abs(params["in_beam_y_STANDARD"] - params["in_beam_y_HIGHRES"]) < 0.001
            )

            if x_match and y_match:
                return True, "Consistent"
            else:
                msg = "MISMATCH:\n"
                if not x_match:
                    msg += f"X: Std({params['in_beam_x_STANDARD']}) != HiRes({params['in_beam_x_HIGHRES']})\n"
                if not y_match:
                    msg += f"Y: Std({params['in_beam_y_STANDARD']}) != HiRes({params['in_beam_y_HIGHRES']})"
                return False, msg
        except Exception as e:
            return False, f"Error: {e}"
