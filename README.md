# Ameritas Life Insurance — Chatbot Integration API

A Python 3.9.6 REST API that powers the Ameritas demo chatbot on **Omilia Cloud Platform**.  
Hosted on **Render**, reads live data from **Google Sheets**.

---

## Table of Contents
1. [API Endpoints Reference](#api-endpoints)
2. [Authentication Flow](#authentication-flow)
3. [Local Development](#local-development)
4. [Google Sheets Setup](#google-sheets-setup)
5. [Deploy to Render](#deploy-to-render)
6. [Connect to GitHub](#connect-to-github)
7. [Omilia Integration Notes](#omilia-integration-notes)
8. [Demo Data Cheat Sheet](#demo-data-cheat-sheet)

---

## API Endpoints

Base URL (after Render deploy): `https://ameritas-chatbot-api.onrender.com`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check (Render ping) |
| POST | `/auth` | Authenticate caller |
| GET | `/policy/{id}/info` | Policy details |
| GET | `/policy/{id}/cash-value` | Cash value & loan info |
| GET | `/policy/{id}/billing` | Premium & billing status |
| POST | `/policy/{id}/payment` | Mock premium payment |
| GET | `/policy/{id}/reinstatement` | Lapse & reinstatement info |
| POST | `/policy/{id}/reinstatement` | Initiate mock reinstatement |

---

## Authentication Flow

### Request
```
POST /auth
Content-Type: application/json

{
  "policy_number": "LI-2847391",
  "dob": "1975-04-12",
  "ssn_last4": "4821"
}
```

### Success Response
```json
{
  "status": "authenticated",
  "policy_number": "LI-2847391",
  "policyholder_name": "James Mitchell",
  "message": "Welcome, James Mitchell. Authentication successful."
}
```

### Failure Response
```json
{
  "status": "error",
  "error_code": "AUTH_FAILED",
  "message": "Authentication failed. DOB or SSN does not match."
}
```

> **Omilia tip:** Map `status == "authenticated"` to your success path. Store `policy_number` in a session variable for all subsequent calls.

---

## Policy Information

```
GET /policy/LI-2847391/info
```

Returns: `policy_type`, `policy_status`, `effective_date`, `coverage_amount`, `death_benefit`, `premium_amount`, `premium_frequency`, `cash_value`, `riders`, beneficiaries.  
Also returns a `message` field with a plain-English summary ready to hand to Omilia's TTS.

---

## Cash Value & Loan

```
GET /policy/LI-2847391/cash-value
```

Returns: `current_cash_value`, `available_loan`, `existing_loan_balance`, `net_available_loan`, `loan_interest_rate`, `tax_implications`.  
Term life policies return `"status": "not_applicable"` with an explanatory `message`.

---

## Billing & Premium Payment

### View billing status
```
GET /policy/LI-2847391/billing
```

Returns: `premium_amount`, `due_date`, `last_payment_date`, `outstanding_balance`, `lapse_warning`, `grace_period_expiry`.  
`lapse_warning` values: `"No"` | `"Yes"` | `"Lapsed"`.

### Submit a payment (mock)
```
POST /policy/LI-2847391/payment
Content-Type: application/json

{
  "amount": "$287.50",
  "payment_method": "ACH"
}
```
Both fields are optional — defaults to the premium amount and method on file.

---

## Lapse & Reinstatement

### Get reinstatement details
```
GET /policy/LI-3384920/reinstatement
```

### Initiate reinstatement (mock)
```
POST /policy/LI-3384920/reinstatement
Content-Type: application/json

{ "confirm": true }
```

`reinstatement_status` values: `"Eligible – Pending"` | `"In Review"` | `"Reinstated"` | `"Denied"` | `"Pre-Lapse Warning"`.

---

## Local Development

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_ORG/ameritas-chatbot-api.git
cd ameritas-chatbot-api

# 2. Create a virtual environment
python3.9 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add your GOOGLE_CREDENTIALS_JSON or leave blank for mock data

# 5. Run
python app.py
# API available at http://localhost:5000
```

If Google credentials are not set, the API automatically falls back to the **mock data** embedded in `sheets.py`. All endpoints will work; they just won't reflect live sheet changes.

---

## Google Sheets Setup

The API reads from:  
**Sheet ID:** `1jLlqZ8rOsD5kkGwm0nkRQji0q6mfAyN2`

### Steps to wire up live data

1. **Create a Google Cloud project**  
   Go to https://console.cloud.google.com → New Project

2. **Enable APIs**  
   Library → enable **Google Sheets API** and **Google Drive API**

3. **Create a Service Account**  
   IAM & Admin → Service Accounts → Create  
   Role: `Viewer` is sufficient

4. **Download the key**  
   Service Account → Keys → Add Key → JSON  
   Save the file. **Do not commit it to git.**

5. **Share the Google Sheet with the service account**  
   Open the sheet → Share → paste the service account email (e.g. `ameritas-bot@your-project.iam.gserviceaccount.com`) → Viewer

6. **Set the environment variable**
   ```bash
   # Paste the entire JSON on one line
   export GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'
   ```

---

## Deploy to Render

### First time
1. Push code to GitHub (see next section)
2. Go to https://dashboard.render.com → **New Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — confirm the settings
5. Add environment variable:
   - Key: `GOOGLE_CREDENTIALS_JSON`
   - Value: paste the full contents of your service account JSON (single line or multi-line — Render handles both)
6. Click **Deploy**

### After the first deploy
Render will auto-deploy on every push to `main`.  
Your base URL will be: `https://ameritas-chatbot-api.onrender.com`

> **Free tier cold starts:** Render's free plan spins down after 15 minutes of inactivity. The first request after a cold start takes ~30 seconds. For demo reliability, upgrade to the **Starter plan ($7/mo)** or set up an external ping (e.g. UptimeRobot) to keep the service warm.

---

## Connect to GitHub

```bash
# In your project directory:
git init
git add .
git commit -m "Initial commit — Ameritas chatbot API"

# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_ORG/ameritas-chatbot-api.git
git branch -M main
git push -u origin main
```

---

## Omilia Integration Notes

### Why responses are structured this way

Omilia Cloud Platform has two known quirks when consuming external REST APIs:

**1. Response body parsing failures**  
Omilia's HTTP connector reads the body as a raw byte stream and maps fields via JSONPath. Chunked transfer encoding (`Transfer-Encoding: chunked`) can cause fields to be silently dropped. To prevent this:
- We set `Content-Length` explicitly on every response (forces non-chunked)
- We use `json.dumps()` + `Response()` instead of Flask's `jsonify()`, which can produce chunked output on some WSGI configs
- All payloads are UTF-8 encoded

**2. Timeout = 0 / premature connection close**  
If Omilia's connector timeout is set to `0` (or very low), it may close the connection before reading the full body. To prevent this:
- Responses include `Content-Length` so the client knows exactly when the body ends
- Gunicorn is configured with `--timeout 30` (generous for our sub-1s responses)
- `--keep-alive 2` avoids lingering connection overhead

**3. Always HTTP 200**  
Omilia's default error handling fires on any non-2xx status. All responses return HTTP 200; the `status` field in the JSON body signals success or failure. Handle `status == "error"` in your Omilia flow logic.

### Recommended Omilia connector settings

| Setting | Recommended Value |
|---------|-------------------|
| HTTP Method | Match endpoint (GET or POST) |
| Content-Type | `application/json` |
| Timeout (ms) | `10000` (10 seconds) |
| Retry on failure | 1 retry |
| JSONPath for success check | `$.status` |
| Success condition | `== "authenticated"` / `== "success"` / `== "payment_accepted"` etc. |

### Session variable pattern for Omilia

```
1. User calls → POST /auth → store policy_number in $session.policyNumber
2. All subsequent calls → GET /policy/$session.policyNumber/info
                         GET /policy/$session.policyNumber/billing
                         etc.
```

---

## Demo Data Cheat Sheet

| Policyholder | Policy # | DOB | SSN Last 4 | Scenario |
|---|---|---|---|---|
| James Mitchell | LI-2847391 | 1975-04-12 | 4821 | Active Whole Life, loan approved, at-risk of lapse |
| Patricia Nguyen | LI-3019284 | 1968-09-30 | 7743 | Active Term Life, no cash value |
| Marcus Williams | LI-4401857 | 1982-06-15 | 3302 | Active Universal Life, existing loan |
| Sandra Torres | LI-2201934 | 1960-11-22 | 5589 | Active Whole Life, **missed Feb payment**, grace period |
| Brian Chen | LI-5590123 | 1990-03-08 | 9910 | Active Term Life, no loan available |
| Olivia Grant | LI-3384920 | 1978-07-19 | 6621 | **Lapsed policy**, eligible for reinstatement |
| Kevin Park | LI-6670045 | 1985-12-01 | 2284 | Active IUL, loan approved |

---

## File Structure

```
ameritas-chatbot-api/
├── app.py              # Flask API — all endpoints and Omilia response logic
├── sheets.py           # Google Sheets data layer + embedded mock data
├── requirements.txt    # Pinned Python dependencies
├── render.yaml         # Render deploy config
├── .env.example        # Environment variable template
├── .gitignore
└── README.md
```
