"""
ERP Automation - Dayananda Sagar University (ums.mydsi.org)
============================================================
Uses Playwright to log into the UMS portal and fetch:
- Assignments (pending/submitted/all)
- Attendance data
- Results / grades
- Timetable / schedule
- Announcements / notices
- Fee details
"""

import os
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ─── Credentials from environment ────────────────────────────────────────────
ERP_URL      = os.getenv("ERP_URL",      "https://ums.mydsi.org/")
ERP_USERNAME = os.getenv("ERP_USERNAME", "")
ERP_PASSWORD = os.getenv("ERP_PASSWORD", "")
ERP_ROLE     = os.getenv("ERP_ROLE",     "student").lower()

# ─── Result container ─────────────────────────────────────────────────────────
@dataclass
class ERPResult:
    success: bool
    action: str
    data: Any = None
    message: str = ""
    raw_text: str = ""


async def _launch_browser():
    """Launch a headless Chromium browser and return (playwright, browser, page)."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
    )
    page = await context.new_page()
    return pw, browser, page


async def _login(page) -> bool:
    """Log into the UMS portal. Returns True on success."""
    try:
        print(f"[ERP] Navigating to {ERP_URL}")
        await page.goto(ERP_URL, wait_until="networkidle", timeout=40_000)
        await asyncio.sleep(1)

        # Select role (Student radio button)
        role_selector = f'input[type="radio"][value="{ERP_ROLE.capitalize()}"], label:has-text("{ERP_ROLE.capitalize()}")'
        role_el = await page.query_selector(role_selector)
        if role_el:
            await role_el.click()
            await asyncio.sleep(0.5)

        # Fill username
        username_input = await page.query_selector(
            'input[name="username"], input[placeholder*="sername"], input[type="email"], #username, #email'
        )
        if username_input:
            await username_input.fill(ERP_USERNAME)
        else:
            print("[ERP] WARNING: Could not find username field")

        # Fill password
        password_input = await page.query_selector(
            'input[type="password"], input[name="password"], #password'
        )
        if password_input:
            await password_input.fill(ERP_PASSWORD)
        else:
            print("[ERP] WARNING: Could not find password field")

        # Click login button
        login_btn = await page.query_selector(
            'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign In")'
        )
        if login_btn:
            await login_btn.click()
        else:
            await page.keyboard.press("Enter")

        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=20_000)

        # Verify login – check we're no longer on the login page
        current_url = page.url
        page_text    = await page.inner_text("body")
        if "logout" in page_text.lower() or "dashboard" in page_text.lower() or current_url != ERP_URL:
            print(f"[ERP] Login successful. URL: {current_url}")
            return True

        # Check for error messages
        error_el = await page.query_selector('.alert-danger, .error, [class*="error"]')
        if error_el:
            err_text = await error_el.inner_text()
            print(f"[ERP] Login error: {err_text}")
        else:
            print("[ERP] Login may have failed – still on login page")
        return False

    except Exception as e:
        print(f"[ERP] Login exception: {e}")
        return False


async def _extract_table(page, table_selector: str = "table") -> List[Dict]:
    """Extract a visible HTML table into a list of dicts."""
    try:
        tables = await page.query_selector_all(table_selector)
        results = []
        for table in tables:
            rows = await table.query_selector_all("tr")
            headers: List[str] = []
            for i, row in enumerate(rows):
                cells = await row.query_selector_all("th, td")
                texts = [await c.inner_text() for c in cells]
                if i == 0:
                    headers = [t.strip() for t in texts]
                else:
                    if headers:
                        results.append(dict(zip(headers, [t.strip() for t in texts])))
                    else:
                        results.append({"col_" + str(j): v for j, v in enumerate(texts)})
        return results
    except Exception as e:
        print(f"[ERP] Table extraction error: {e}")
        return []


async def _navigate_to_section(page, keywords: List[str]) -> bool:
    """Try to find and click a nav item matching any of the given keywords."""
    for kw in keywords:
        # Try sidebar/nav links
        links = await page.query_selector_all(f'a:has-text("{kw}"), li:has-text("{kw}") a, nav a')
        for link in links:
            text = (await link.inner_text()).strip().lower()
            if kw.lower() in text:
                try:
                    await link.click()
                    await asyncio.sleep(2)
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                    print(f"[ERP] Navigated to section: {kw}")
                    return True
                except Exception:
                    continue
    return False


# ─── Public high-level functions ──────────────────────────────────────────────

async def check_erp(action: str = "assignments") -> ERPResult:
    """
    Main entry point. Logs in and performs the requested action.
    
    Actions:
      assignments  – pending/all assignments
      attendance   – attendance summary
      results      – exam results / grades
      timetable    – class schedule
      announcements / notices
      fees         – fee dues
      general      – general dashboard info / notifications
    """
    if not PLAYWRIGHT_AVAILABLE:
        return ERPResult(
            success=False,
            action=action,
            message=(
                "Playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            ),
        )

    if not ERP_USERNAME or not ERP_PASSWORD:
        return ERPResult(
            success=False,
            action=action,
            message=(
                "ERP credentials not configured. "
                "Set ERP_USERNAME and ERP_PASSWORD in .env"
            ),
        )

    pw, browser, page = None, None, None
    try:
        pw, browser, page = await _launch_browser()

        # Login
        logged_in = await _login(page)
        if not logged_in:
            return ERPResult(
                success=False,
                action=action,
                message=(
                    "Could not log in to ERP portal. "
                    "Please verify your credentials at ums.mydsi.org"
                ),
            )

        action_lower = action.lower()

        # ── Assignments ──────────────────────────────────────────────────────
        if "assign" in action_lower:
            navigated = await _navigate_to_section(
                page,
                ["Assignment", "Assignments", "My Assignments", "Academic"]
            )
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            tables    = await _extract_table(page)

            if not tables and not navigated:
                # Try URL guessing
                for suffix in ["/student/assignment", "/student/assignments", "/assignment"]:
                    try:
                        base = ERP_URL.rstrip("/")
                        await page.goto(base + suffix, wait_until="networkidle", timeout=15_000)
                        await asyncio.sleep(2)
                        tables = await _extract_table(page)
                        if tables:
                            break
                    except Exception:
                        pass

            summary = _summarise_assignments(tables, page_text)
            return ERPResult(
                success=True,
                action="assignments",
                data={"tables": tables, "summary": summary},
                message=summary,
                raw_text=page_text[:3000],
            )

        # ── Attendance ───────────────────────────────────────────────────────
        elif "attend" in action_lower:
            await _navigate_to_section(page, ["Attendance", "My Attendance"])
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            tables    = await _extract_table(page)
            summary   = _summarise_text_table("Attendance", tables, page_text)
            return ERPResult(
                success=True, action="attendance",
                data={"tables": tables}, message=summary, raw_text=page_text[:3000],
            )

        # ── Results / Grades ─────────────────────────────────────────────────
        elif any(w in action_lower for w in ["result", "grade", "mark", "score"]):
            await _navigate_to_section(page, ["Results", "Grades", "Marks", "Examination"])
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            tables    = await _extract_table(page)
            summary   = _summarise_text_table("Results", tables, page_text)
            return ERPResult(
                success=True, action="results",
                data={"tables": tables}, message=summary, raw_text=page_text[:3000],
            )

        # ── Timetable ────────────────────────────────────────────────────────
        elif any(w in action_lower for w in ["timetable", "schedule", "class", "time table"]):
            await _navigate_to_section(page, ["Timetable", "Time Table", "Schedule", "Classes"])
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            tables    = await _extract_table(page)
            summary   = _summarise_text_table("Timetable", tables, page_text)
            return ERPResult(
                success=True, action="timetable",
                data={"tables": tables}, message=summary, raw_text=page_text[:3000],
            )

        # ── Fees ─────────────────────────────────────────────────────────────
        elif "fee" in action_lower:
            await _navigate_to_section(page, ["Fees", "Fee Payment", "Finance"])
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            tables    = await _extract_table(page)
            summary   = _summarise_text_table("Fee", tables, page_text)
            return ERPResult(
                success=True, action="fees",
                data={"tables": tables}, message=summary, raw_text=page_text[:3000],
            )

        # ── Announcements / Notices ──────────────────────────────────────────
        elif any(w in action_lower for w in ["announce", "notice", "circular", "news"]):
            await _navigate_to_section(
                page, ["Announcements", "Notices", "Circulars", "News", "Notifications"]
            )
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            tables    = await _extract_table(page)
            summary   = _summarise_text_table("Announcements", tables, page_text)
            return ERPResult(
                success=True, action="announcements",
                data={"tables": tables}, message=summary, raw_text=page_text[:3000],
            )

        # ── General dashboard ────────────────────────────────────────────────
        else:
            page_text = await page.inner_text("body")
            return ERPResult(
                success=True, action="dashboard",
                data={},
                message=f"Logged into ERP portal successfully. Dashboard preview:\n{page_text[:1500]}",
                raw_text=page_text[:3000],
            )

    except Exception as e:
        return ERPResult(
            success=False, action=action,
            message=f"ERP automation error: {str(e)}",
        )
    finally:
        try:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
        except Exception:
            pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _summarise_assignments(tables: List[Dict], page_text: str) -> str:
    """Turn extracted table data into a readable assignment summary."""
    if not tables:
        # Try to extract meaningful text from page
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]
        # Filter for assignment-like lines
        relevant = [l for l in lines if any(w in l.lower() for w in
                    ["assignment", "submit", "due", "deadline", "pending", "completed"])]
        if relevant:
            return "📚 **Assignments found on portal:**\n" + "\n".join(relevant[:20])
        return "No assignments table found on the portal page."

    lines = ["📚 **Assignments:**\n"]
    for i, row in enumerate(tables[:15], 1):
        parts = [f"**{k}**: {v}" for k, v in row.items() if v.strip()]
        lines.append(f"{i}. " + " | ".join(parts))
    return "\n".join(lines)


def _summarise_text_table(section: str, tables: List[Dict], page_text: str) -> str:
    """Generic summary from table or page text."""
    if not tables:
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]
        if lines:
            return f"📋 **{section} info from portal:**\n" + "\n".join(lines[:25])
        return f"No {section.lower()} data found."

    out = [f"📋 **{section}:**\n"]
    for i, row in enumerate(tables[:20], 1):
        parts = [f"**{k}**: {v}" for k, v in row.items() if v.strip()]
        out.append(f"{i}. " + " | ".join(parts))
    return "\n".join(out)
