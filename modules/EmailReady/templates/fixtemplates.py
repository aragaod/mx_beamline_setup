import os

# The list of files that still contain the 'p_names' typo
files_to_fix = [
    "email_template_S2_LunarNewYear.jinja2",
    "email_template_S3_Spring.jinja2",
    "email_template_S6_Diwali.jinja2",
    "email_template_S7_AustraliaDay.jinja2",
    "email_template_S9_StPatricksDay.jinja2",
    "email_template_S10_StAndrewsDay.jinja2",
]

text_to_find = "puck_info.p_names"
text_to_replace = "puck_info.puck_names"
files_changed = 0

print("--- Starting template fix script ---")

for filename in files_to_fix:
    # Check if the file actually exists before trying to open it
    if not os.path.exists(filename):
        print(f"WARNING: File not found, skipping: {filename}")
        continue

    try:
        # Read the content of the file
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()

        # Perform the replacement
        new_content = content.replace(text_to_find, text_to_replace)

        # Check if any change was actually made
        if new_content != content:
            # Write the corrected content back to the file
            with open(filename, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"SUCCESS: Fixed typo in {filename}")
            files_changed += 1
        else:
            print(f"INFO: No typo found in {filename} (already correct).")

    except Exception as e:
        print(f"ERROR: Could not process file {filename}. Reason: {e}")

print(f"--- Script finished. Total files fixed: {files_changed} ---")
