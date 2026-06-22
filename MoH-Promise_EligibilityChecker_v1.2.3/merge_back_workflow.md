# DHS Promise Eligibility Checker - Merge-Back Feature Workflow

This document explains the internal step-by-step workflow of the **Merge-Back** feature implemented in version `v1.2.3` of the DHS Promise Portal Eligibility Checker.

---

## 1. Overview
The **Merge-Back** feature solves two major problems when pausing, resuming, or recheck-running lookups:
1. **Order Preservation**: Out-of-order rows appended to the progress CSV are automatically sorted back to their original sequence.
2. **Exclusion of Unprocessed Rows**: The output sheet only includes rows that have been processed, omitting any remaining rows at the end of the input file.
3. **Speed Efficiency**: Unlike UPMC, which writes heavily to Excel on every iteration, this merge happens in memory once at stop or completion, keeping crawling speeds at maximum.

---

## 2. Step-by-Step Data Example

### Phase A: The Original Input File
Your original Excel spreadsheet has 5 rows in this exact sequence:

| Serial (`Unnamed: 0`) | Name | Contract |
| :--- | :--- | :--- |
| **1** | John Doe | KEYSTONE FIRST CHC |
| **2** | Jane Smith | UPMC LTSS |
| **3** | Bob Johnson | AMERIHEALTH |
| **4** | Alice Williams | KEYSTONE FIRST CHC |
| **5** | Charlie Brown | UPMC LTSS |

---

### Phase B: The Run, Pause, and Edit
1. You run the script. Rows **1** and **3** complete successfully, but row **2** encounters a network error and is saved as `Portal/Network Error`.
2. You click **Stop**.
3. You open the progress CSV and **delete row 2** so the script will re-run it next time.
4. You restart the script. The script sees that serial **2** is missing, re-runs it, gets successful results, and appends it to the bottom of the CSV file.
5. The run stops before processing rows 4 and 5.

Here is the raw state of the progress CSV (Note that **Row 2 is at the bottom**):

| Serial (`Unnamed: 0`) | Name | Contract | Insurance Name |
| :--- | :--- | :--- | :--- |
| **1** | John Doe | KEYSTONE FIRST CHC | KEYSTONE FIRST CHC |
| **3** | Bob Johnson | AMERIHEALTH | AMERIHEALTH |
| **2** | Jane Smith | UPMC LTSS | UPMC LTSS | *(Appended at the bottom)* |

---

### Phase C: The Merge-Back Action

When saving the final Excel file, the script executes these steps inside the [write_output_excel](file:///D:/WORK/Eligibility/MoH-Promise_EligibilityChecker_v1.2.3/main.py#L150) function:

#### 1. Reads the Template
Loads the original input file (containing rows `1, 2, 3, 4, 5`).

#### 2. Reads the Progress CSV
Loads the progress file containing serials `1, 3, 2`.

#### 3. Filters Out Unprocessed Rows
The script checks which serials are present in the progress CSV (`{1, 2, 3}`) and filters the template. 
* **Rows 4 and 5** (Alice and Charlie) are discarded.
* The remaining template looks like this (Notice they are back in original sequence `1, 2, 3`):

| Serial (`Unnamed: 0`) | Name | Contract |
| :--- | :--- | :--- |
| **1** | John Doe | KEYSTONE FIRST CHC |
| **2** | Jane Smith | UPMC LTSS |
| **3** | Bob Johnson | AMERIHEALTH |

#### 4. Prepares Empty Columns
Adds blank columns for the results:

| Serial (`Unnamed: 0`) | Name | Contract | Insurance Name |
| :--- | :--- | :--- | :--- |
| **1** | John Doe | KEYSTONE FIRST CHC | *[empty]* |
| **2** | Jane Smith | UPMC LTSS | *[empty]* |
| **3** | Bob Johnson | AMERIHEALTH | *[empty]* |

#### 5. In-Place Alignment (`.update`)
Both datasets are aligned by their serial numbers. The script calls the Pandas `.update()` function to populate the template:
* Matches Serial **1** $\rightarrow$ Fills in `"KEYSTONE FIRST CHC"`.
* Matches Serial **2** $\rightarrow$ Finds serial **2** in the CSV, and fills in `"UPMC LTSS"`.
* Matches Serial **3** $\rightarrow$ Fills in `"AMERIHEALTH"`.

---

### Phase D: The Final Output Excel File
The final spreadsheet is saved to disk:

| Serial (`Unnamed: 0`) | Name | Contract | Insurance Name |
| :--- | :--- | :--- | :--- |
| **1** | John Doe | KEYSTONE FIRST CHC | KEYSTONE FIRST CHC |
| **2** | Jane Smith | UPMC LTSS | UPMC LTSS | *(Perfectly sorted back to position 2)* |
| **3** | Bob Johnson | AMERIHEALTH | AMERIHEALTH |
