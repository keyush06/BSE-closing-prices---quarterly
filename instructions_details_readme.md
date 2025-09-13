## This repository is rendering a website that fetches quaterly prices from the Bombay Stock Exchnage (BSE). 
> There were two methods that I used (the second being an improvement of the first for fetching the results faster - the fetching time reduced by more than 500 times!)

> Here is the rendered application: https://bse-app-462019151429.asia-south1.run.app/

### Method 1
- Launch Chromium (headless), navigate to the BSE history URL for a scrip code, wait for DOM/network to settle; do a lightweight preflight request and save HTML snapshots for debugging.
- Switch the view to “Monthly,” then detect and set the month/year from the "select" tags in HTML (also searches the frames) using tolerant matching (e.g., Jan/JAN/01 and target year).
- Submit using multiple selectors or fallback to __doPostBack, then wait for the postback and locate the resulting table by scanning the page and frames for a table containing "Month" and "Close."
- Parse the captured table HTML with pandas.read_html, normalize headers (promote header rows, flatten multi-index), drop duplicate header/footnote rows, and return a DataFrame with Month and Close.
- Post-process to quarter-end data by filtering Mar/Jun/Sep/Dec and formatting “Quarter End,” converting Close to numeric, and sorting.

### Method 2
- **Direct WebForms flow (no browser):** <br>
Do one initial GET to the BSE page to grab the ASP.NET tokens (__VIEWSTATE, __EVENTVALIDATION, __VIEWSTATEGENERATOR) and the currently selected settlement value.
Parse all input fields with BeautifulSoup, then **construct a POST payload that mirrors the real form: scrip code in hdnCode/hiddenScripCode, DMY=rdbMonthly, hidDMY=M, cmbMonthly/cmbMYear, and mirror the visible name fields from hidCompanyVal.**

- **Single POST to get results:** <br>
Submit the payload back to the same URL using requests.Session (cookie + TCP reuse).
Session reuse avoids an extra handshake and keeps the state consistent (like a browser would).

- **Parse only what’s needed:** <br>
From the returned HTML, find the table that contains “Month” and “Close” under ContentPlaceHolder1_divStkData. Use pandas.read_html to parse that table; clean headers and return just [Quarter End, Close].
If parsing fails, trigger the server “Download” postback and parse the CSV/HTML download as a fallback.

### Instructions to Implement

Prerequisites
- Windows: Python 3.11+ (or 3.12), Git, Docker Desktop.
- Google Cloud: Billing enabled, gcloud CLI or Cloud Shell.

1) Windows: create and use a virtual environment
```powershell
# from repo root
py -3 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

2) Optional: run Streamlit locally (without Docker)
```powershell
streamlit run frontend/app.py
```

3) Build and test Docker locally
```powershell
# build
docker build -t bse-app:local -f Dockerfile .

# run on host port 8080 and pass PORT=8080 to the container
docker run --rm --name bse-local -p 8080:8080 -e PORT=8080 bse-app:local

# browse: http://localhost:8080
```

4) Push image to Artifact Registry (Cloud Shell recommended)

Cloud Shell (bash) — set variables, enable APIs, create repo:
```bash
export PROJECT_ID="YOUR_PROJECT_ID"          # e.g. modern-force-471020-s4
export REGION="asia-south1"                  # choose your region
export REPO="bse-repo"

gcloud config set project "$PROJECT_ID"
gcloud services enable artifactregistry.googleapis.com run.googleapis.com cloudbuild.googleapis.com

gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Docker repo for BSE app"
```

Build and push with Cloud Build (single command):
```bash
# tag with a timestamp so you know what you deployed
TAG=$(date +%s)
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/bse-app:${TAG} .
```

5) Deploy to Cloud Run
```bash
gcloud run deploy bse-app \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/bse-app:${TAG} \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080
```

6) Verify and logs
```bash
# show service URL
gcloud run services describe bse-app --region "$REGION" --format='value(status.url)'

# read recent logs
gcloud logs read --region "$REGION" --service bse-app --limit 200 --format='value(textPayload)'
```

7) Update (rebuild and redeploy)
```bash
TAG=$(date +%s)
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/bse-app:${TAG} .
gcloud run deploy bse-app --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/bse-app:${TAG} --region "$REGION" --allow-unauthenticated --port 8080
```

Notes
- The Dockerfile must bind Streamlit to Cloud Run’s PORT. Current CMD:
  exec streamlit run frontend/app.py --server.address=0.0.0.0 --server.port=${PORT:-8080}
- In Cloud Run, do not override command/args; leave “Container port” empty or 8080.
- If APIs fail to enable, ensure billing is linked to the project (Console → Billing → Link).
