
from __future__ import annotations

# import sys, asyncio
# if sys.platform.startswith("win"):
#     try:
#         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     except Exception:
#         pass
import re
from datetime import datetime, date
import sys
from typing import List, Dict, Any
import numpy as np, pandas as pd
from io import StringIO

## for scraping
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

## imported to check whether BSE is responding
import urllib.request, sys


class Scraper_bse:
    def __init__(self, headless: bool = True, verbose: bool = True):
        # self.base_url = "https://www.bseindia.com/markets/equity/EQReports/StockPrcHistori.html?flag=0"
        self.base_url = "https://www.bseindia.com/markets/equity/EQReports/StockPrcHistori.aspx?expandable=7&scripcode={code}&flag=sp&Submit=G"
        self.quarter_months = {"Mar", "Jun", "Sep", "Dec"}
        self.headless = headless
        self.verbose = verbose

    def _pick_monthly_data(self, html:str)->pd.DataFrame:
        """
        From the HTML page, pick the monthly price table (has columns Month and Close)
        """
        candidates = []
        tables = pd.read_html(StringIO(html))
        print(f"*****this is our number of tables: {len(tables)}")
        # print(f"*****this is our tables: {tables}")

        ## iterating over those
        for t in tables:
            # print(f"this is our t: {t}")
            cols = {str(c).strip().title() for c in t.columns}
            if {'Month', "Close"}.issubset(cols):
                candidates.append(t)
        
        ## If none of the found tables have these columns then we use the beautifulsoup
        if not candidates:
            soup = BeautifulSoup(html, "lxml")
            for tbl in soup.find_all("table"):
                if tbl.find(string = re.compile(r"Month", re.I)) and tbl.find(string = re.compile(r"Close", re.I)):
                    try:
                        raw = pd.read_html(StringIO(str(tbl)))[0]
                        candidates.append(raw)
                        break
                    except Exception as e:
                        print("Even beautiful soup could not find the table")

        if not candidates:
            with open("debug_no_table.html", "w", encoding="utf-8") as f:
                f.write(html)
            raise RuntimeError("Monthly table not found. Saved debug_no_table.html")

        print(f"[DEBUG]: Our candidates that we got are the following:")
        for i, df in enumerate(candidates):
            print(f"[DEBUG]: Candidate {i}: {df.columns.tolist()}")

        
        monthly = candidates[0]
        # print(f"[DEBUG]: This is THE TYPE of the monthly data that we have got: {type(monthly)}")

        if all(re.fullmatch(r"\d+", str(c)) for c in monthly.columns):
            header_row_idx = None
            header_values = None
            # Look in the first few rows for a row that clearly is the header
            for i in range(min(6, len(monthly))):
                row_vals = [str(v).strip() for v in monthly.iloc[i].tolist()]
                tokens_lower = {v.lower() for v in row_vals}
                if "month" in tokens_lower and "close" in tokens_lower:
                    header_row_idx = i
                    header_values = row_vals
                    break
            if header_row_idx is None:
                # Fallback: keep what we have (will likely raise later if not found)
                if self.verbose:
                    print("[WARN] Could not locate header row inside numeric-column table.")
            else:
                if self.verbose:
                    print(f"[INFO] Promoting internal row {header_row_idx} to header: {header_values}")
                # Data starts AFTER that header row; if a second header immediately follows (Month again), drop it later.
                monthly = monthly.iloc[header_row_idx+1:].reset_index(drop=True)
                monthly.columns = header_values
        else:
            # Non-numeric columns (possibly tuples if multi-level); flatten
            flat_cols = []
            for c in monthly.columns:
                if isinstance(c, tuple):
                    parts = [str(p).strip() for p in c if p and str(p).strip().lower() != "nan"]
                    flat_cols.append(parts[-1] if parts else "")
                else:
                    flat_cols.append(str(c).strip())
            monthly.columns = flat_cols

        # Remove any residual duplicate header rows inside the data (where first cell == 'Month')
        if not monthly.empty:
            first_col_name = monthly.columns[0]
            monthly = monthly[monthly[first_col_name].astype(str).str.strip().str.lower() != "month"].reset_index(drop=True)

        # Drop footnote / legend line (starts with "* Spread" or contains "High-Low")
        if not monthly.empty:
            first_col = monthly.columns[0]
            monthly = monthly[~monthly[first_col].astype(str).str.contains(r"\* *Spread|High-?Low", flags=re.I, na=False)].reset_index(drop=True)

        # Strip & clean final column names
        monthly.columns = [c.strip() for c in monthly.columns]

        if self.verbose:
            print("[DEBUG] Normalized columns:", monthly.columns.tolist())
            print("[DEBUG] Sample rows after cleanup:\n", monthly.head(3))

        # Identify Month column (exact match preferred)
        try:
            month_col = next(c for c in monthly.columns if re.fullmatch(r"month", c, flags=re.I))
        except StopIteration:
            month_col = next(c for c in monthly.columns if re.search(r"month", c, flags=re.I))

        # Identify Close column (handles Close, Close*, Close Price, etc.)
        try:
            close_col = next(c for c in monthly.columns if re.fullmatch(r"close\*?", c, flags=re.I))
        except StopIteration:
            close_col = next(c for c in monthly.columns if re.search(r"\bclose\b", c, flags=re.I))

        # Build output
        out = monthly[[month_col, close_col]].rename(columns={month_col: "Month", close_col: "Close"})

        if self.verbose:
            print("[INFO] Parsed monthly columns:", out.columns.tolist())
            print(out.head())

        return out

    def _fetch_monthly_data(self, scrip_code: int, from_year = 2024)->pd.DataFrame:
        """
        Use Playwright to load BSE page, switch to Monthly, set From year, submit,
        and return the full monthly table as a DataFrame.
        """
        filled_url = self.base_url.format(code = str(scrip_code).strip())

        def _preflight(url):
            try:
                req = urllib.request.Request(url, headers={"User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    print("PREFLIGHT_STATUS", r.status, file=sys.stderr)
                    return r.status
            except Exception as e:
                print("PREFLIGHT_FAIL", repr(e), file=sys.stderr)
                return None

        if self.verbose:
            print(f"[INFO] Navigating: {filled_url}")

        def dump(stage, html_text):
            fname = f"debug_stage_{stage}.html"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(html_text)
            if self.verbose:
                print(f"[DEBUG] Saved {fname}")

        ## using the playwright -- this is the old code
        # with sync_playwright() as p:
        #     browser = p.chromium.launch(headless=self.headless)
        #     context = browser.new_context(user_agent=(
        #         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        #         "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        #     ))
        #     page = context.new_page()

        #     # page.set_default_timeout(15000)

        #     ## Load the new page
        #     # page.goto(filled_url, wait_until="load")
        #     page.goto(filled_url, wait_until="domcontentloaded", timeout=120_000)
        #     # Let late scripts (Angular / ASP.NET) finish.
        #     try:
        #         page.wait_for_load_state("networkidle", timeout=8000)
        #     except Exception:
        #         pass -- old code till here


        ## updated new code with better error handling
        """The browser is being launched with additional arguments to enhance stability and compatibility, especially in containerized or restricted environments."""
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args = [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )

            try:
                context = browser.new_context(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                ))
                page = context.new_page()

                # raise navigation timeout so we can see network/blocking issues in logs
                page.set_default_navigation_timeout(180_000)
                page.set_default_timeout(180_000)

                print("[INFO] Performing preflight check...")
                _preflight(filled_url)

                try:
                    page.goto(filled_url, wait_until="domcontentloaded")
                except PWTimeoutError:

                    ## now we have the logs to see what is happening when deployed
                    try:
                        html = page.content()
                        with open("Debug_timeout_goto.html", "w", encoding="utf-8") as f:
                            f.write(html)

                    except Exception:
                        pass

                    try:
                        page.screenshot(path = "/tmp/Debug_timeout_goto.png")
                    except Exception:
                        pass

                    browser.close()
                    raise RuntimeError(f"Timed out loading BSE page for scrip code {scrip_code}. Saved Debug_timeout_goto.html")
                
                ## allow background activity
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass

            except Exception as e:
                pass          

            dump("initial", page.content())

            ## select the monthly
            monthly_selected = False
            radio_attempts = [
                "label:has-text('Monthly')",
                "text=Monthly",
                "xpath=//label[contains(.,'Monthly')]",
                "xpath=//input[@type='radio' and (contains(@id,'Month') or contains(@value,'M'))]"
            ]
            for sel in radio_attempts:
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        tag = loc.evaluate("el => el.tagName")
                        if tag == "INPUT":
                            loc.check(force=True)
                        else:
                            loc.click(force=True)
                        monthly_selected = True
                        break
                except Exception:
                    continue

            if not monthly_selected and self.verbose:
                print("[WARN] Could not assert Monthly radio; continuing anyway.")
                
            page.wait_for_timeout(800) # Gather selects (may be created after radio selection / postback)

            ## assuming the first text box is for the month and the second is for the year
            selects = page.locator("select") ## this is the number of select tags -> click on the area-> click inspect and see the tags
            
            try:
                selects.wait_for(state = "attached", timeout=4000)
            except Exception as e:
                if self.verbose:
                    print("[INFO] No selects at page root yet; will also search frames later.")
            
            dump("after_radio", page.content())

            def set_month_year(root):
                got_month, got_year = False, False
                sels = root.locator("select").count()

                if sels:
                    for i in range(sels):
                        sel = root.locator("select").nth(i)
                        options_text = sel.locator("option").all_text_contents()
                        low = [o.strip().lower() for o in options_text]
                        # Month select guess
                        if any(o.startswith("jan") for o in low) and not got_month:
                            for cand in ["Jan", "JAN", "Jan ", "1", "01"]:
                                try:
                                    sel.select_option(label=cand)
                                    got_month = True
                                    break
                                except Exception:
                                    try:
                                        sel.select_option(cand)
                                        got_month = True
                                        break
                                    except Exception:
                                        continue

                        ## Year select
                        if any(str(from_year) in o for o in low) and not got_year:
                            try:
                                sel.select_option(str(from_year))
                                got_year = True
                            except Exception:
                                try:
                                    sel.select_option(label=str(from_year))
                                    got_year = True
                                except Exception:
                                    pass
                    return got_month, got_year
                return False, False

            month_ok, year_ok = set_month_year(page)
            if self.verbose:
                print(f"[INFO] Month dropdown set: {month_ok}, Year dropdown set: {year_ok}")


            if not (month_ok and year_ok):
                for fr in page.frames:
                    if fr == page.main_frame:
                        continue
                    try:
                        m_ok, y_ok = set_month_year(fr)
                        if m_ok or y_ok:
                            month_ok = month_ok or m_ok
                            year_ok = year_ok or y_ok
                            if self.verbose:
                                print(f"[INFO] Set dropdown(s) inside frame {fr.url}")
                            break
                    except Exception:
                        continue

            dump("after dropdowns", page.content())
            # Old method
            # counts = selects.count()
            # if counts>=2:
            #     got_value = False
            #     for v in ["Jan", "JAN", "1"]:
            #         try:
            #             selects.nth(0).select_option(v)
            #             got_value = True
            #             break
            #         except Exception as e:
            #             pass

            #     ## year dropdown
            #     try:
            #         selects.nth(1).select_option(str(from_year))
            #     except Exception as e:
            #         pass

            ## submit the form

            ## old
            # submitted = False
            # for _ in range(2):
            #     try:
            #         page.get_by_role("button", name=re.compile("submit", re.I)).click(timeout=2500)
            #         submitted = True
            #         break
            #     except Exception:
            #         try:
            #             page.locator("input[type='submit'], button:has-text('Submit')").first.click()
            #             submitted = True
            #             break
            #         except Exception:
            #             page.wait_for_timeout(500)
            # if not submitted and self.verbose:
            #     print("[WARN] Could not positively confirm Submit click.")


            # try:
            #     ## This will basically ensure that the table has been generated as it looks for a "Month" column
            #     page.wait_for_selector("table:has-text('Month')", timeout=15000)
            # except PWTimeoutError:
            #     # Save HTML for debugging
            #     html_debug = page.content()
            #     with open("debug_bse_page.html", "w", encoding="utf-8") as f:
            #         f.write(html_debug)
            #     browser.close()
            #     raise RuntimeError("Timed out waiting for monthly data table. Saved debug_bse_page.html")

            ## new

            submitted = False
            submit_selectors = [
                "button:has-text('Submit')",
                "input[type=submit][value*='Submit' i]",
                "xpath=//input[@type='submit']",
                "xpath=//button[contains(translate(., 'SUBMIT','submit'),'submit')]"
            ]
            for sel in submit_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count():
                        loc.click()
                        submitted = True
                        break
                except Exception:
                    continue

            if not submitted:
                # Try invoking ASP.NET __doPostBack if available
                try:
                    page.evaluate("() => { if (typeof __doPostBack === 'function') __doPostBack('', ''); }")
                    submitted = True
                except Exception:
                    pass

            if self.verbose:
                print(f"[INFO] Submit triggered: {submitted}")

            page.wait_for_timeout(1200)  # allow postback

            dump("after_submit", page.content())

            # Print a short page head to cloud logs so you can inspect remotely
            try:
                head = page.content()[:2000]
                print("[DEBUG][after_submit] page head:\n", head)
            except Exception:
                pass

            table_html = None

            # Primary: wait for a table containing "Month" (longer timeout for cloud)
            try:
                sel = page.wait_for_selector("table:has-text('Month')", timeout=60_000)
                if sel:
                    table_html = sel.evaluate("el => el.outerHTML")
            except PWTimeoutError:
                pass
            except Exception:
                pass

            def find_table_html() -> str | None:
                patterns = [re.compile(r"Month", re.I), re.compile(r"Close", re.I)]
                # Search every frame
                for fr in page.frames:
                    try:
                        tables = fr.locator("table")
                        count = tables.count()
                        for i in range(count):
                            tloc = tables.nth(i)
                            txt = tloc.inner_text(timeout=2000)
                            if all(p.search(txt) for p in patterns):
                                return tloc.evaluate("el => el.outerHTML")
                    except Exception:
                        continue
                return None
            
            table_html = None
            for _ in range(8):  # ~ up to ~8 * 1s = 8 seconds
                table_html = find_table_html()
                print("In the final loop of table")
                if table_html:
                    break
                page.wait_for_timeout(10000) ## this is 10 seconds  

            if not table_html:
                dump("no_table_final", page.content())
                try:
                    full = page.content() ## saving so that I can see on logs
                    print("[DEBUG] Saved final page content for debugging.")
                except Exception as e:
                    print("[ERROR] Failed to save final page content:", e)
                browser.close()
                raise RuntimeError("Monthly data table not found (even after submit & frame scan). See debug_stage_* files.")

             # Build a minimal HTML fragment so _pick_monthly_data can parse
            fragment = f"<html><body>{table_html}</body></html>"
            if self.verbose:
                print("[INFO] Monthly table captured; parsing...")
            
            browser.close()

            # print(f"this is the html: {html}")

            # df = self._pick_monthly_data(html)

            # ##
            # df_cols = [str(c).strip().title() for c in df.columns]
            # needed = [c for c in ["Month", "Close"] if c in df_cols]
            # return df[needed].copy()

            ## since we make the month and column in the df in the parse_monthly function
            ## here we just return the df

            return self._pick_monthly_data(fragment)
    
    
    def _extract_qtrly_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return only quarter months and format date as 'mar 2024'."""
        if not {"Month", "Close"}.issubset(df.columns):
            raise ValueError("DataFrame must contain 'Month' and 'Close' columns")

        rows: List[dict] = []
        for _, r in df.iterrows():
            m_raw = str(r["Month"]).strip()
            # Expected like 'Mar 24' or 'Mar 2024'
            parts = m_raw.split()
            if len(parts) < 2:
                continue
            mon_abbr = parts[0].title()
            if mon_abbr not in self.quarter_months:
                continue
            yy = int(parts[1])
            year = 2000 + yy if yy < 100 else yy

            # Close → float; BSE sometimes uses commas elsewhere, Close usually doesn't
            try:
                close = float(str(r["Close"]).replace(",", ""))
            except Exception:
                close = pd.NA

            rows.append({"Quarter End": f"{mon_abbr.lower()} {year}", "Close": close})

        out = pd.DataFrame(rows).dropna(subset=["Close"]).reset_index(drop=True)
        # Sort by year/quarter
        if not out.empty:
            out["__key"] = out["Quarter End"].apply(
                lambda s: (int(s.split()[1]), ["mar","jun","sep","dec"].index(s.split()[0]))
            )
            out = out.sort_values("__key", ascending=False).drop(columns="__key").reset_index(drop=True)
        return out

    
    def _get_qtrly_dates(self, scrip_code: int, from_year: int = 2024):
        df = self._fetch_monthly_data(scrip_code, from_year)
        print("our df after the step", df)
        return self._extract_qtrly_dates(df)


## Just for checking
if __name__ == "__main__":
    s = Scraper_bse(headless=True, verbose=True)
    # TATA POWER = 500400, RELIANCE = 500325, TCS = 532540
    df = s._get_qtrly_dates(500400, from_year=2025)
    print(df.head(12))