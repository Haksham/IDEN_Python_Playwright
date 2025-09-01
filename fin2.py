import json
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

OUTPUT_PATH = Path(__file__).parent / "product_table.json"


def try_fill(page, selectors, value, timeout=2000):
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=timeout)
            page.fill(sel, value)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def try_click_by_text(page, text, timeout=5000):
    # try several strategies to click a visible button/link with given text
    try:
        page.get_by_role("button", name=re.compile(text, re.I)).click(timeout=timeout)
        return True
    except Exception:
        pass
    try:
        page.get_by_text(re.compile(text, re.I)).first.click(timeout=timeout)
        return True
    except Exception:
        pass
    # fallback: click any element that contains the text
    try:
        page.locator(f"text={text}", has_text=re.compile(text, re.I)).first.click(timeout=timeout)
        return True
    except Exception:
        return False


def extract_table_to_list(table_locator):
    # table_locator is a playwright Locator for a <table>
    headers = []
    try:
        headers = table_locator.locator("thead tr th").all_text_contents()
    except Exception:
        headers = []
    if not headers:
        # try first row as header
        first_row_th = table_locator.locator("tr").first.locator("th")
        if first_row_th.count() > 0:
            headers = first_row_th.all_text_contents()
    rows = []
    body_rows = table_locator.locator("tbody tr")
    if body_rows.count() == 0:
        # fallback to any tr after thead
        # build list from all tr except thead
        all_tr = table_locator.locator("tr")
        for i in range(1, all_tr.count()):
            row = all_tr.nth(i)
            cells = row.locator("td").all_text_contents()
            if not headers:
                headers = [f"col{j}" for j in range(len(cells))]
            item = {headers[j].strip() if j < len(headers) else f"col{j}": cells[j].strip() for j in range(len(cells))}
            rows.append(item)
        return rows
    for i in range(body_rows.count()):
        row = body_rows.nth(i)
        cells = row.locator("td").all_text_contents()
        if not headers:
            # create generic headers
            headers = [f"col{j}" for j in range(len(cells))]
        item = {headers[j].strip() if j < len(headers) else f"col{j}": cells[j].strip() for j in range(len(cells))}
        rows.append(item)
    return rows


def parse_products_from_text(blob):
    """
    Parse product cards/text blob and return list of product dicts with keys:
    product_name, type, id, shade, cost, manufacturer, sku, composition, updated
    """
    products = []
    # 1) Try to find structured blocks using regex (cards with labels)
    pattern = re.compile(
        r"(?P<name>.+?)\n(?P<type>.+?)\n\s*\nID:\s*(?P<id>\d+)\s*\n\s*Shade:\s*\n(?P<shade>.+?)\s*\nCost:\s*\n(?P<cost>\$[\d,\.]+)\s*\nManufacturer:\s*\n(?P<manufacturer>.+?)\s*\nSKU:\s*\n(?P<sku>.+?)\s*\nComposition:\s*\n(?P<composition>.+?)\s*\nUpdated:\s*(?P<updated>[\d/]+)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(blob):
        d = m.groupdict()
        item = {
            "product_name": d.get("name", "").strip(),
            "type": d.get("type", "").strip(),
            "id": int(d.get("id")) if d.get("id") and d.get("id").isdigit() else d.get("id", "").strip(),
            "shade": d.get("shade", "").strip(),
            "cost": d.get("cost", "").strip(),
            "manufacturer": d.get("manufacturer", "").strip(),
            "sku": d.get("sku", "").strip(),
            "composition": d.get("composition", "").strip(),
            "updated": d.get("updated", "").strip(),
        }
        products.append(item)

    if products:
        # dedupe and return
        seen = set()
        dedup = []
        for p in products:
            key = str(p.get("sku") or p.get("id") or (p.get("product_name")+"|"+p.get("type")))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(p)
        return dedup

    # 2) Fallback: parse card-style lists by scanning lines for patterns like:
    #    <Product Name>
    #    <Category/Type>
    #    ...other label/value lines...
    categories = {
        "beauty","automotive","toys","books","home & kitchen","garden","office",
        "health","clothing","electronics","garden","home","kitchen"
    }
    header_noise = ["iden challenge", "candidate", "instructions", "submit solution",
                    "sign out", "product dashboard", "assessment id", "showing", "layout:"]
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    i = 0
    while i < len(lines) - 1:
        name = lines[i]
        typ = lines[i + 1]
        if typ.lower() in categories and not any(h in name.lower() for h in header_noise):
            prod = {
                "product_name": name,
                "type": typ,
                "id": "",
                "shade": "",
                "cost": "",
                "manufacturer": "",
                "sku": "",
                "composition": "",
                "updated": "",
            }
            # scan next few lines to pick up labeled fields
            j = i + 2
            while j < len(lines) and j < i + 12:
                l = lines[j]
                low = l.lower()
                if low.startswith("id:"):
                    val = l.split(":", 1)[1].strip()
                    prod["id"] = int(val) if val.isdigit() else val
                elif low.startswith("shade"):
                    prod["shade"] = l.split(":", 1)[1].strip() if ":" in l else (lines[j+1] if j+1 < len(lines) else "")
                elif low.startswith("cost"):
                    prod["cost"] = l.split(":", 1)[1].strip() if ":" in l else (lines[j+1] if j+1 < len(lines) else "")
                elif low.startswith("manufacturer"):
                    prod["manufacturer"] = l.split(":", 1)[1].strip() if ":" in l else (lines[j+1] if j+1 < len(lines) else "")
                elif low.startswith("sku"):
                    prod["sku"] = l.split(":", 1)[1].strip() if ":" in l else (lines[j+1] if j+1 < len(lines) else "")
                elif low.startswith("composition"):
                    prod["composition"] = l.split(":", 1)[1].strip() if ":" in l else (lines[j+1] if j+1 < len(lines) else "")
                elif low.startswith("updated"):
                    prod["updated"] = l.split(":", 1)[1].strip() if ":" in l else (lines[j+1] if j+1 < len(lines) else "")
                else:
                    # detect cost like "$123.45"
                    if "$" in l and not prod["cost"]:
                        prod["cost"] = l
                    # detect SKU pattern e.g., ABC-1234-1
                    if re.search(r"[A-Z]{2,4}-\d{3,}-\d+", l) and not prod["sku"]:
                        prod["sku"] = l
                j += 1
            products.append(prod)
            i = j
        else:
            i += 1

    # final dedupe
    seen = set()
    dedup = []
    for p in products:
        key = p.get("sku") or f"{p.get('product_name')}|{p.get('type')}"
        if key in seen:
            continue
        seen.add(key)
        # ensure strings trimmed
        for k in p:
            if isinstance(p[k], str):
                p[k] = p[k].strip()
        dedup.append(p)
    return dedup


def normalize_row_dict(raw):
    """
    Map a raw table/dict row to the required output keys.
    Accepts different header names and returns normalized dict.
    """
    out = {
        "product_name": "",
        "type": "",
        "id": "",
        "shade": "",
        "cost": "",
        "manufacturer": "",
        "sku": "",
        "composition": "",
        "updated": "",
    }

    # helper to fetch by multiple possible keys
    def get_any(d, candidates):
        for c in candidates:
            for k in d.keys():
                if k and k.strip().lower() == c.lower():
                    return d[k]
        # fallback: search keys that contain candidate
        for c in candidates:
            for k in d.keys():
                if c.lower() in k.strip().lower():
                    return d[k]
        return ""

    out["product_name"] = get_any(raw, ["product name", "name", "product", "title"])
    out["type"] = get_any(raw, ["type", "category"])
    out_id = get_any(raw, ["id", "ID"])
    out["id"] = int(out_id) if str(out_id).isdigit() else (out_id or "")
    out["shade"] = get_any(raw, ["shade", "color"])
    out["cost"] = get_any(raw, ["cost", "price"])
    out["manufacturer"] = get_any(raw, ["manufacturer", "maker", "brand"])
    out["sku"] = get_any(raw, ["sku", "SKU"])
    out["composition"] = get_any(raw, ["composition", "material"])
    out["updated"] = get_any(raw, ["updated", "last updated", "modified"])
    # strip strings
    for k in out:
        if isinstance(out[k], str):
            out[k] = out[k].strip()
    return out


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # run in background/headless
        context = browser.new_context()
        page = context.new_page()

        # 1) Go to login page
        page.goto("https://hiring.idenhq.com/", timeout=60000)

        # 2) Fill credentials (as requested: username / pass)
        username = "harsh924hashvm@gmail.com"
        password = "iOOzvRZP"

        user_selectors = [
            'input[name="username"]', 'input[name="email"]', 'input[type="email"]',
            'input[id*=user]', 'input[placeholder*=User]', 'input[placeholder*=Email]'
        ]
        pass_selectors = [
            'input[name="password"]', 'input[type="password"]', 'input[id*=pass]',
            'input[placeholder*=Password]'
        ]

        filled_user = try_fill(page, user_selectors, username)
        filled_pass = try_fill(page, pass_selectors, password)

        if not filled_user or not filled_pass:
            # try generic filling by finding first two inputs
            try:
                inputs = page.locator("input").all()
                if len(inputs) >= 2:
                    inputs[0].fill(username)
                    inputs[1].fill(password)
                else:
                    raise RuntimeError("Could not find credential inputs")
            except Exception as e:
                browser.close()
                raise

        # submit - try many ways
        submitted = False
        try:
            # try pressing Enter on password field
            for sel in pass_selectors:
                try:
                    page.press(sel, "Enter", timeout=2000)
                    submitted = True
                    break
                except Exception:
                    continue
        except Exception:
            pass

        if not submitted:
            # try clicking common submit buttons
            for btn_text in ["Sign in", "Sign In", "Log in", "Login", "Submit"]:
                if try_click_by_text(page, btn_text, timeout=3000):
                    submitted = True
                    break
        # wait a bit for login to complete
        time.sleep(2)

        # 3) Navigate to challenge page (after authentication)
        page.goto("https://hiring.idenhq.com/challenge", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)

        # 4) Interact: Tools > Open Data Tools > Open Inventory > Select Inventory Tab > Load Product Table
        # These are attempted by text; adjust if labels differ.
        actions = [
            "Tools",
            "Open Data Tools",
            "Open Inventory",
            "Inventory",
            "Load Product Table",
            "Load Products",
            "Load Product Table"
        ]

        # Click Tools
        try_click_by_text(page, "Tools", timeout=5000)
        time.sleep(1)

        # Click Open Data Tools (try variations)
        try_click_by_text(page, "Open Data Tools", timeout=5000)
        time.sleep(1)

        # Click Open Inventory (or Inventory)
        if not try_click_by_text(page, "Open Inventory", timeout=4000):
            try_click_by_text(page, "Inventory", timeout=4000)
        time.sleep(1)

        # Ensure Inventory tab selected
        try_click_by_text(page, "Inventory", timeout=4000)
        time.sleep(1)

        # Click Load Product Table (or similar)
        if not try_click_by_text(page, "Load Product Table", timeout=5000):
            try_click_by_text(page, "Load Products", timeout=5000)
        time.sleep(2)

        # 5) Wait for table or cards to appear and extract required fields
        table_locator = None
        try:
            # try common selectors for table area
            page.wait_for_selector("table", timeout=10000)
            # prefer a table that contains the word "Product" in it
            tables = page.locator("table")
            chosen = None
            for i in range(tables.count()):
                t = tables.nth(i)
                txt = t.inner_text()[:200]
                if re.search(r"Prod(uct)?|SKU|Name|Price", txt, re.I):
                    chosen = t
                    break
            if not chosen and tables.count() > 0:
                chosen = tables.first
            table_locator = chosen
        except PlaywrightTimeoutError:
            pass

        final_products = []

        if not table_locator:
            # look for product cards / containers containing the product text
            # collect all text blocks that contain "SKU" or "Manufacturer" to build a blob
            blocks = []
            # try several selectors that might correspond to card containers
            selectors = ["div", "section", "article"]
            for sel in selectors:
                elems = page.locator(sel).filter(has_text=re.compile(r"SKU|Manufacturer|ID:|Updated", re.I))
                for i in range(elems.count()):
                    txt = elems.nth(i).inner_text().strip()
                    # skip very short irrelevant blocks
                    if len(txt) > 40:
                        blocks.append(txt)
            # if nothing found, fallback to full page text
            if not blocks:
                page_text = page.inner_text("body")
                blocks = [page_text]

            blob = "\n\n".join(blocks)

            # remove leading page header up to and including the known inventory header
            header_re = re.compile(
                r"Iden Challenge.*?Product Inventory\s*.*?Showing\s*\d+\s*of\s*\d+\s*products",
                re.IGNORECASE | re.DOTALL,
            )
            m = header_re.search(blob)
            if m:
                blob = blob[m.end():].lstrip()

            parsed = parse_products_from_text(blob)
            # keep only requested fields in the required order
            required = ["product_name", "type", "id", "shade", "cost", "manufacturer", "sku", "composition", "updated"]
            final_products = []
            for p in parsed:
                out = {}
                for k in required:
                    v = p.get(k, "")
                    if k == "id" and str(v).isdigit():
                        v = int(v)
                    out[k] = v
                final_products.append(out)
        else:
            # table exists: extract rows & normalize
            products = extract_table_to_list(table_locator)
            normalized = []
            for r in products:
                nr = normalize_row_dict(r)
                normalized.append(nr)
            final_products = normalized

        # Ensure final_products contains only requested fields and pretty-print
        # Convert any non-serializable values (e.g., ints) are okay for json
        OUTPUT_PATH.write_text(json.dumps(final_products, indent=2))

        context.close()
        browser.close()


if __name__ == "__main__":
    run()