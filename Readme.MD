# 🔎 IdenHQ Product Table Harvester

A resilient Python + Playwright scraper that reuses or creates an authenticated session, navigates the hidden UI path to the Products table, harvests all product rows (including paginated / lazy-loaded data), and exports structured JSON for analysis.

---

## 🚀 Highlights

- ✅ Session reuse: loads and reuses playwright_state.json when possible
- 🔐 Login fallback: logs in using credentials from `.env` when session is invalid
- 🧭 Navigation: Tools → Data (nested) → Inventory → Products (robust text-based clicks)
- 📦 Data capture: full table extraction, pagination & lazy-loading handling
- 💾 Output: `product_table.json` (structured JSON)
- 🔁 Each run merges new cookies & origins into `playwright_state.json`

---

## ⚙️ Quick Setup

1. Install deps:
   ```bash
   pip install playwright python-dotenv
   playwright install
   ```
2. Create a .env next to the script (/home/harshvm/Desktop/IDEN/.env):
   ```
   IDEN_URL=https://your-login-url
   IDEN_USERNAME=your_username
   IDEN_PASSWORD=your_password
   ```
   The script will also accept these environment variables if exported in your shell.

## 🏁 Run

- From the project directory:
  ```
  python /home/harshvm/Desktop/IDEN/final_script.py
  ```
- Output written to: product_table.json
- Session file written/merged at: playwright_state.json

## 📜 Behavior notes

- Session reuse: If playwright_state.json exists the script attempts to create a context using it and verifies the session by visiting the target URL. If the session appears expired (sign-in form detected) the script performs a login flow and updates playwright_state.json using `merge_and_persist_storage_state`.
- Merge strategy: cookies keyed by (name, domain, path) are replaced by latest run; origins keyed by origin string are replaced by latest run. This prevents accidental removal of unrelated cookies/origins while adding new ones.
- Navigation path: the script locates and clicks UI elements by visible text (robust to variations) to reach Tools -> Data -> Inventory -> Products.
- Extraction: prefers table extraction (thead/tbody) and falls back to parsing card-like text blobs. `ensure_all_rows_loaded` attempts clicks/scrolls to load paginated or lazy-loaded content.

## 💡 Tips for excellence

- Adjust selectors in [final_script.py](/home/harshvm/Desktop/IDEN/final_script.py) if your build uses different labels or structure.
- Increase timeouts if the target is slow to respond.
- Keep playwright_state.json in the same directory so subsequent runs reuse/merge cookies and avoid repeated logins.
- For debugging, set headless=False in `fin2.run` to watch the browser.

## 📤 Submitting

- After verifying product_table.json contains the expected data, open the challenge site, go to the "Submit Script" page and push your repository as instructed.

## 🐛 Troubleshooting

- Missing env vars -> script raises an error; ensure .env or exported env vars are present.
- If automatic detection of the product table fails, inspect the page structure and update table/card selectors in [final_script.py](/home/harshvm/Desktop/IDEN/final_script.py).

## 📝 License / Notes

- Keep credentials secure. Do not commit .env with secrets to public repos.

```// filepath: /home/harshvm/Desktop/IDEN/Readme.MD
# IdenHQ Product Table Harvester

Summary
- Python Playwright script that reuses an existing session (playwright_state.json) when available; otherwise logs in using credentials from a .env file and saves/merges the session for future runs.
- Navigates the hidden path to the product table: Tools -> Data (nested tabset) -> Inventory -> Products.
- Captures all product rows, handles pagination / lazy-loading, and exports the result to product_table.json.
- Submit the final script via the "Submit Script" page in the challenge repo.

Files
- Main script: [final_script.py](/home/harshvm/Desktop/IDEN/final_script.py)
- Output JSON: product_table.json (created by the script)
- Stored session: playwright_state.json (created/merged by the script)

Key functions (in final_script.py)
- [`fin2.run`](/home/harshvm/Desktop/IDEN/final_script.py) — main entrypoint that orchestrates session reuse/login, navigation, extraction and output.
- [`merge_and_persist_storage_state`](/home/harshvm/Desktop/IDEN/final_script.py) — merges new cookies/origins into existing playwright_state.json on every run.
- [`try_fill`](/home/harshvm/Desktop/IDEN/final_script.py), [`try_click_by_text`](/home/harshvm/Desktop/IDEN/final_script.py) — resilient interaction helpers.
- [`ensure_all_rows_loaded`](/home/harshvm/Desktop/IDEN/final_script.py) — scrolls / clicks pagination to load all rows.
- [`extract_table_to_list`](/home/harshvm/Desktop/IDEN/final_script.py), [`parse_products_from_text`](/home/harshvm/Desktop/IDEN/final_script.py), [`normalize_row_dict`](/home/harshvm/Desktop/IDEN/final_script.py) — extraction and normalization helpers.

Requirements
- Python 3.8+
- Playwright for Python
- (optional) python-dotenv (script has a lightweight .env fallback)

Quick setup
1. Install dependencies:
```

pip install playwright python-dotenv
playwright install

```
2. Create a .env next to the script (/home/harshvm/Desktop/IDEN/.env):
```

IDEN_URL=https://your-login-url
IDEN_USERNAME=your_username
IDEN_PASSWORD=your_password

```
The script will also accept these environment variables if exported in your shell.

Run
- From the project directory:
```

python /home/harshvm/Desktop/IDEN/final_script.py

```
- Output written to: product_table.json
- Session file written/merged at: playwright_state.json

Behavior notes
- Session reuse: If playwright_state.json exists the script attempts to create a context using it and verifies the session by visiting the target URL. If the session appears expired (sign-in form detected) the script performs a login flow and updates playwright_state.json using `merge_and_persist_storage_state`.
- Merge strategy: cookies keyed by (name, domain, path) are replaced by latest run; origins keyed by origin string are replaced by latest run. This prevents accidental removal of unrelated cookies/origins while adding new ones.
- Navigation path: the script locates and clicks UI elements by visible text (robust to variations) to reach Tools -> Data -> Inventory -> Products.
- Extraction: prefers table extraction (thead/tbody) and falls back to parsing card-like text blobs. `ensure_all_rows_loaded` attempts clicks/scrolls to load paginated or lazy-loaded content.

Tips for excellence
- Adjust selectors in [final_script.py](/home/harshvm/Desktop/IDEN/final_script.py) if your build uses different labels or structure.
- Increase timeouts if the target is slow to respond.
- Keep playwright_state.json in the same directory so subsequent runs reuse/merge cookies and avoid repeated logins.
- For debugging, set headless=False in `fin2.run` to watch the browser.

Submitting
- After verifying product_table.json contains the expected data, open the challenge site, go to the "Submit Script" page and push your repository as instructed.

Troubleshooting
- Missing env vars -> script raises an error; ensure .env or exported env vars are present.
- If automatic detection of the product table fails, inspect the page structure and update table/card selectors in [final_script.py](/home/harshvm/Desktop/IDEN/final_script.py).

License / Notes
- Keep credentials secure. Do not commit .env with secrets
```
