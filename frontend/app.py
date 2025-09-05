import asyncio
import sys
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st 
# from bse_scraper import Scraper_bse as bse
import pandas as pd
from pathlib import Path

# print("before: ",sys.path)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# print("after: ",sys.path)
## importing after adding to the system path!
from bse_scraper import Scraper_bse as bse

## defining our class
s = bse(headless=True, verbose=False)

## App UI
st.set_page_config(page_title="BSE Quarter-End Closes", layout="centered")

st.title("BSE Quarter-End Closing Prices")
st.caption("Source: bseindia.com monthly history. Enter a 6-digit BSE scrip code (e.g., 500325 for RELIANCE, 500400 for TATAPOWER).")

scrip_code = st.text_input("BSE Scrip Code", value="500400").strip()
from_year = st.number_input("From year", min_value=2000, max_value=pd.Timestamp.today().year, value=2024, step=1)

if st.button("Get Prices"):
    if not scrip_code.isdigit():
        st.error("Please enter a numeric 6-digit BSE scrip code.")
    else:
        with st.spinner("Fetching from BSE..."):
            try:
                df = s._get_qtrly_dates(scrip_code, from_year=int(from_year))
                st.write("DEBUG: returned", "shape:", getattr(df, "shape", None))

                if df is None:
                    st.error("Scraper returned None (check _get_qtrly_dates returns a DataFrame)")

                elif isinstance(df, pd.DataFrame) and df.empty:
                    st.warning("No quarter-end data found. Check the scrip code or try another.")
                
                else:
                    # pretty display
                    show = df.copy()
                    show["Quarter End"] = show["Quarter End"].astype(str)
                    st.dataframe(show, width="stretch")
                    st.download_button(
                        "Download CSV",
                        data=show.to_csv(index=False).encode(),
                        file_name=f"bse_quarterlies_{scrip_code}.csv",
                        mime="text/csv"
                    )
            except Exception as e:
                st.error(f"Failed to fetch data: {e}")
                st.info("If this persists, selectors on BSE may have changed; see bse_quarterlies.py comments to tweak month/year/submit selectors.")