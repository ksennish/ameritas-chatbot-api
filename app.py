"""
Ameritas Life Insurance - Chatbot Integration API
--------------------------------------------------
Designed for Omilia Cloud Platform integration.

OMILIA COMPATIBILITY NOTES:
- All responses use explicit Content-Type: application/json
- Response bodies are flat, UTF-8 encoded JSON strings
- No streaming, no chunked transfer encoding
- Every endpoint returns within 5 seconds (Omilia timeout safety)
- CORS headers included for all origins
- Connection: keep-alive is NOT used (Omilia prefers short-lived connections)
- All HTTP 200 responses — Omilia reads the "status" field in the body to determine success/failure

Python version: 3.9.6
Deploy target: Render (https://render.com)
"""

import json
import logging
import os
from datetime import datetime
from functools import wraps

from flask import Flask, Response, request
from flask_cors import CORS

import sheets

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Allow all origins — Omilia sends requests from variable IPs


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------

def omilia_response(payload: dict, http_status: int = 200) -> Response:
    """
    Build a Flask Response that Omilia Cloud Platform can reliably parse.

    IMPORTANT: Omilia's MiniApp/DiaManT expects all response fields to live
    inside a top-level `wsResponseBody` wrapper. Without this wrapper the
    MiniApp reports 'Tool doesn't contain wsResponseBody' and fails.

    Key design decisions:
    1. All payload fields are nested under `wsResponseBody`
    2. json.dumps with ensure_ascii=False avoids double-encoding issues
    3. Content-Type is set explicitly on the Response object
    4. We do NOT use jsonify() — it can produce chunked responses
    5. Content-Length is set so Omilia knows exactly when the body ends
       and does not hang waiting (timeout = 0 workaround)
    """
    wrapped = {"wsResponseBody": payload}
    body = json.dumps(wrapped, ensure_ascii=False, default=str)
    encoded = body.encode("utf-8")

    resp = Response(
        response=encoded,
        status=http_status,
        mimetype="application/json",
    )
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    resp.headers["Content-Length"] = str(len(encoded))
    resp.headers["Cache-Control"] = "no-cache, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

# ---------------------------------------------------------------------------
# Request logging decorator
# ---------------------------------------------------------------------------

def log_request(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        logger.info("REQUEST  %s %s | body=%s", request.method, request.path, request.get_data(as_text=True)[:200])
        resp = fn(*args, **kwargs)
        logger.info("RESPONSE %s %s | status=%s", request.method, request.path, resp.status_code)
        return resp
    return wrapper


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Render uses this to verify the service is up."""
    return omilia_response({"status": "ok", "service": "ameritas-chatbot-api", "timestamp": datetime.utcnow().isoformat()})


# ---------------------------------------------------------------------------
# 1. AUTHENTICATION
# POST /auth
# Body: { "policy_number": "LI-2847391", "dob": "1975-04-12", "ssn_last4": "4821" }
# ---------------------------------------------------------------------------

@app.route("/auth", methods=["POST"])
@log_request
def authenticate():
    """
    Authenticate a caller by policy number only.
    Returns policyholder name on success.

    Omilia usage:
      - Call this at the start of every session
      - Store returned `policy_number` in a session variable for all subsequent calls
    """
    body = request.get_json(silent=True) or {}
    policy_number = (body.get("policy_number") or "").strip().upper()

    if not policy_number:
        return error_response("policy_number is required.", "MISSING_FIELDS")

    record = sheets.get_policy_info(policy_number)
    if not record:
        return error_response("Policy not found. Please check your policy number and try again.", "POLICY_NOT_FOUND")

    return omilia_response({
        "status": "authenticated",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "message": f"Welcome, {record['policyholder_name']}. Authentication successful.",
    })


# ---------------------------------------------------------------------------
# 2. POLICY INFORMATION
# GET /policy/<policy_number>/info
# ---------------------------------------------------------------------------

@app.route("/policy/<policy_number>/info", methods=["GET"])
@log_request
def policy_info(policy_number: str):
    """
    Return full policy details for the authenticated caller.

    Returns: status, policy_type, effective_date, coverage_amount,
             death_benefit, premium_amount, premium_frequency, cash_value,
             riders, beneficiaries
    """
    policy_number = policy_number.strip().upper()
    record = sheets.get_policy_info(policy_number)
    if not record:
        return error_response("Policy not found.", "POLICY_NOT_FOUND")

    return omilia_response({
        "status": "success",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "policy_type": record["policy_type"],
        "policy_status": record["status"],
        "effective_date": record["effective_date"],
        "coverage_amount": record["coverage_amount"],
        "death_benefit": record["death_benefit"],
        "premium_amount": record["premium_amount"],
        "premium_frequency": record["premium_frequency"],
        "cash_value": record["cash_value"],
        "riders": record["riders"],
        "primary_beneficiary_1": record["primary_beneficiary_1"],
        "primary_beneficiary_1_pct": record["pb1_pct"],
        "primary_beneficiary_2": record["primary_beneficiary_2"],
        "primary_beneficiary_2_pct": record["pb2_pct"],
        "contingent_beneficiary": record["contingent_beneficiary"],
        "contingent_beneficiary_pct": record["cb_pct"],
        "message": (
            f"Your {record['policy_type']} policy is currently {record['status']}. "
            f"It has been in effect since {record['effective_date']} with a death benefit of {record['death_benefit']} "
            f"and a monthly premium of {record['premium_amount']}."
        ),
    })


# ---------------------------------------------------------------------------
# 3. LOAN / CASH VALUE
# GET /policy/<policy_number>/cash-value
# ---------------------------------------------------------------------------

@app.route("/policy/<policy_number>/cash-value", methods=["GET"])
@log_request
def cash_value(policy_number: str):
    """
    Return available cash value and loan details.

    Returns: current_cash_value, available_loan, existing_loan_balance,
             net_available_loan, loan_interest_rate, tax_implications
    """
    policy_number = policy_number.strip().upper()
    record = sheets.get_cash_value(policy_number)
    if not record:
        return error_response("Cash value record not found for this policy.", "NOT_FOUND")

    if record.get("available_loan") in (None, "N/A", ""):
        return omilia_response({
            "status": "not_applicable",
            "policy_number": policy_number,
            "message": "This policy type does not accumulate cash value. Policy loans are not available on term life policies.",
        })

    return omilia_response({
        "status": "success",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "policy_type": record["policy_type"],
        "current_cash_value": record["current_cash_value"],
        "available_loan": record["available_loan"],
        "existing_loan_balance": record["existing_loan_balance"],
        "net_available_loan": record["net_available_loan"],
        "loan_interest_rate": record["loan_interest_rate"],
        "death_benefit_impact": record["death_benefit_impact"],
        "tax_implications": record["tax_implications"],
        "message": (
            f"Your current cash value is {record['current_cash_value']}. "
            f"You may borrow up to {record['net_available_loan']} at {record['loan_interest_rate']}. "
            f"Any outstanding loan balance will reduce your death benefit."
        ),
    })


# ---------------------------------------------------------------------------
# 4. PREMIUM PAYMENTS / BILLING
# GET  /policy/<policy_number>/billing   — view billing status
# POST /policy/<policy_number>/payment   — submit a mock payment
# ---------------------------------------------------------------------------

@app.route("/policy/<policy_number>/billing", methods=["GET"])
@log_request
def billing(policy_number: str):
    """
    Return current billing and payment status for a policy.
    """
    policy_number = policy_number.strip().upper()
    record = sheets.get_billing(policy_number)
    if not record:
        return error_response("Billing record not found.", "NOT_FOUND")

    return omilia_response({
        "status": "success",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "premium_amount": record["premium_amount"],
        "due_date": record["due_date"],
        "last_payment_date": record["last_payment_date"],
        "last_payment_amount": record["last_payment_amount"],
        "payment_method": record["payment_method"],
        "account_last4": record["account_last4"],
        "autopay_enrolled": record["autopay_enrolled"],
        "grace_period_days": record["grace_period_days"],
        "grace_period_expiry": record["grace_period_expiry"],
        "outstanding_balance": record["outstanding_balance"],
        "lapse_warning": record["lapse_warning"],
        "message": _billing_message(record),
    })


@app.route("/policy/<policy_number>/payment", methods=["POST"])
@log_request
def make_payment(policy_number: str):
    """
    Process a MOCK premium payment (no real transaction occurs).
    Body: { "amount": "$287.50", "payment_method": "ACH" }  (both optional — defaults to premium due)

    DEMO NOTE: This endpoint simulates payment acceptance only.
    No funds are moved. For demo purposes a confirmation number is generated.
    """
    policy_number = policy_number.strip().upper()
    body = request.get_json(silent=True) or {}

    billing_record = sheets.get_billing(policy_number)
    if not billing_record:
        return error_response("Policy not found.", "POLICY_NOT_FOUND")

    amount = body.get("amount") or billing_record["premium_amount"]
    payment_method = body.get("payment_method") or billing_record["payment_method"]

    # Generate a mock confirmation number
    import hashlib, time
    confirmation = "AMT-" + hashlib.md5(f"{policy_number}{time.time()}".encode()).hexdigest()[:8].upper()

    return omilia_response({
        "status": "payment_accepted",
        "policy_number": policy_number,
        "policyholder_name": billing_record["policyholder_name"],
        "amount_paid": amount,
        "payment_method": payment_method,
        "confirmation_number": confirmation,
        "payment_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "message": (
            f"Your payment of {amount} has been accepted. "
            f"Confirmation number: {confirmation}. "
            f"Please allow 1 to 2 business days for your account to reflect this payment."
        ),
        "demo_note": "This is a simulated payment. No real transaction has occurred.",
    })


# ---------------------------------------------------------------------------
# 5. POLICY LAPSE & REINSTATEMENT
# GET  /policy/<policy_number>/reinstatement   — get lapse + reinstatement details
# POST /policy/<policy_number>/reinstatement   — initiate reinstatement (mock)
# ---------------------------------------------------------------------------

@app.route("/policy/<policy_number>/reinstatement", methods=["GET"])
@log_request
def reinstatement_info(policy_number: str):
    """
    Return lapse status and reinstatement eligibility details.
    """
    policy_number = policy_number.strip().upper()
    record = sheets.get_reinstatement(policy_number)
    if not record:
        return error_response("No lapse or reinstatement record found for this policy.", "NOT_FOUND")

    return omilia_response({
        "status": "success",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "lapse_date": record["lapse_date"],
        "reason_for_lapse": record["reason_for_lapse"],
        "months_lapsed": record["months_lapsed"],
        "back_premium_owed": record["back_premium_owed"],
        "interest_owed": record["interest_owed"],
        "total_reinstatement_amount": record["total_reinstatement_amount"],
        "reinstatement_window_expiry": record["reinstatement_window_expiry"],
        "health_requalification_required": record["health_requalification_required"],
        "reinstatement_status": record["reinstatement_status"],
        "apl_triggered": record["apl_triggered"],
        "notes": record["notes"],
        "message": _reinstatement_message(record),
    })


@app.route("/policy/<policy_number>/reinstatement", methods=["POST"])
@log_request
def initiate_reinstatement(policy_number: str):
    """
    Initiate a MOCK reinstatement request.
    Body: { "confirm": true }

    DEMO NOTE: This simulates reinstatement initiation only.
    """
    policy_number = policy_number.strip().upper()
    body = request.get_json(silent=True) or {}

    if not body.get("confirm"):
        return error_response("Set 'confirm': true to initiate reinstatement.", "CONFIRMATION_REQUIRED")

    record = sheets.get_reinstatement(policy_number)
    if not record:
        return error_response("No reinstatement record found.", "NOT_FOUND")

    if record["reinstatement_status"] in ("Denied", "Reinstated"):
        return omilia_response({
            "status": "not_eligible",
            "reinstatement_status": record["reinstatement_status"],
            "message": f"Reinstatement cannot be initiated. Current status: {record['reinstatement_status']}.",
        })

    import hashlib, time
    confirmation = "AMT-REIN-" + hashlib.md5(f"{policy_number}{time.time()}".encode()).hexdigest()[:6].upper()

    return omilia_response({
        "status": "reinstatement_initiated",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "total_due": record["total_reinstatement_amount"],
        "confirmation_number": confirmation,
        "next_steps": (
            "A reinstatement application has been opened. "
            f"Total amount due: {record['total_reinstatement_amount']}. "
            "You will receive written instructions within 3 to 5 business days."
        ),
        "message": (
            f"Your reinstatement request has been received. Confirmation: {confirmation}. "
            f"To complete reinstatement, a payment of {record['total_reinstatement_amount']} is required."
        ),
        "demo_note": "This is a simulated reinstatement. No real action has been taken.",
    })

 # ---------------------------------------------------------------------------
# 6. BENEFICIARY LOOKUP
# GET /policy/<policy_number>/beneficiaries
# ---------------------------------------------------------------------------

@app.route("/policy/<policy_number>/beneficiaries", methods=["GET"])
@log_request
def beneficiaries(policy_number: str):
    """
    Return all beneficiary information for a policy.

    Returns: primary_beneficiary_1, pb1_pct, primary_beneficiary_2,
             pb2_pct, contingent_beneficiary, cb_pct
    """
    policy_number = policy_number.strip().upper()
    record = sheets.get_policy_info(policy_number)
    if not record:
        return error_response("Policy not found.", "POLICY_NOT_FOUND")

    return omilia_response({
        "status": "success",
        "policy_number": policy_number,
        "policyholder_name": record["policyholder_name"],
        "primary_beneficiary_1": record["primary_beneficiary_1"],
        "primary_beneficiary_1_pct": record["pb1_pct"],
        "primary_beneficiary_2": record["primary_beneficiary_2"],
        "primary_beneficiary_2_pct": record["pb2_pct"],
        "contingent_beneficiary": record["contingent_beneficiary"],
        "contingent_beneficiary_pct": record["cb_pct"],
        "message": _beneficiary_message(record),
    })

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _billing_message(r: dict) -> str:
    if r.get("lapse_warning") == "Lapsed":
        return (
            f"Your policy has lapsed as of the last missed payment. "
            f"Outstanding balance: {r['outstanding_balance']}. "
            f"Please contact us to discuss reinstatement options."
        )
    if r.get("lapse_warning") == "Yes":
        return (
            f"Your premium of {r['premium_amount']} was due on {r['due_date']} and has not been received. "
            f"Your grace period expires {r['grace_period_expiry']}. "
            f"Please make a payment to avoid a lapse."
        )
    return (
        f"Your premium of {r['premium_amount']} is due on {r['due_date']}. "
        f"Your last payment of {r['last_payment_amount']} was received on {r['last_payment_date']}. "
        f"Your account is current."
    )


def _reinstatement_message(r: dict) -> str:
    status = r.get("reinstatement_status", "")
    if status == "Reinstated":
        return "Your policy has already been reinstated. No further action is required."
    if status == "Denied":
        return "Your reinstatement request was denied. Please contact an Ameritas representative for alternatives."
    if status == "In Review":
        return (
            "Your reinstatement application is currently under review. "
            "You will be notified once a decision has been made."
        )
    return (
        f"Your policy lapsed on {r.get('lapse_date')}. "
        f"You are eligible for reinstatement. "
        f"The total amount required to reinstate is {r.get('total_reinstatement_amount')}. "
        f"Your reinstatement window expires {r.get('reinstatement_window_expiry')}."
    )

def _beneficiary_message(r: dict) -> str:
    msg = "Your primary beneficiary is "
    if r.get("primary_beneficiary_2"):
        msg += f"{r['primary_beneficiary_1']} at {r['pb1_pct']} and {r['primary_beneficiary_2']} at {r['pb2_pct']}."
    else:
        msg += f"{r['primary_beneficiary_1']} at {r['pb1_pct']}."
    if r.get("contingent_beneficiary"):
        msg += f" Your contingent beneficiary is {r['contingent_beneficiary']} at {r['cb_pct']}."
    return msg
```

---

No changes needed to `sheets.py` at all — `get_policy_info` already pulls all the beneficiary fields from the sheet.

---

The full URL for Omilia will be:
```
GET https://ameritas-chatbot-api.onrender.com/policy/{policy_number}/beneficiaries

# ---------------------------------------------------------------------------
# Error handlers — always return JSON so Omilia can parse failures
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return error_response(f"Endpoint not found: {request.path}", "NOT_FOUND")


@app.errorhandler(405)
def method_not_allowed(e):
    return error_response(f"Method {request.method} not allowed on {request.path}", "METHOD_NOT_ALLOWED")


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled exception")
    return error_response("An internal error occurred. Please try again.", "INTERNAL_ERROR")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # debug=False is critical in production; Render sets PORT automatically
    app.run(host="0.0.0.0", port=port, debug=False)
