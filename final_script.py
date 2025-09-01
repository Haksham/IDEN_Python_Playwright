import json
import time
import re
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

OUTPUT_PATH = Path(__file__).parent / "product_table.json"
STORAGE_STATE = Path(__file__).parent / "playwright_state.json"

# Smart waiting helpers
def wait_for_selector_visible(page, selector, timeout=5000):
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        return True
    except Exception:
        return False

def wait_for_locator_visible(locator, timeout=5000):
    try:
        locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False

def wait_and_fill(page, selector, value, timeout=5000, pause=200):
    try:
        # accept either selector string or Locator
        if isinstance(selector, str):
            if not wait_for_selector_visible(page, selector, timeout=timeout):
                return False
            page.fill(selector, value, timeout=timeout)
        else:
            if not wait_for_locator_visible(selector, timeout=timeout):
                return False
            selector.fill(value, timeout=timeout)
        page.wait_for_timeout(pause)
        return True
    except Exception:
        return False

def wait_and_click(page, target, timeout=5000, pause=300):
    try:
        # target may be selector string or Locator
        if isinstance(target, str):
            if not wait_for_selector_visible(page, target, timeout=timeout):
                return False
            page.click(target, timeout=timeout)
        else:
            if not wait_for_locator_visible(target, timeout=timeout):
                return False
            target.click(timeout=timeout)
        # short pause to let UI react
        page.wait_for_timeout(pause)
        return True
    except Exception:
        return False


def try_fill(page, selectors, value, timeout=2000):
    for sel in selectors:
        try:
            if wait_and_fill(page, sel, value, timeout=timeout):
                return True
        except Exception:
            continue
    return False


def try_click_by_text(page, text, timeout=5000):
    # try several strategies to click a visible button/link with given text
    try:
        locator = page.get_by_role("button", name=re.compile(text, re.I))
        if wait_for_locator_visible(locator, timeout=timeout):
            locator.click(timeout=timeout)
            page.wait_for_timeout(300)
            return True
    except Exception:
        pass
    try:
        locator = page.get_by_text(re.compile(text, re.I)).first
        if wait_for_locator_visible(locator, timeout=timeout):
            locator.click(timeout=timeout)
            page.wait_for_timeout(300)
            return True
    except Exception:
        pass
    # fallback: click any element that contains the text
    try:
        # use locator text= which supports Playwright's text selector
        sel = f"text={text}"
        if wait_for_selector_visible(page, sel, timeout=timeout):
            page.click(sel, timeout=timeout)
            page.wait_for_timeout(300)
            return True
    except Exception:
        return False

def ensure_all_rows_loaded(page, table_locator=None, row_selector="tbody tr", timeout_ms=120000, pause=0.6):
    start = time.time()
    last_count = -1
    stable = 0
    max_stable = 3

    def count_rows():
        try:
            if table_locator:
                return table_locator.locator(row_selector).count()
            return page.locator(row_selector).count()
        except Exception:
            return 0

    # try to detect expected total like "Showing 1-20 of 2850"
    expected_total = None
    try:
        body = page.inner_text("body", timeout=2000)
        m = re.search(r"of\s+([0-9,]{2,})", body, re.I)
        if m:
            expected_total = int(m.group(1).replace(",", ""))
    except Exception:
        expected_total = None

    while (time.time() - start) * 1000 < timeout_ms:
        curr = count_rows()
        # try pagination clicks first
        clicked = False
        for txt in ["Next", "next", ">", "»", "→", "More", "Load more"]:
            try:
                if try_click_by_text(page, txt, timeout=800):
                    clicked = True
                    page.wait_for_load_state("networkidle", timeout=3000)
                    page.wait_for_timeout(int(pause * 1000))
                    break
            except Exception:
                continue

        if not clicked:
            # try to click pagination anchors if present
            try:
                # common pagination list items
                pag_links = page.locator("ul.pagination a, nav[aria-label*='pagination'] a, .pagination a")
                for i in range(pag_links.count()):
                    a = pag_links.nth(i)
                    txt = a.inner_text().strip()
                    if re.match(r"^\s*(Next|>|»|→)\s*$", txt, re.I):
                        a.click(timeout=1000)
                        clicked = True
                        page.wait_for_load_state("networkidle", timeout=3000)
                        page.wait_for_timeout(int(pause * 1000))
                        break
            except Exception:
                pass

        if not clicked:
            # scroll the table container if provided
            try:
                if table_locator:
                    try:
                        table_locator.evaluate("el => { el.scrollTop = el.scrollHeight; return el.scrollHeight; }")
                    except Exception:
                        # fallback to scrolling the page
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                else:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            page.wait_for_timeout(int(pause * 1000))

        new_count = count_rows()
        # if expected_total known and reached, finish
        if expected_total and new_count >= expected_total:
            return

        if new_count == last_count:
            stable += 1
        else:
            stable = 0
            last_count = new_count

        if stable >= max_stable:
            return

    return

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


# Load .env into environment (uses python-dotenv if available, otherwise a simple fallback)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)
except Exception:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # run in background/headless

        # read credentials and url from environment (.env)
        iden_url = os.getenv("IDEN_URL") or os.getenv("URL")
        username = os.getenv("IDEN_USERNAME") or os.getenv("IDEN_USER") or os.getenv("USER")
        password = os.getenv("IDEN_PASSWORD") or os.getenv("PASSWORD")

        if not iden_url:
            browser.close()
            raise RuntimeError("Missing IDEN_URL or URL in .env or environment")

        context = None
        page = None

        # Try to reuse existing stored session
        try:
            if STORAGE_STATE.exists():
                try:
                    context = browser.new_context(storage_state=str(STORAGE_STATE))
                    page = context.new_page()
                    # quick check if session is still valid by visiting the target page
                    page.goto(iden_url, timeout=60000)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    # Heuristic: if there's a visible sign-in form, consider session invalid
                    try:
                        sign_in_present = False
                        # common sign-in indicators
                        for sel in ['text="Sign in"', 'text="Sign In"', 'input[type="password"]', 'form[action*="login"]']:
                            try:
                                if page.locator(sel).count() > 0:
                                    sign_in_present = True
                                    break
                            except Exception:
                                continue
                        if sign_in_present:
                            context.close()
                            context = None
                            page = None
                    except Exception:
                        # If any check fails, fall back to fresh login
                        if context:
                            try:
                                context.close()
                            except Exception:
                                pass
                        context = None
                        page = None
                except Exception:
                    # unable to create context with stored state, continue to fresh login
                    if context:
                        try:
                            context.close()
                        except Exception:
                            pass
                    context = None
                    page = None
        except Exception:
            context = None
            page = None

        # If we didn't get a valid context from storage, perform login and save storage
        if context is None:
            context = browser.new_context()
            page = context.new_page()

            # Only require credentials when performing login
            if not username or not password:
                context.close()
                browser.close()
                raise RuntimeError("Missing IDEN_USERNAME or IDEN_PASSWORD in .env or environment required for login")

            # 1) Go to login page
            page.goto(iden_url, timeout=60000)

            # 2) Fill credentials (from .env / env)
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
                except Exception:
                    context.close()
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

            # After successful login, save storage state for future runs
            try:
                # navigate to a stable page/state before saving storage
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                context.storage_state(path=str(STORAGE_STATE))
            except Exception:
                # non-fatal: continue without persisting
                pass

        # ensure we have page/context to continue
        if page is None:
            page = context.new_page()

        # 3) Navigate to challenge page (after authentication)
        try:
            page.goto("https://hiring.idenhq.com/challenge", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            # continue even if navigation has minor issues
            pass

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
                try:
                    txt = t.inner_text()[:200]
                except Exception:
                    txt = ""
                if re.search(r"Prod(uct)?|SKU|Name|Price", txt, re.I):
                    chosen = t
                    break
            if not chosen and tables.count() > 0:
                chosen = tables.first
            table_locator = chosen
            # attempt to load all paginated pages and collect rows
            try:
                collected = paginate_and_collect(page, table_locator, max_pages=None)
                if collected:
                    # collected already normalized - use it as final_products
                    final_products = collected
            except Exception:
                # fallback to single-page extraction below
                pass
        except PlaywrightTimeoutError:
            # try to ensure all rows load (pagination / infinite scroll)
            try:
                ensure_all_rows_loaded(page, table_locator=table_locator, row_selector="tbody tr", timeout_ms=120000)
            except Exception:
                pass
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
            # if paginate_and_collect already filled final_products, skip
            if not final_products:
                # table exists: extract rows & normalize (single page)
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


def merge_and_persist_storage_state(context, path=STORAGE_STATE):
    """
    Merge current context.storage_state() into existing storage file.
    - Cookies are deduped by (name, domain, path) and overwritten by latest run.
    - Origins are deduped by origin string and overwritten by latest run.
    Best-effort: failures are non-fatal.
    """
    try:
        new_state = context.storage_state()
        # load existing file if present
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                existing = {}
        else:
            existing = {}

        existing_cookies = existing.get("cookies", [])
        existing_origins = existing.get("origins", [])

        # merge cookies (keyed by name, domain, path)
        def cookie_key(c): return (c.get("name"), c.get("domain"), c.get("path"))
        merged_cookie_map = {cookie_key(c): c for c in existing_cookies}
        for c in new_state.get("cookies", []):
            merged_cookie_map[cookie_key(c)] = c
        merged_cookies = list(merged_cookie_map.values())

        # merge origins (keyed by origin)
        merged_origin_map = {o.get("origin"): o for o in existing_origins}
        for o in new_state.get("origins", []):
            merged_origin_map[o.get("origin")] = o
        merged_origins = list(merged_origin_map.values())

        merged = {"cookies": merged_cookies, "origins": merged_origins}
        path.write_text(json.dumps(merged, indent=2))
    except Exception as e:
        # non-fatal: print warning so runs continue
        print("Warning: could not persist merged storage state:", str(e))


if __name__ == "__main__":
    run()