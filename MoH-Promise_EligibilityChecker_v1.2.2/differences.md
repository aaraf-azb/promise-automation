# Differences between v1.2.1 and v1.2.2

This document details all differences between the code in v1.2.1 and v1.2.2.

---

## 1. Summary of Key Differences

| Feature / Logic | MoH-Promise_EligibilityChecker_v1.2.1 | MoH-Promise_EligibilityChecker_v1.2.2 |
| :--- | :--- | :--- |
| **Excel Skipping Logic** | Checks if Medicaid Number is in `processed_ids`. | Same (checks Medicaid Number), but with enhanced string cleaning and resilience to Excel edits. |
| **Medicaid Empty Value Handling** | Zero-pads empty values to `"0000000000"`. | Leaves empty/blank values as `""` to prevent invalid lookup loops. |
| **CSV Progress Loading** | Strict string match on `Medicaid Number` column. | Resilient: strips quotes, ignores case, and automatically zero-pads IDs (`.zfill(10)`) to match Excel formatting even if edited in Microsoft Excel. |
| **Windows File Lock Recovery** | Prone to `PermissionError` crash during backup rename. | Safe: releases the file handle before renaming mismatching CSV files. |
| **Payer Normalization** | returns `{""}` for `"WAIVER"` group. | returns `set()` (empty set) — **Resolved**. |
| **Waiver Payer Prioritization** | No sorting applied to extracted insurances. | Sorts insurances in `extract_results` so that any records containing `"WAIVER"` are placed last. |
| **Screenshot Filenames** | Prefixed with `"screenshot_"` (e.g., `screenshot_SMITH_JOHN_...`). | Starts directly with the patient's name (e.g., `SMITH_JOHN_...`) to allow natural alphabetical sorting in your file explorer. |

---

## 2. Code Comparison Diff (`main.py`)

Here is the exact code differences in `main.py`:

```diff
--- MoH-Promise_EligibilityChecker_v1.2.1/main.py
+++ MoH-Promise_EligibilityChecker_v1.2.2/main.py
@@ -122,7 +122,10 @@ def normalize_excel_row(row: dict) -> dict:
                 val_str = str(int(float(value))).strip()
             except ValueError:
                 val_str = str(value).strip()
-            normalized[key] = val_str.zfill(10)
+            if val_str == "":
+                normalized[key] = ""
+            else:
+                normalized[key] = val_str.zfill(10)
 
         # Standardize Date of Birth as MM/DD/YYYY string
         elif key == "Date of Birth":
@@ -194,7 +197,7 @@ def normalize_payer(contract: str) -> set:
     elif matched_group == "WELLNESS":
         return {"PA HEALTH AND WELLNESS"}
     elif matched_group == "WAIVER":
-        return {""}
+        return set()
         
     return {upper_name}
 
@@ -283,6 +286,14 @@
                     {"Insurance Name": name, "Begin Date": begin, "End Date": end}
                 )
 
+    # Sort result_rows so that records containing "WAIVER" are listed last
+    result_rows.sort(key=lambda x: "WAIVER" in x["Insurance Name"].upper())
+    
+    # Realign parallel lists with the sorted result_rows
+    insurance_names = [r["Insurance Name"] for r in result_rows]
+    begin_dates = [r["Begin Date"] for r in result_rows]
+    end_dates = [r["End Date"] for r in result_rows]
+
     return {
         "result_rows": result_rows,
         "insurance_names": insurance_names,
@@ -320,7 +331,7 @@ def check_results(
                 f"⚠️ Payer Mismatch Discrepancy: Contract '{row_contract.strip()}' does not match portal entry '{last_checked_insurance}'"
             )
 
-    # 1.1. Evaluate Waiver presence
+    # 1.5. Evaluate Waiver presence
     waiver_found = False
     for insurance_name in insurance_names:
         if "WAIVER" in insurance_name.upper():
@@ -443,27 +454,54 @@ def take_screenshot(page, output_folder, filename_prefix, log_callback=None) ->
 def setup_progress_tracking(input_path, output_headers):
     progress_file = input_path.parent / f"{input_path.stem}_progress.csv"
     processed_ids = set()
+    rows_count = 0
     file_exists = progress_file.exists()
 
     if file_exists:
         try:
-            with open(progress_file, newline="", encoding="utf-8-sig") as f:
-                reader = csv.DictReader(f)
-                for row in reader:
-                    member_id = (row.get("Medicaid Number") or "").strip()
-                    if member_id:
-                        processed_ids.add(member_id)
-
+            # 1. Read first line to verify headers match
             with open(progress_file, newline="", encoding="utf-8-sig") as f:
                 first_line = f.readline().strip()
-                expected_header = ",".join(output_headers)
-                if first_line != expected_header and first_line:
-                    progress_file.rename(progress_file.with_suffix(".csv.bak"))
-                    file_exists = False
-                    processed_ids.clear()
+            
+            # Parse the CSV header line safely (handling quotes and delimiters)
+            import csv as csv_parser
+            header_reader = csv_parser.reader([first_line])
+            actual_cols = next(header_reader, [])
+            actual_cols_clean = [c.strip().replace('"', '').lower() for c in actual_cols if c]
+            expected_cols_clean = [c.strip().lower() for c in output_headers if c]
+            
+            # We check if all expected columns are present in the actual columns
+            headers_match = all(col in actual_cols_clean for col in expected_cols_clean)
+            
+            if not headers_match and first_line:
+                # Header mismatch: rename file to .bak to start fresh
+                bak_file = progress_file.with_suffix(".csv.bak")
+                try:
+                    if bak_file.exists():
+                        bak_file.unlink() # remove old backup to prevent rename failure on Windows
+                    progress_file.rename(bak_file)
+                except Exception:
+                    pass
+                file_exists = False
+            else:
+                # Headers match: read all processed IDs (standardizing them to 10-digit strings)
+                with open(progress_file, newline="", encoding="utf-8-sig") as f:
+                    reader = csv.DictReader(f)
+                    for row in reader:
+                        # Find the Medicaid Number key resiliently
+                        member_id = ""
+                        for k, v in row.items():
+                            if k and k.strip().replace('"', '').lower() == "medicaid number":
+                                member_id = (v or "").strip().replace('"', '')
+                                break
+                        if member_id:
+                            # Standardize to 10-digit padded string
+                            processed_ids.add(member_id.zfill(10))
+                rows_count = len(processed_ids)
         except Exception:
             file_exists = False
             processed_ids.clear()
+            rows_count = 0
 
     mode = "a" if file_exists else "w"
     progress_f = open(progress_file, mode=mode, newline="", encoding="utf-8-sig")
@@ -471,7 +509,7 @@
     if not file_exists:
         progress_writer.writeheader()
 
-    return progress_file, processed_ids, progress_writer, progress_f
+    return progress_file, processed_ids, progress_writer, progress_f, rows_count
 
 
 # ----------------------------
@@ -506,7 +544,9 @@ def run_automation(
         # Read Excel using pandas
         try:
             df_in = pd.read_excel(input_path, sheet_name="Detail Data")
-            input_headers = [str(col).strip() for col in df_in.columns]
+            # Strip column headers in the DataFrame itself to avoid key mismatches
+            df_in.columns = [str(col).strip() for col in df_in.columns]
+            input_headers = list(df_in.columns)
             raw_rows = df_in.to_dict(orient="records")
             input_rows = [normalize_excel_row(r) for r in raw_rows]
             
@@ -549,13 +589,14 @@ def run_automation(
             # Immediately pre-fill/restore the output Excel file with existing progress
             write_output_excel(progress_file_raw, output_file, log_callback)
 
-        progress_file, processed_ids, progress_writer, progress_f = (
+        progress_file, processed_ids, progress_writer, progress_f, rows_count = (
             setup_progress_tracking(input_path, full_headers)
         )
 
         if has_historical_session and log_callback:
             log_callback(
-                f"📂 Resumed from previous run: {len(processed_ids)} records safely restored."
+                f"📂 Resumed from previous run: {rows_count} records safely restored."
             )
 
         try:
@@ -591,6 +631,7 @@ def run_automation(
                         )
                     break
 
+                # Skip completed rows based on the Medicaid Number
                 if member_id_raw in processed_ids:
                     if progress_callback:
                         progress_callback(
@@ -616,7 +657,8 @@ def run_automation(
                     )
                     progress_writer.writerow(output_row)
                     progress_f.flush()
-                    processed_ids.add(member_id_raw)
+                    if member_id_raw:
+                        processed_ids.add(member_id_raw)
                     if progress_callback:
                         progress_callback(
                             current=idx, total=len(input_rows), member_id=member_id_raw
@@ -682,7 +724,8 @@ def run_automation(
                     progress_writer.writerow(output_row)
                     progress_f.flush()
 
-                    processed_ids.add(member_id_raw)
+                    if member_id_raw:
+                        processed_ids.add(member_id_raw)
 
                     if progress_callback:
                         progress_callback(
@@ -704,7 +747,7 @@
                         screenshot_success = take_screenshot(
                             page=page,
                             output_folder=output_folder,
-                            filename_prefix=f"screenshot_{sanitize_filename(fullname)}_{member_id_raw}_{timestamp}",
+                            filename_prefix=f"{sanitize_filename(fullname)}_{member_id_raw}_{timestamp}",
                             log_callback=log_callback,
                         )
                         screenshot_taken = "Yes" if screenshot_success else "No"
```
