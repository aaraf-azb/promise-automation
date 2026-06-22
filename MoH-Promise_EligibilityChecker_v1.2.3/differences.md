# Differences between v1.2.2 and v1.2.3

This document details all differences between the code in v1.2.2 and v1.2.3.

---

## 1. Summary of Key Differences

| Feature / Logic | MoH-Promise_EligibilityChecker_v1.2.2 | MoH-Promise_EligibilityChecker_v1.2.3 |
| :--- | :--- | :--- |
| **Excel Skipping Logic** | Checks if Medicaid Number is in `processed_ids`, potentially skipping duplicate Medicaid Numbers on different contracts. | Checks the unique serial number (first column, read as `Unnamed: 0`) in `processed_ids` to support multiple contracts for the same patient. |
| **CSV Progress Loading** | Standardizes and loads processed IDs based on the `Medicaid Number` column. | Resilient: reads the unique serial number from the first column of the progress file to prevent incorrect skips. |
| **Row Order Preservation** | Appends rows to the final Excel in the order they were processed, which mixes up sequence on stop/resume. | **Merge-Back**: Merges progress details back into the original spreadsheet structure. The final Excel rows follow the exact relative order of the original input file (excluding any unprocessed rows). |

---

## 2. Code Comparison Diff (`main.py`)

Here is the exact code differences in `main.py`:

```diff
--- MoH-Promise_EligibilityChecker_v1.2.2/main.py
+++ MoH-Promise_EligibilityChecker_v1.2.3/main.py
@@ -148,14 +148,61 @@
 
 
 def write_output_excel(
-    progress_file_path: Path, output_file_path: Path, log_callback=None
+    progress_file_path: Path, output_file_path: Path, input_excel_path: Path, log_callback=None
 ) -> bool:
     if not progress_file_path.exists() or progress_file_path.stat().st_size == 0:
         return False
     try:
-        # Read the entire progress CSV as text to preserve leading zeros in ID strings
-        df = pd.read_csv(progress_file_path, dtype=str)
-        df.to_excel(output_file_path, index=False)
+        # 1. Read original input spreadsheet (maintaining original order & data types as strings)
+        df_in = pd.read_excel(input_excel_path, sheet_name="Detail Data", dtype=str).fillna("")
+        serial_col = df_in.columns[0]  # E.g., 'Unnamed: 0'
+        
+        # 2. Read progress CSV containing scraped results
+        df_prog = pd.read_csv(progress_file_path, dtype=str)
+        
+        # Helper to convert numeric float strings like '2.0' to '2' for exact matching
+        def clean_serial(val):
+            val_str = str(val).strip()
+            try:
+                return str(int(float(val_str)))
+            except ValueError:
+                return val_str
+
+        # Standardize serial columns to clean string formats
+        df_in_clean = df_in.copy()
+        df_in_clean[serial_col] = df_in_clean[serial_col].apply(clean_serial)
+
+        df_prog_clean = df_prog.copy()
+        df_prog_clean[serial_col] = df_prog_clean[serial_col].apply(clean_serial)
+        
+        # 3. Filter original input rows to only keep those present in the progress CSV
+        processed_serials = set(df_prog_clean[serial_col].dropna().tolist())
+        df_in_filtered = df_in_clean[df_in_clean[serial_col].isin(processed_serials)].copy()
+        
+        # 4. Add result columns if not present
+        result_cols = [
+            "Insurance Name",
+            "Begin Date",
+            "End Date",
+            "Discrepancy",
+            "Penalty",
+            "Screenshot Taken",
+        ]
+        for col in result_cols:
+            if col not in df_in_filtered.columns:
+                df_in_filtered[col] = ""
+
+        # 5. Set index to serialize alignment
+        df_in_filtered.set_index(serial_col, inplace=True)
+        df_prog_clean.set_index(serial_col, inplace=True)
+        
+        # 6. Update original rows in-place with scraped results
+        df_in_filtered.update(df_prog_clean)
+        df_out = df_in_filtered.reset_index()
+        
+        # 7. Save perfect output preserving original order (excluding unprocessed rows)
+        df_out.to_excel(output_file_path, index=False)
+        
         if log_callback:
             log_callback(
                 f"📝 Excel output file successfully updated: {output_file_path.name}"
@@ -484,19 +531,19 @@
                     pass
                 file_exists = False
             else:
-                # Headers match: read all processed IDs (standardizing them to 10-digit strings)
+                # Headers match: read all processed IDs using the serial number (first column)
                 with open(progress_file, newline="", encoding="utf-8-sig") as f:
                     reader = csv.DictReader(f)
+                    serial_key = reader.fieldnames[0] if reader.fieldnames else (output_headers[0] if output_headers else "Unnamed: 0")
+                    serial_key_clean = serial_key.strip().replace('"', '').lower()
                     for row in reader:
-                        # Find the Medicaid Number key resiliently
-                        member_id = ""
+                        serial_val = ""
                         for k, v in row.items():
-                            if k and k.strip().replace('"', '').lower() == "medicaid number":
-                                member_id = (v or "").strip().replace('"', '')
+                            if k and k.strip().replace('"', '').lower() == serial_key_clean:
+                                serial_val = (v or "").strip().replace('"', '')
                                 break
-                        if member_id:
-                            # Standardize to 10-digit padded string
-                            processed_ids.add(member_id.zfill(10))
+                        if serial_val:
+                            processed_ids.add(serial_val)
                 rows_count = len(processed_ids)
         except Exception:
             file_exists = False
@@ -587,7 +634,7 @@
                     "📂 Found previous run progress. Loading already processed records..."
                 )
             # Immediately pre-fill/restore the output Excel file with existing progress
-            write_output_excel(progress_file_raw, output_file, log_callback)
+            write_output_excel(progress_file_raw, output_file, input_path, log_callback)
 
         progress_file, processed_ids, progress_writer, progress_f, rows_count = (
             setup_progress_tracking(input_path, full_headers)
@@ -624,6 +671,9 @@
                 fname = (row.get("First Name") or "").strip()
                 fullname = f"{lname}, {fname}".strip(", ")
 
+                serial_col = input_headers[0] if input_headers else "Unnamed: 0"
+                serial_val = (row.get(serial_col) or "").strip()
+
                 if stop_check and stop_check():
                     if log_callback:
                         log_callback(
@@ -631,8 +681,8 @@
                         )
                     break
 
-                # Skip completed rows based on the Medicaid Number
-                if member_id_raw in processed_ids:
+                # Skip completed rows based on the unique serial number (first column)
+                if serial_val in processed_ids:
                     if progress_callback:
                         progress_callback(
                             current=idx, total=len(input_rows), member_id=member_id_raw
@@ -642,7 +692,7 @@
                 if not PAYER_REGEX.search(row_contract.upper().strip()):
                     if log_callback:
                         log_callback(
-                            "⏭️ Skipping row {idx}/{len(input_rows)}: {fullname} - Contract is '{row_contract}'"
+                            f"⏭️ Skipping row {idx}/{len(input_rows)}: {fullname} - Contract is '{row_contract}'"
                         )
                     output_row = dict(row)
                     output_row.update(
@@ -657,8 +707,8 @@
                     )
                     progress_writer.writerow(output_row)
                     progress_f.flush()
-                    if member_id_raw:
-                        processed_ids.add(member_id_raw)
+                    if serial_val:
+                        processed_ids.add(serial_val)
                     if progress_callback:
                         progress_callback(
                             current=idx, total=len(input_rows), member_id=member_id_raw
@@ -724,8 +774,8 @@
                     progress_writer.writerow(output_row)
                     progress_f.flush()
 
-                    if member_id_raw:
-                        processed_ids.add(member_id_raw)
+                    if serial_val:
+                        processed_ids.add(serial_val)
 
                     if progress_callback:
                         progress_callback(
@@ -750,8 +800,8 @@
                     progress_writer.writerow(output_row)
                     progress_f.flush()
                     
-                    if member_id_raw:
-                        processed_ids.add(member_id_raw)
+                    if serial_val:
+                        processed_ids.add(serial_val)
                     
                     if progress_callback:
                         progress_callback(
@@ -766,7 +816,7 @@
 
             # Write/refresh final output Excel file
             if progress_file.exists() and progress_file.stat().st_size > 0:
-                write_output_excel(progress_file, output_file, log_callback)
+                write_output_excel(progress_file, output_file, input_path, log_callback)
 
     if log_callback:
         log_callback(f"✅ Run processing complete. Export located at: {output_file}")
```
