import datetime as dt
import requests
from bs4 import BeautifulSoup
import pandas as pd
# from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os, sys
from io import StringIO
import re

class bse_scraper_2:
    def __init__(self):
        self.base_url = "https://www.bseindia.com"
        self.path = (
            "/markets/equity/EQReports/StockPrcHistori.aspx"
            "?expandable=7&scripcode={code}&flag=sp&Submit=G"
        )
        self.agent = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
        }

    def _get_settlement_value(self, soup: BeautifulSoup) -> Optional[str]:
        sel = soup.find("select", id="ContentPlaceHolder1_ddlsetllementcal")
        if not sel:
            return None
        
        option = sel.find("option", selected=True)
        if option:
            return option["value"] ## this should be value 0 which corresponds to Equity T + 1
        return None

    def _find_monthly_table_html(self, html:str)->Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        given_root = soup.find(id="ContentPlaceHolder1_divStkData") or soup
        table = given_root.find("table")

        ## this will definitely have columns "Month" and "Close"
        for tbl in given_root.find_all("table"):
            header_text = tbl.get_text(" ", strip=True)
            if re.search(r"\bMonth\b", header_text, re.I) and re.search(r"\bClose\b", header_text, re.I):
                return str(tbl)
        return None

    def _collect_inputs(self, soup):
        payload = {}
        for tag in soup.find_all(["input"]): # Not needed now "textarea", "select"
            if not tag.has_attr("name"):
                continue
            name = tag["name"]
            value = tag.get("value", "")

            payload[name] = value
        return payload
    
    def _decompose_monthly_table(self, table:str) -> pd.DataFrame:
        actual_table = self._find_monthly_table_html(table) or table
        tables = pd.read_html(StringIO(actual_table), header=0)

        for table in tables:
            # print("[DEBUG] this is our table",table)
            # table = table.iloc[1:,:]
            table.columns = table.iloc[0]
            table = table.iloc[1:,:].reset_index(drop=True)

            # print("[DEBUG] this is our table after setting columns",table.columns)
            cols = [str(c).strip().title() for c in table.columns]
            # print("[DEBUG] this table!!!", table)
            if all(c in cols for c in ["Month", "Close"]):
                df = table[["Month", "Close"]].copy()
                df.rename(columns={"Month": "Quarter End", "Close": "Close"}, inplace=True)
                return df
        raise ValueError("Could not find the expected table with 'Month' and 'Close' columns.")
                

    def _get_monthly_table(self, script_code: int, from_month: int, from_year: int, to_month: Optional[int] = None, to_year: Optional[int] = None) -> pd.DataFrame:
        BASE = self.base_url + self.path
        BASE = BASE.format(code=script_code)
        print("Fetching data from:", BASE)

        mm = f"{from_month:02d}"
        yyyy = str(from_year)

        with requests.Session() as s:

            ## first we get the html file to retrieve all the inputs that we will later use to post the form
            r = s.get(BASE, headers=self.agent, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")

            # baseline payload (all inputs present) + override essentials
            payload = self._collect_inputs(soup)

            ## some checks for the .NET tokens
            for k in ("__VIEWSTATE", "__EVENTVALIDATION", "__VIEWSTATEGENERATOR"):
                if not payload.get(k): raise RuntimeError(f"Missing token: {k}")
            
            # Keep current settlement selection
            settlement_value = self._get_settlement_value(soup)
            if settlement_value is not None:
                payload["ctl00$ContentPlaceHolder1$ddlsetllementcal"] = settlement_value


            ## Now we add more required tokens to form the complete payload
            payload.update({
                ## Indicating the code by the user
                "ctl00$ContentPlaceHolder1$hdnCode": str(script_code),
                "ctl00$ContentPlaceHolder1$hiddenScripCode": str(script_code),

                ## indicating the monthly data
                "ctl00$ContentPlaceHolder1$DMY": "rdbMonthly",
                "ctl00$ContentPlaceHolder1$hidDMY": "M",
                "ctl00$ContentPlaceHolder1$cmbMonthly": mm,
                "ctl00$ContentPlaceHolder1$cmbMYear": yyyy,

                # optional mirrors; harmless and often present
                "ctl00$ContentPlaceHolder1$hidFromDate": f"01/{mm}/{yyyy}",
                "ctl00$ContentPlaceHolder1$hidToDate": dt.date.today().strftime("%d/%m/%Y"),

                # "ctl00$ContentPlaceHolder1$btnSubmit": "Submit",
                # Proper WebForms postback
                # "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnSubmit",
                "__EVENTTARGET": "", ## as per my check, this is empty string
                "__EVENTARGUMENT": "",

            })

            ## checking all the required fields are present
            required_fields = [
                "__EVENTTARGET", "__EVENTARGUMENT",
                "__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION", "__VIEWSTATEENCRYPTED",
            "ctl00$ContentPlaceHolder1$hdnCode",
            "ctl00$ContentPlaceHolder1$DDate",
            "ctl00$ContentPlaceHolder1$hidDMY",
            "ctl00$ContentPlaceHolder1$hdflag",
            "ctl00$ContentPlaceHolder1$hidCurrentDate",
            "ctl00$ContentPlaceHolder1$hidYear",
            "ctl00$ContentPlaceHolder1$hidFromDate",
            "ctl00$ContentPlaceHolder1$hidToDate",
            "ctl00$ContentPlaceHolder1$hidOldDMY",
            "ctl00$ContentPlaceHolder1$hiddenScripCode",
            "ctl00$ContentPlaceHolder1$hidCompanyVal",
            "ctl00$ContentPlaceHolder1$ddlsetllementcal",
            "ctl00$ContentPlaceHolder1$Hidden1",
            "ctl00$ContentPlaceHolder1$smartSearch",
            "ctl00$ContentPlaceHolder1$scripname",
            "ctl00$ContentPlaceHolder1$Hidden4",
            "ctl00$ContentPlaceHolder1$smartSearch_TO",
            "ctl00$ContentPlaceHolder1$scriptnameTO",
            "ctl00$ContentPlaceHolder1$Hidden2",
            "ctl00$ContentPlaceHolder1$smartSearch_mf",
            "ctl00$ContentPlaceHolder1$scriptnamemf",
            "ctl00$ContentPlaceHolder1$Hidden3",
            "ctl00$ContentPlaceHolder1$smartSearch_Debt",
            "ctl00$ContentPlaceHolder1$ScriptnameDebt",
            "ctl00$ContentPlaceHolder1$DMY",
            "ctl00$ContentPlaceHolder1$cmbMonthly",
            "ctl00$ContentPlaceHolder1$cmbMYear",
            "ctl00$ContentPlaceHolder1$btnSubmit"
            ]
            # not_present = [element for element in required_fields if element not in payload]
            # present_vals = [print(f"{element}={payload[element]}") for element in required_fields if element in payload]

            """ Debugging info"""

            # [DEBUG 1]
            # for element in required_fields:
            #     if element in payload:
            #         print(f'{element}={payload[element]}')

            # [DEBUG 2]
            # print("Payload check, missing fields:", not_present)
            # print("payload elements: ", present_vals)
            """
            So, after checking all the fields, we do not need any value in Hidden1 so I am going to leave that.
            apart from that, I am going to populate all the fields that are missing with the name of the hidCompanyVal
            like RELIANCE or TATAPOWER or whatever the scrip code is.

            ** Also check hidToDate was empty in Network->Payload: If any errors then fallback to an empty date as it is in the original form.
            """

            payload["ctl00$ContentPlaceHolder1$smartSearch"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")
            payload["ctl00$ContentPlaceHolder1$Hidden4"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")
            payload["ctl00$ContentPlaceHolder1$smartSearch_TO"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")
            payload["ctl00$ContentPlaceHolder1$Hidden2"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")
            payload["ctl00$ContentPlaceHolder1$smartSearch_mf"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")
            payload["ctl00$ContentPlaceHolder1$Hidden3"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")
            payload["ctl00$ContentPlaceHolder1$smartSearch_Debt"] = payload.get("ctl00$ContentPlaceHolder1$hidCompanyVal", "")



            ## post the form
            r1 = s.post(
                BASE,
                headers = {"Referer": BASE, **self.agent},
                data = payload,
                timeout=20
            )

            r1.raise_for_status()

            ## we will now parse the resulting html to extract the table
            try:
                df = self._decompose_monthly_table(r1.text)
                df["Close"] = pd.to_numeric(
                    df["Close"].astype(str).str.replace(",", ""), errors="coerce"
                )

                return df
            
            except Exception:
                # Fallback: use the Download postback (often returns CSV)
                dl_payload = payload.copy()
                dl_payload["__EVENTTARGET"] = "ctl00$ContentPlaceHolder1$btnDownload"
                r2 = s.post(
                    BASE,
                    headers={"Referer": BASE, **self.agent},
                    data=dl_payload,
                    timeout=45
                )
                r2.raise_for_status()
                df = pd.read_csv(StringIO(r2.text))
                month_col = next((c for c in df.columns if re.search(r"\bmonth\b", str(c), re.I)), None)
                close_col = next((c for c in df.columns if re.search(r"\bclose\b", str(c), re.I)), None)
                if not (month_col and close_col):
                    raise ValueError("Download did not return recognizable Month/Close columns.")
                df = df[[month_col, close_col]].copy()
                df.columns = ["Quarter End", "Close"]

            df["Close"] = pd.to_numeric(df["Close"].astype(str).str.replace(",", ""), errors="coerce")
            return df
        
    ## Now we have to just get the quarters from the list
    def _get_quarterly_dates(self, df: pd.DataFrame)->pd.DataFrame:
        df_qtr = df.copy()
        quarterly_months = ["Mar", "Jun", "Sep", "Dec"]
        # print("DEBUG: data types of date column: \n", df_qtr.dtypes)

        # print("[DEBUG]: original df", df)
        df_qtr = df_qtr[df_qtr["Quarter End"].astype(str).str.slice(0,3).isin(quarterly_months)]
        return df_qtr
    
    def _calculate_next_month_year(self, df:pd.DataFrame)->tuple:
        """ This function will calculate the next month and year from the last entry in the dataframe"""
        df_last = df.iloc[-1]["Quarter End"]
        last_year = int("20"+ df_last.split()[-1])
        last_month_str = df_last.split()[0]

        print(f"[DEBUG] Last entry in the dataframe is for {last_month_str} {last_year}")
        
        monthly_mapping = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
            "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
            "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
        }
        last_month_int = monthly_mapping.get(last_month_str, None)
        if last_month_int is None:
            raise ValueError(f"Could not parse month from string: {last_month_str}")

        if last_month_int < 12:
            next_month_int = last_month_int + 1
            next_year = last_year
        else:
            next_month_int = 1
            next_year = last_year + 1

        return next_month_int, next_year
    
    def _recurse_until_today(self, script_code:int, from_month:int, from_year:int)->pd.DataFrame:
        """ This function will keep calling _get_monthly_table until we reach current month and year"""
        current_date = dt.date.today()
        current_month = current_date.month
        current_year = current_date.year

        ## first itertion
        df = self._get_monthly_table(script_code, from_month, from_year)

        next_month, next_year = self._calculate_next_month_year(df)
        while (next_year <= current_year) and (next_month <= current_month):
            print(f"[INFO] Fetching data for {next_month:02d}/{next_year}")
            df_next = self._get_monthly_table(script_code, next_month, next_year)
            df = pd.concat([df, df_next], ignore_index=True)

            next_month, next_year = self._calculate_next_month_year(df)

        return df


if __name__ == "__main__":
    scraper = bse_scraper_2()

    """Add this functionality to_month and to_year later"""
    # df = scraper._get_monthly_table(500400, 3, 2024, 12, 2024) 
    # df = scraper._get_monthly_table(500400, 3, 2015)

    """Testing iterating over upto the current month and year"""
    df = scraper._recurse_until_today(500400, 3, 2020)
    df = scraper._get_quarterly_dates(df)
    print(df)
