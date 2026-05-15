import csv
import subprocess
import time
import requests
import datetime
import calendar
from typing import Tuple
import re

from pathlib import Path
from playwright.sync_api import sync_playwright


CDP_URL = "http://127.0.0.1:9222"

def sanitize_filename(value: str) -> str:
    return re.sub(r'[^\w\-_. ]', '_', value)

def is_cdp_running():
    try:
        response = requests.get(f"{CDP_URL}/json/version", timeout=2)
        return response.status_code == 200
    except Exception:
        return False

def launch_edge_with_cdp():
    print("🚀 Launching new Edge browser with CDP...")
    edge_cmd = [
        "cmd", "/c", "start", "msedge",
        "--remote-debugging-port=9222",
        "--start-maximized",
        "--user-data-dir=C:\\edge-playwright-profile"
    ]
    subprocess.Popen(edge_cmd)
    for _ in range(20):
        if is_cdp_running():
            print("✅ CDP browser is ready")
            return True
        time.sleep(1)
    return False

def ensure_edge_cdp():
    if is_cdp_running():
        print("✅ Existing CDP browser detected")
        return
    print("⚠ No CDP browser detected")
    success = launch_edge_with_cdp()
    if not success:
        raise Exception("❌ Failed to launch Edge with CDP")

def get_or_create_page(context):
    if context.pages:
        page = context.pages[0]
        print(f"🌐 Attached to existing tab: {page.url}")
        return page
    page = context.new_page()
    print("🆕 Created new tab")
    return page

def get_valid_csv_path() -> Path:
    """
    Prompts the user to enter the input CSV file path.
    Verifies the file exists. Returns Path object if valid, else None.
    Retries until a valid path is provided or user cancels with empty input.
    """
    while True:
        try:
            csv_input_path = input("Please enter the path to the input CSV file (or press Enter to cancel): ").strip('"').strip()
            if csv_input_path == "":
                print("Input cancelled by user.")
                return None

            input_path = Path(csv_input_path)
            if not input_path.is_file():
                print(f"❌ Input CSV file not found: {csv_input_path}. Please try again.")
                continue

            return input_path
        except Exception as e:
            print(f"❌ Error processing input: {e}. Please try again.")

def prepare_output_folder(input_csv_path: str, timestamp: str) -> Tuple[Path, Path]:
    """
    Create an output folder based on the input CSV filename plus current timestamp.

    Returns:
        output_folder (Path): The path to the created output folder.
        output_file (Path): The path to the output CSV file inside the folder.
    """
    input_path = Path(input_csv_path)
    input_stem = input_path.stem
    output_folder_name = f"{input_stem}_{timestamp}"
    output_folder = Path.cwd() / output_folder_name
    output_folder.mkdir(parents=True, exist_ok=True)
    output_file = output_folder / f"{input_stem}-{timestamp}.csv"
    return output_folder, output_file

def prepare_csv_reader_writer(input_path: Path, output_file: Path):
    """
    Reads the entire input CSV file, prepares the output CSV file with additional headers,
    and returns the list of input rows and the CSV writer object.
    """
    # Read all input data
    with open(input_path, newline='', encoding='utf-8') as f:
        input_rows = list(csv.DictReader(f))
        input_headers = list(input_rows[0].keys()) if input_rows else []

    # Prepare output headers (add columns you need)
    output_headers = input_headers + ["Insurance Name", "Begin Date", "End Date"]

    # Open output CSV and prepare writer
    f_out = open(output_file, mode='w', newline='', encoding='utf-8')
    writer = csv.DictWriter(f_out, fieldnames=output_headers)
    writer.writeheader()

    return input_rows, writer, f_out

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

    page.wait_for_selector("#dnn_ctr1732_Eligibility_btnSearch", timeout=60000)  # wait up to 60s
    page.click('#dnn_ctr1732_Eligibility_btnSearch')

def extract_results(page):
    result_rows = []
    try:
        page.wait_for_selector("#dnn_ctr1732_Eligibility_gvSummary tbody tr:not(:first-child)", timeout=60000)
        rows = page.query_selector_all("#dnn_ctr1732_Eligibility_gvSummary tbody tr:not(:first-child)")
        for row in rows:
            type_cell = row.query_selector("td:nth-child(1)")
            type_text = type_cell.inner_text().strip() if type_cell else ""

            if "Managed Care" in type_text:
                name_cell = row.query_selector("td:nth-child(2)")

                if "COMMUNITY HEALTHCHOICES" in name_cell.inner_text().strip().upper():
                    begin_cell = row.query_selector("td:nth-child(3)")
                    end_cell = row.query_selector("td:nth-child(4)")
                    name = name_cell.inner_text().strip() if name_cell else ""
                    begin = begin_cell.inner_text().strip() if begin_cell else ""
                    end = end_cell.inner_text().strip() if end_cell else ""
                    result_rows.append({
                        "Insurance Name": name,
                        "Begin Date": begin,
                        "End Date": end
                    })
    except Exception as e:
        print(f"⚠️ No Results Found: {e}")
    return result_rows

def take_screenshot(page, output_folder, filename_prefix):
    page.wait_for_selector("#dnn_ctr1732_Eligibility_gvRecipient")
    page.wait_for_selector("#dnn_ctr1732_Eligibility_Table6")

    try:
        table1 = page.locator("#dnn_ctr1732_Eligibility_gvRecipient")
        table2 = page.locator("#dnn_ctr1732_Eligibility_Table6")

        # Scroll to second table to stabilize viewport
        table2.scroll_into_view_if_needed()

        # Wait for layout to settle
        page.wait_for_timeout(1500)

        # Get fresh bounding boxes AFTER scrolling
        box1 = table1.bounding_box()
        box2 = table2.bounding_box()

        if not box1 or not box2:
            print("⚠️ Could not get bounding boxes.")
            return

        # Different padding for each side
        padding_left = 200
        padding_right = 300

        padding_top = 1 
        padding_bottom = 800

        # Calculate clip area
        left = min(box1["x"], box2["x"]) - padding_left
        top = min(box1["y"], box2["y"]) - padding_top

        right = max(
            box1["x"] + box1["width"],
            box2["x"] + box2["width"]
        ) + padding_right

        bottom = max(
            box1["y"] + box1["height"],
            box2["y"] + box2["height"]
        ) + padding_bottom

        # Prevent negative coordinates
        left = max(0, left)
        top = max(0, top)

        screenshot_path = output_folder / f"{filename_prefix}.png"

        # Take screenshot
        page.screenshot(
            path=str(screenshot_path),
            clip={
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top
            }
        )

        print(f"🖼️ Screenshot saved: {screenshot_path}")

    except Exception as e:
        print(f"⚠️ Error taking screenshot: {e}")
 
def main():
    ensure_edge_cdp()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = get_or_create_page(context)
        input("Please log in to the portal if needed, then press Enter here to continue...")

        input_path = get_valid_csv_path()
        if input_path is None:
            return  # or exit
        
        # Prepare output folder and unique output file
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_folder, output_file = prepare_output_folder(input_path, timestamp)

        input_rows, writer, f_out = prepare_csv_reader_writer(input_path, output_file)

        # remember to close the file object at the end:
        # f_out.close()

        page.wait_for_selector('#dnn_PrimaryMenu_PrimaryMenuRepeater_PrimaryItemHCPHyperlink_2')
        page.click('#dnn_PrimaryMenu_PrimaryMenuRepeater_PrimaryItemHCPHyperlink_2')

        for idx, row in enumerate(input_rows, 1):
            member_id_raw = row.get("Medicaid Number", "").strip()
            dob = row.get("Date of Birth", "").strip()
            lname = row.get("Last Name", "").strip()
            fname = row.get("First Name", "").strip()
            name = f"{lname}, {fname}"
            sanitized_name = sanitize_filename(name)
                
            search(page, member_id_raw, dob)
            result = extract_results(page)

            # Prepare aggregated strings (numbered, multi-line) for each column
            if not result:
                agg_name = ""
                agg_begin = ""
                agg_end = ""
            else:
                agg_name = "\n".join(f"{i+1}. {d['Insurance Name']}" for i, d in enumerate(result))
                agg_begin = "\n".join(f"{i+1}. {d['Begin Date']}" for i, d in enumerate(result))
                agg_end = "\n".join(f"{i+1}. {d['End Date']}" for i, d in enumerate(result))

                output_row = dict(row)
                if result:
                    output_row.update({
                        "Insurance Name": agg_name,
                        "Begin Date": agg_begin,
                        "End Date": agg_end
                    })
                else:
                    output_row.update({
                        "Insurance Name": "",
                        "Begin Date": "",
                        "End Date": ""
                    })
                        
                writer.writerow(output_row)
                    
                screenshot_prefix = f"screenshot_{sanitized_name}_{member_id_raw}_{timestamp}"
                take_screenshot(page, output_folder, screenshot_prefix)
            print(f"Processed {idx}/{len(input_rows)}: Medicaid Number={member_id_raw}")
            f_out.flush()  # ensure data is written to disk after each row
        f_out.close()  # close the file after processing all rows

    print(f"✅ Automation complete. Output saved to {output_file}")

if __name__ == "__main__":
    main()