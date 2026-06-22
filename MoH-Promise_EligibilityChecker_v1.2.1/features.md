# MoH-Promise Eligibility Checker - Version 1.2.1 Features Specification

MoH-Promise Eligibility Checker is a high-efficiency automation tool designed to streamline patient eligibility verification via the Pennsylvania Department of Human Services Promise Portal. Below are the core features of the system in version 1.2.1 along with illustrative code snippets implementing them.

---

### 🖥️ Interactive Control Dashboard (GUI)
The desktop application provides a clean, visual console that allows users to manage and execute automation tasks:
* **Dynamic File Pickers**: Simple browser dialogues for selecting source Excel documents and specifying destination folders.
* **Granular Entry Limits**: Ability to set a custom numeric threshold on the number of rows processed in a single run.
* **Live Logging Viewport**: A thread-safe log panel featuring color-coded visual markers (`🟢 Info`, `🔴 Error`, `🟢 Success`, `⚠️ Warning`) to monitor the state of the active run.
* **Progress Diagnostics**: Horizontal progress bar complemented by status labels reflecting percentage complete, rows remaining, and the active patient Medicaid Number.

```python
# Example UI State Transition Logic (from gui.py)
def _set_ui_state(ui_state):
    def _apply():
        if ui_state == "idle":
            _apply_button_style(connect_btn, "connect", True)
            _apply_button_style(start_btn, "start", False)
            _apply_button_style(stop_btn, "stop", False)
            excel_browse_btn.config(state="normal")
            output_browse_btn.config(state="normal")
            entry_size_entry.config(state="normal")
        elif ui_state == "running":
            _apply_button_style(connect_btn, "connect", False)
            _apply_button_style(start_btn, "start", False)
            _apply_button_style(stop_btn, "stop", True)
            excel_browse_btn.config(state="disabled")
            output_browse_btn.config(state="disabled")
            entry_size_entry.config(state="disabled")
    app.after(0, _apply)
```

---

### 🌐 Edge Browser CDP Integration
To align with security and operational guidelines, the software leverages the Chrome DevTools Protocol (CDP):
* **Automatic Debug Port Setup**: Attempts to detect and connect to port `9222`. If not active, it automatically launches Microsoft Edge with remote debugging enabled.
* **Session and Tab Preservation**: Automatically scans active tabs to identify existing Promise Portal sessions, reusing open tabs to maintain authentication state and avoid redundant login cycles.
* **Human-like Navigation**: Embedded randomized delays to mimic manual workflow pacing, maintaining stable connections with portal search interfaces.

```python
# Example Remote Browser CDP Initialization (from main.py)
def launch_edge_with_cdp():
    print("🚀 Launching Edge with CDP...")
    edge_cmd = [
        "cmd",
        "/c",
        "start",
        "msedge",
        "--remote-debugging-port=9222",
        "--ignore-certificate-errors",
        "--allow-running-insecure-content",
        "--start-maximized",
        "--user-data-dir=C:\\edge-playwright-profile",
    ]
    subprocess.Popen(edge_cmd)
    for _ in range(20):
        if is_cdp_running():
            print("✅ Edge launched and CDP is running")
            return True
        time.sleep(1)
    return False
```

---

### 🔍 Smart Eligibility Search & Field Mapping
The utility automates patient searches and parses returned results:
* **Targeted Search Forms**: Automatically fills patient Medicaid Number (padded to 10 digits), Date of Birth, and date ranges (spanning from the first of the month to the last of the month).
* **Multi-Payer Contract Alignment**: Automatically matches extracted managed care plans against standardized payer groups (including `UPMC`, `Keystone First`, `AmeriHealth`, `PA Health & Wellness`, and `Waiver`).
* **Discrepancy and Penalty Pipeline**: 
  * Verifies contract terms against portal output categories.
  * Ensures presence of required `"WAIVER"` programs.
  * Validates extracted dates against search limits.
  * Scans portal results for explicit `"Penalty"` notifications.

```python
# Example Patient Query and Form Submission (from main.py)
def search(page, member_id_raw: str, dob: str):
    member_id = member_id_raw.strip().zfill(10)
    today = datetime.date.today()
    first_of_month = today.replace(day=1)
    _, last_day = calendar.monthrange(today.year, today.month)
    last_of_month = today.replace(day=last_day)

    start_date_str = first_of_month.strftime("%m/%d/%Y")
    end_date_str = last_of_month.strftime("%m/%d/%Y")

    page.fill("#dnn_ctr1732_Eligibility_txtRecipientID2", member_id)
    page.fill("#dnn_ctr1732_Eligibility_txtDob3", dob)
    page.fill("#dnn_ctr1732_Eligibility_txtDosFrom", start_date_str)
    page.fill("#dnn_ctr1732_Eligibility_txtDosTo", end_date_str)

    time.sleep(random.uniform(1, 3))
    page.wait_for_selector(
        "#dnn_ctr1732_Eligibility_btnSearch", state="visible", timeout=60000
    )
    page.click("#dnn_ctr1732_Eligibility_btnSearch", no_wait_after=True)

    return start_date_str, end_date_str
```

---

### 📸 High-Fidelity Visual Verification (Screenshots)
Ensures visual record keeping for audit and quality assurance:
* **Layout Scaling**: Zooms the portal layout to 87% dynamically before capture to align eligibility details within the crop area.
* **Targeted Clipping**: Uses precise bounding-box coordinates to capture only the relevant eligibility tables, ignoring surrounding portal headers or footers.
* **Standardized Filenames**: Saves screenshots using a uniform template combining the patient name, Medicaid Number, and execution timestamp.

```python
# Example Element Bounding-Box Clipping and Zooming (from main.py)
page.evaluate("""
    () => {
        document.body.style.zoom = "87%"
    }
""")
table = page.locator("#dnn_ctr1732_Eligibility_Table6")
table.scroll_into_view_if_needed()
page.wait_for_timeout(1000)
box = table.bounding_box()

page.screenshot(
    path=str(screenshot_path),
    clip={
        "x": max(0, box["x"] - padding_left),
        "y": max(0, box["y"] - padding_top),
        "width": (box["width"] + padding_left + padding_right),
        "height": (box["height"] + padding_top + padding_bottom),
    },
)
```

---

### 📂 Session Resuming & Milestone Recovery
Guarantees data integrity and processing efficiency during long runs:
* **Milestone Progress Tracking**: Automatically generates and updates a companion `_progress.csv` file in the source directory.
* **Delta Recovery**: Automatically checks for existing progress files on start, restoring already verified records and resuming execution seamlessly from the last completed patient.
* **Automated Excel Compilations**: Writes intermediate results to a final multi-column Excel spreadsheet output immediately upon run completion or interruption.

```python
# Example Recovery Milestone Setup (from main.py)
def setup_progress_tracking(input_path, output_headers):
    progress_file = input_path.parent / f"{input_path.stem}_progress.csv"
    processed_ids = set()
    file_exists = progress_file.exists()

    if file_exists:
        try:
            with open(progress_file, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    member_id = (row.get("Medicaid Number") or "").strip()
                    if member_id:
                        processed_ids.add(member_id)
        except Exception:
            file_exists = False
            processed_ids.clear()
    
    # ... Initialize Writer ...
    return progress_file, processed_ids, progress_writer, progress_f
```
