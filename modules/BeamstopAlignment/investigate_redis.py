from beamline import redis
import json
import time

# Configuration
LIST_KEY = "i04:eiger:collections"
SCHEMA_KEY = "i04:eiger:collections:schema"
DEPTH = 2000  # Look back 2000 entries to ensure we see a mix of states


def investigate():
    print(f"--- Investigating Redis Key: {LIST_KEY} ---")

    # 1. Get Schema
    schema_json = redis.get(SCHEMA_KEY)
    if not schema_json:
        print("CRITICAL: Schema not found!")
        return
    headers = json.loads(schema_json)

    # 2. Get Data
    raw_entries = redis.lrange(LIST_KEY, 0, DEPTH - 1)
    print(f"Retrieved {len(raw_entries)} entries.")

    # 3. Analyze States
    unique_states = {}  # Key: (id, msg), Value: Count

    for raw in raw_entries:
        try:
            entry = dict(zip(headers, json.loads(raw.decode("utf-8"))))

            s_id = entry.get("state_id")
            s_msg = entry.get("state_msg")

            # Create a signature
            sig = (s_id, s_msg)

            if sig not in unique_states:
                unique_states[sig] = 0
            unique_states[sig] += 1

        except Exception:
            continue

    print("\n--- Unique States Found ---")
    print(f"{'ID':<5} | {'Message':<20} | {'Count':<5}")
    print("-" * 35)

    for (sid, smsg), count in sorted(unique_states.items()):
        print(f"{str(sid):<5} | {str(smsg):<20} | {count:<5}")

    print("\n--- Recommendation ---")
    print("Identify the ID corresponding to 'Armed', 'Ready', or 'Acquire'.")
    print("Update 'GUI_BeamstopAlignment.yaml' -> valid_state_ids with this number.")


if __name__ == "__main__":
    investigate()
