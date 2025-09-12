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
# from bse_scraper import Scraper_bse as bse
from bse_scraper_v2 import bse_scraper_2 as bse

## defining our class
# s = bse(headless=True, verbose=False)
s = bse()


## App UI
st.set_page_config(page_title="BSE Quarter-End Closes", layout="centered")

st.markdown("""
<style>
/* Page background: blue gradient + subtle texture */
.stApp {
  background-image:
    linear-gradient(135deg, rgba(0,82,161,0.20) 0%, rgba(0,163,224,0.20) 100%),
    url('https://www.transparenttextures.com/patterns/cubes.png');
  background-attachment: fixed;
  background-size: cover;
}

/* Card-like container */
.main .block-container {
  background: rgba(255,255,255,0.92);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.12);
  backdrop-filter: blur(3px);
  padding: 2rem 2rem 2.5rem 2rem;
}

/* Headers and captions */
h1, h2, h3 { color: #003D66; }
.stMarkdown, .stCaption, p { color: #1d3557cc; }

/* Highlight the source/caption line */
.stCaption {
  font-size: 15px;
  font-weight: 600;
  color: #003D66;
  background: linear-gradient(90deg, rgba(0,163,224,0.06), rgba(0,82,161,0.03));
  border-left: 4px solid #0052A1;
  padding: 8px 12px;
  border-radius: 6px;
  display: inline-block;
  margin-bottom: 1rem;
}

/* Input labels (make headers bigger) */
.stTextInput > label, .stNumberInput > label,
.stTextInput > div > label, .stNumberInput > div > label {
  font-size: 18px;
  font-weight: 600;
  color: #003D66;
  margin-bottom: 6px;
  display: block;
}

/* Input fields (larger, more airy) */
.stTextInput > div > div > input,
.stNumberInput input {
  border-radius: 10px !important;
  border: 1px solid #0052A133 !important;
  font-size: 16px;
  padding: 12px 14px !important;
  height: auto !important;
}

/* Primary button */
.stButton > button {
  background: linear-gradient(90deg,#0052A1,#00A3E0);
  color: #fff;
  border: 0;
  padding: 0.6rem 1.2rem;
  border-radius: 10px;
  box-shadow: 0 10px 24px rgba(0,82,161,0.22);
  font-size: 15px;
  font-weight: 600;
}
.stButton > button:hover { filter: brightness(1.05); }

/* Download button */
.stDownloadButton > button {
  background: #0B8457;
  color: #fff;
  border: 0;
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(11,132,87,0.28);
}

/* Dataframe frame */
.stDataFrame {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.10);
}
</style>
""", unsafe_allow_html=True)

st.title("BSE Quarter-End Closing Prices")
st.caption("Source: bseindia.com monthly history. Enter a 6-digit BSE scrip code (e.g., 500325 for RELIANCE, 500400 for TATAPOWER).")

scrip_code = st.text_input("BSE Scrip Code", value="500400").strip()
from_year = st.number_input("From year", min_value=2000, max_value=pd.Timestamp.today().year, value=2024, step=1)

## New code for bse_scraper 2
from_month = st.number_input("From month", min_value=1, max_value=12, value=1, step=1)
# to_month = st.number_input("To month", min_value=1, max_value=12, value=12, step=1)
# to_year = st.number_input("To year", min_value=2000, max_value=pd.Timestamp.today().year, value=2025, step=1)

if st.button("Get Prices"):
    if not scrip_code.isdigit():
        st.error("Please enter a numeric 6-digit BSE scrip code.")
    else:
        with st.spinner("Fetching from BSE..."):
            try:
                # df = s._get_qtrly_dates(scrip_code, from_year=int(from_year))
                df = s._get_monthly_table(scrip_code, from_year=int(from_year), from_month=int(from_month))
                df = s._get_quarterly_dates(df)
        
                # st.write("DEBUG: returned", "shape:", getattr(df, "shape", None))

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
                st.error(f"Failed to fetch data: The dates are wrong or the scrip code is invalid.")
                # st.info("If this persists, selectors on BSE may have changed; see bse_quarterlies.py comments to tweak month/year/submit selectors.")