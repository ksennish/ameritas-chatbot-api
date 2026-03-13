"""
sheets.py — Google Sheets data access layer
--------------------------------------------
Reads live data from the Ameritas demo Google Sheet.

Sheet ID: 1jLlqZ8rOsD5kkGwm0nkRQji0q6mfAyN2

Tab mapping:
  - "Policy Status & Coverage"    → get_policy_info / get_auth_record
  - "Premium Payment & Billing"   → get_billing
  - "Policy Lapse & Reinstatement"→ get_reinstatement
  - "Cash Value Loan & Withdrawal"→ get_cash_value

Authentication:
  Set GOOGLE_CREDENTIALS_JSON env var to the contents of your service account
  key file (the full JSON string, not a path).

  Alternatively, set GOOGLE_CREDENTIALS_PATH to a file path.

  If neither is set, the module falls back to MOCK_DATA (useful for local dev
  and Render preview deploys before credentials are wired up).
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1jLlqZ8rOsD5kkGwm0nkRQji0q6mfAyN2"

# ---------------------------------------------------------------------------
# Mock authentication data
# (DOB and SSN are not in the sheet — stored here for demo purposes only)
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Google Sheets client (lazy-loaded)
# ---------------------------------------------------------------------------

_gc = None  # gspread client singleton


def _get_client():
    """Return a gspread client, or None if credentials are unavailable."""
    global _gc
    if _gc is not None:
        return _gc

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")

        if creds_json:
            info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        elif creds_path:
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        else:
            logger.warning("No Google credentials found — using mock data fallback.")
            return None

        _gc = gspread.authorize(creds)
        logger.info("Google Sheets client initialised successfully.")
        return _gc

    except Exception as exc:
        logger.error("Failed to initialise Google Sheets client: %s", exc)
        return None


def _get_sheet_records(tab_name: str) -> list:
    """
    Fetch all rows from a named tab as a list of dicts.
    Falls back to an empty list on any error.
    """
    gc = _get_client()
    if gc is None:
        return []
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(tab_name)
        return ws.get_all_records()
    except Exception as exc:
        logger.error("Sheets read error (tab=%s): %s", tab_name, exc)
        return []


# ---------------------------------------------------------------------------
# Public data-access functions
# ---------------------------------------------------------------------------



def get_policy_info(policy_number: str) -> Optional[dict]:
    """Return policy status & coverage row for given policy_number."""
    rows = _get_sheet_records("Policy Status & Coverage")
    if not rows:
        rows = _MOCK_POLICY_INFO

    for row in rows:
        if str(row.get("Policy Number", "")).strip().upper() == policy_number:
            return {
                "policy_number": row.get("Policy Number"),
                "policyholder_name": row.get("Policyholder Name"),
                "policy_type": row.get("Policy Type"),
                "status": row.get("Status"),
                "effective_date": _fmt_date(row.get("Effective Date")),
                "coverage_amount": row.get("Coverage Amount"),
                "death_benefit": row.get("Death Benefit"),
                "premium_amount": row.get("Premium Amount"),
                "premium_frequency": row.get("Premium Frequency"),
                "cash_value": row.get("Cash Value"),
                "riders": row.get("Riders"),
                "primary_beneficiary_1": row.get("Primary Beneficiary 1"),
                "pb1_pct": row.get("PB1 %"),
                "primary_beneficiary_2": row.get("Primary Beneficiary 2"),
                "pb2_pct": row.get("PB2 %"),
                "contingent_beneficiary": row.get("Contingent Beneficiary"),
                "cb_pct": row.get("CB %"),
            }
    return None


def get_billing(policy_number: str) -> Optional[dict]:
    """Return premium payment & billing row for given policy_number."""
    rows = _get_sheet_records("Premium Payment & Billing")
    if not rows:
        rows = _MOCK_BILLING

    for row in rows:
        if str(row.get("Policy Number", "")).strip().upper() == policy_number:
            return {
                "policy_number": row.get("Policy Number"),
                "policyholder_name": row.get("Policyholder Name"),
                "premium_amount": row.get("Premium Amount"),
                "due_date": _fmt_date(row.get("Due Date")),
                "last_payment_date": _fmt_date(row.get("Last Payment Date")),
                "last_payment_amount": row.get("Last Payment Amount"),
                "payment_method": row.get("Payment Method"),
                "account_last4": row.get("Account Last 4"),
                "autopay_enrolled": row.get("Autopay Enrolled"),
                "grace_period_days": row.get("Grace Period (Days)"),
                "grace_period_expiry": _fmt_date(row.get("Grace Period Expiry")),
                "outstanding_balance": row.get("Outstanding Balance"),
                "lapse_warning": row.get("Lapse Warning"),
                "consecutive_payments": row.get("Consecutive On-Time Payments"),
                "payment_notes": row.get("Payment History Notes"),
            }
    return None


def get_reinstatement(policy_number: str) -> Optional[dict]:
    """Return lapse & reinstatement row for given policy_number."""
    rows = _get_sheet_records("Policy Lapse & Reinstatement")
    if not rows:
        rows = _MOCK_REINSTATEMENT

    for row in rows:
        if str(row.get("Policy Number", "")).strip().upper() == policy_number:
            return {
                "policy_number": row.get("Policy Number"),
                "policyholder_name": row.get("Policyholder Name"),
                "lapse_date": _fmt_date(row.get("Lapse Date")),
                "reason_for_lapse": row.get("Reason for Lapse"),
                "months_lapsed": row.get("Months Lapsed"),
                "back_premium_owed": row.get("Back-Premium Owed"),
                "interest_rate": row.get("Interest Rate"),
                "interest_owed": row.get("Interest Owed"),
                "total_reinstatement_amount": row.get("Total Reinstatement Amount"),
                "reinstatement_window_expiry": _fmt_date(row.get("Reinstatement Window Expiry")),
                "health_requalification_required": row.get("Health Re-Qualification Required"),
                "reinstatement_status": row.get("Reinstatement Status"),
                "apl_triggered": row.get("APL Triggered"),
                "notes": row.get("Notes"),
            }
    return None


def get_cash_value(policy_number: str) -> Optional[dict]:
    """
    Return the most relevant cash value / loan record for a policy.
    If multiple rows exist (e.g. multiple withdrawals), returns the latest.
    """
    rows = _get_sheet_records("Cash Value Loan & Withdrawal")
    if not rows:
        rows = _MOCK_CASH_VALUE

    matches = [
        r for r in rows
        if str(r.get("Policy Number", "")).strip().upper() == policy_number
    ]
    if not matches:
        return None

    # Return last entry (most recent transaction or most up-to-date balance)
    row = matches[-1]
    return {
        "policy_number": row.get("Policy Number"),
        "policyholder_name": row.get("Policyholder Name"),
        "policy_type": row.get("Policy Type"),
        "current_cash_value": row.get("Current Cash Value"),
        "cost_basis": row.get("Cost Basis"),
        "available_loan": row.get("Available Loan (90%)"),
        "existing_loan_balance": row.get("Existing Loan Balance"),
        "net_available_loan": row.get("Net Available Loan"),
        "loan_interest_rate": row.get("Loan Interest Rate"),
        "death_benefit_impact": row.get("Death Benefit Impact"),
        "tax_implications": row.get("Tax Implications"),
        "transaction_status": row.get("Transaction Status"),
    }


# ---------------------------------------------------------------------------
# Date formatter
# ---------------------------------------------------------------------------

def _fmt_date(val) -> str:
    """Return date as string, handling both datetime objects and raw strings."""
    if val is None:
        return ""
    from datetime import datetime, date
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    return str(val).strip()


# ---------------------------------------------------------------------------
# Mock data — used when Google credentials are not configured
# Mirrors the exact structure returned by gspread get_all_records()
# ---------------------------------------------------------------------------

_MOCK_POLICY_INFO = [
    {"Policy Number": "LI-2847391", "Policyholder Name": "James Mitchell", "Policy Type": "Whole Life", "Status": "Active", "Effective Date": "3/25/2018", "Coverage Amount": "$500,000", "Death Benefit": "$500,000", "Premium Amount": "$287.50", "Premium Frequency": "Monthly", "Cash Value": "$24,350.00", "Cost Basis": "$20,700.00", "Riders": "Waiver of Premium; Accidental Death ($250K)", "Primary Beneficiary 1": "Sarah Mitchell", "PB1 %": "70%", "Primary Beneficiary 2": "Tyler Mitchell", "PB2 %": "30%", "Contingent Beneficiary": "Robert Mitchell", "CB %": "100%"},
    {"Policy Number": "LI-3019284", "Policyholder Name": "Patricia Nguyen", "Policy Type": "Term Life (20-Year)", "Status": "Active", "Effective Date": "6/1/2015", "Coverage Amount": "$750,000", "Death Benefit": "$750,000", "Premium Amount": "$134.00", "Premium Frequency": "Monthly", "Cash Value": "N/A", "Cost Basis": "N/A", "Riders": "Accidental Death ($100K)", "Primary Beneficiary 1": "David Nguyen", "PB1 %": "100%", "Primary Beneficiary 2": "", "PB2 %": "", "Contingent Beneficiary": "Linda Tran", "CB %": "100%"},
    {"Policy Number": "LI-4401857", "Policyholder Name": "Marcus Williams", "Policy Type": "Universal Life", "Status": "Active", "Effective Date": "9/22/2020", "Coverage Amount": "$1,000,000", "Death Benefit": "$1,000,000", "Premium Amount": "$412.00", "Premium Frequency": "Monthly", "Cash Value": "$11,820.00", "Cost Basis": "$9,840.00", "Riders": "Waiver of Premium; Child Term Rider", "Primary Beneficiary 1": "Angela Williams", "PB1 %": "60%", "Primary Beneficiary 2": "Derek Williams", "PB2 %": "40%", "Contingent Beneficiary": "Carol Williams", "CB %": "100%"},
    {"Policy Number": "LI-2201934", "Policyholder Name": "Sandra Torres", "Policy Type": "Whole Life", "Status": "Active", "Effective Date": "1/10/2012", "Coverage Amount": "$250,000", "Death Benefit": "$250,000", "Premium Amount": "$188.25", "Premium Frequency": "Monthly", "Cash Value": "$41,200.00", "Cost Basis": "$33,000.00", "Riders": "Waiver of Premium", "Primary Beneficiary 1": "Luis Torres", "PB1 %": "50%", "Primary Beneficiary 2": "Maria Torres", "PB2 %": "50%", "Contingent Beneficiary": "Elena Ruiz", "CB %": "100%"},
    {"Policy Number": "LI-5590123", "Policyholder Name": "Brian Chen", "Policy Type": "Term Life (10-Year)", "Status": "Active", "Effective Date": "11/3/2022", "Coverage Amount": "$300,000", "Death Benefit": "$300,000", "Premium Amount": "$78.50", "Premium Frequency": "Monthly", "Cash Value": "N/A", "Cost Basis": "N/A", "Riders": "None", "Primary Beneficiary 1": "Jennifer Chen", "PB1 %": "100%", "Primary Beneficiary 2": "", "PB2 %": "", "Contingent Beneficiary": "Thomas Chen", "CB %": "100%"},
    {"Policy Number": "LI-3384920", "Policyholder Name": "Olivia Grant", "Policy Type": "Whole Life", "Status": "Lapsed", "Effective Date": "8/14/2016", "Coverage Amount": "$400,000", "Death Benefit": "$400,000", "Premium Amount": "$231.00", "Premium Frequency": "Monthly", "Cash Value": "$18,900.00", "Cost Basis": "$16,500.00", "Riders": "Accidental Death ($200K)", "Primary Beneficiary 1": "Marcus Grant", "PB1 %": "100%", "Primary Beneficiary 2": "", "PB2 %": "", "Contingent Beneficiary": "Grace Grant", "CB %": "100%"},
    {"Policy Number": "LI-6670045", "Policyholder Name": "Kevin Park", "Policy Type": "Indexed Universal Life", "Status": "Active", "Effective Date": "4/5/2019", "Coverage Amount": "$600,000", "Death Benefit": "$600,000", "Premium Amount": "$350.00", "Premium Frequency": "Monthly", "Cash Value": "$15,640.00", "Cost Basis": "$13,200.00", "Riders": "Waiver of Premium", "Primary Beneficiary 1": "Yuna Park", "PB1 %": "70%", "Primary Beneficiary 2": "James Park", "PB2 %": "30%", "Contingent Beneficiary": "Hannah Park", "CB %": "100%"},
]

_MOCK_BILLING = [
    {"Policy Number": "LI-2847391", "Policyholder Name": "James Mitchell", "Premium Amount": "$287.50", "Due Date": "3/25/2026", "Last Payment Date": "2/25/2026", "Last Payment Amount": "$287.50", "Payment Method": "ACH – Checking", "Account Last 4": "4821", "Autopay Enrolled": "Yes", "Grace Period (Days)": "31", "Grace Period Expiry": "4/15/2026", "Outstanding Balance": "$0.00", "Lapse Warning": "No", "Consecutive On-Time Payments": "94", "Payment History Notes": "All payments current"},
    {"Policy Number": "LI-3019284", "Policyholder Name": "Patricia Nguyen", "Premium Amount": "$134.00", "Due Date": "3/1/2026", "Last Payment Date": "2/1/2026", "Last Payment Amount": "$134.00", "Payment Method": "Credit Card – Visa", "Account Last 4": "7743", "Autopay Enrolled": "Yes", "Grace Period (Days)": "31", "Grace Period Expiry": "4/1/2026", "Outstanding Balance": "$0.00", "Lapse Warning": "No", "Consecutive On-Time Payments": "129", "Payment History Notes": "All payments current"},
    {"Policy Number": "LI-4401857", "Policyholder Name": "Marcus Williams", "Premium Amount": "$412.00", "Due Date": "3/22/2026", "Last Payment Date": "2/22/2026", "Last Payment Amount": "$412.00", "Payment Method": "ACH – Savings", "Account Last 4": "3302", "Autopay Enrolled": "No", "Grace Period (Days)": "31", "Grace Period Expiry": "4/22/2026", "Outstanding Balance": "$0.00", "Lapse Warning": "No", "Consecutive On-Time Payments": "66", "Payment History Notes": "Autopay canceled Feb 2025; manual since"},
    {"Policy Number": "LI-2201934", "Policyholder Name": "Sandra Torres", "Premium Amount": "$188.25", "Due Date": "3/10/2026", "Last Payment Date": "1/10/2026", "Last Payment Amount": "$188.25", "Payment Method": "Check", "Account Last 4": "N/A", "Autopay Enrolled": "No", "Grace Period (Days)": "31", "Grace Period Expiry": "4/10/2026", "Outstanding Balance": "$188.25", "Lapse Warning": "Yes", "Consecutive On-Time Payments": "167", "Payment History Notes": "Missed Feb 2026 payment; in grace period"},
    {"Policy Number": "LI-5590123", "Policyholder Name": "Brian Chen", "Premium Amount": "$78.50", "Due Date": "3/3/2026", "Last Payment Date": "2/3/2026", "Last Payment Amount": "$78.50", "Payment Method": "ACH – Checking", "Account Last 4": "9910", "Autopay Enrolled": "Yes", "Grace Period (Days)": "31", "Grace Period Expiry": "4/3/2026", "Outstanding Balance": "$0.00", "Lapse Warning": "No", "Consecutive On-Time Payments": "28", "Payment History Notes": "All payments current"},
    {"Policy Number": "LI-3384920", "Policyholder Name": "Olivia Grant", "Premium Amount": "$231.00", "Due Date": "N/A", "Last Payment Date": "10/14/2025", "Last Payment Amount": "$231.00", "Payment Method": "ACH – Checking", "Account Last 4": "6621", "Autopay Enrolled": "N/A", "Grace Period (Days)": "31", "Grace Period Expiry": "N/A", "Outstanding Balance": "$693.00", "Lapse Warning": "Lapsed", "Consecutive On-Time Payments": "0", "Payment History Notes": "Lapsed 11/14/2025; 3 missed payments; eligible for reinstatement"},
    {"Policy Number": "LI-6670045", "Policyholder Name": "Kevin Park", "Premium Amount": "$350.00", "Due Date": "3/5/2026", "Last Payment Date": "2/5/2026", "Last Payment Amount": "$350.00", "Payment Method": "ACH – Checking", "Account Last 4": "2284", "Autopay Enrolled": "Yes", "Grace Period (Days)": "31", "Grace Period Expiry": "4/5/2026", "Outstanding Balance": "$0.00", "Lapse Warning": "No", "Consecutive On-Time Payments": "81", "Payment History Notes": "All payments current"},
]

_MOCK_REINSTATEMENT = [
    {"Policy Number": "LI-3384920", "Policyholder Name": "Olivia Grant", "Lapse Date": "11/14/2025", "Reason for Lapse": "Missed Payments", "Past-Due Premiums": "3", "Months Lapsed": "4", "Back-Premium Owed": "$693.00", "Interest Rate": "6%", "Interest Owed": "$13.86", "Total Reinstatement Amount": "$706.86", "Reinstatement Window Expiry": "11/14/2028", "Health Re-Qualification Required": "No (lapsed < 6 months)", "Reinstatement Application Submitted": "No", "Cash Value at Lapse": "$18,900.00", "APL Triggered": "No (APL not elected)", "Reinstatement Status": "Eligible – Pending", "Notes": "Customer contacted 3/1/2026; wants to reinstate"},
    {"Policy Number": "LI-7723001", "Policyholder Name": "Harold Simmons", "Lapse Date": "5/20/2024", "Reason for Lapse": "Non-Payment", "Past-Due Premiums": "6", "Months Lapsed": "10", "Back-Premium Owed": "$1,152.00", "Interest Rate": "6%", "Interest Owed": "$57.60", "Total Reinstatement Amount": "$1,209.60", "Reinstatement Window Expiry": "5/20/2027", "Health Re-Qualification Required": "Yes (lapsed 6–24 months)", "Reinstatement Application Submitted": "Yes", "Cash Value at Lapse": "$9,300.00", "APL Triggered": "No", "Reinstatement Status": "In Review", "Notes": "Health statement submitted; awaiting underwriting decision"},
    {"Policy Number": "LI-8812450", "Policyholder Name": "Denise Fowler", "Lapse Date": "1/3/2025", "Reason for Lapse": "Missed Payments", "Past-Due Premiums": "2", "Months Lapsed": "14", "Back-Premium Owed": "$564.50", "Interest Rate": "6%", "Interest Owed": "$39.52", "Total Reinstatement Amount": "$604.02", "Reinstatement Window Expiry": "1/3/2028", "Health Re-Qualification Required": "No (lapsed < 6 months)", "Reinstatement Application Submitted": "Yes", "Cash Value at Lapse": "$5,600.00", "APL Triggered": "No", "Reinstatement Status": "Reinstated", "Notes": "Reinstated 3/5/2025; conf. AMT-55003412"},
    {"Policy Number": "LI-9934201", "Policyholder Name": "Raymond Blake", "Lapse Date": "9/1/2023", "Reason for Lapse": "Non-Payment", "Past-Due Premiums": "4", "Months Lapsed": "30", "Back-Premium Owed": "$1,848.00", "Interest Rate": "6%", "Interest Owed": "$277.20", "Total Reinstatement Amount": "$2,125.20", "Reinstatement Window Expiry": "9/1/2026", "Health Re-Qualification Required": "Yes (lapsed > 24 months)", "Reinstatement Application Submitted": "No", "Cash Value at Lapse": "$12,400.00", "APL Triggered": "No", "Reinstatement Status": "Denied", "Notes": "Failed medical underwriting; too high-risk"},
    {"Policy Number": "LI-2847391", "Policyholder Name": "James Mitchell", "Lapse Date": "N/A – At Risk", "Reason for Lapse": "Payment due 3/25/2026", "Past-Due Premiums": "0 (Grace Period)", "Months Lapsed": "0", "Back-Premium Owed": "$0.00", "Interest Rate": "6%", "Interest Owed": "$0.00", "Total Reinstatement Amount": "$287.50 (current premium)", "Reinstatement Window Expiry": "4/15/2026", "Health Re-Qualification Required": "N/A", "Reinstatement Application Submitted": "N/A", "Cash Value at Lapse": "$24,350.00", "APL Triggered": "Yes – APL Available", "Reinstatement Status": "Pre-Lapse Warning", "Notes": "APL would cover premium automatically if missed"},
]

_MOCK_CASH_VALUE = [
    {"Policy Number": "LI-2847391", "Policyholder Name": "James Mitchell", "Policy Type": "Whole Life", "Current Cash Value": "$24,350.00", "Cost Basis": "$20,700.00", "Available Loan (90%)": "$21,915.00", "Existing Loan Balance": "$0.00", "Net Available Loan": "$21,915.00", "Loan Interest Rate": "5.5% annually", "Death Benefit Impact": "Reduced by loan balance", "Requested Action": "Loan Request", "Request Amount": "$10,000.00", "Tax Implications": "None – loan not taxable", "Estimated Tax Owed": "$0.00", "Confirmation Number": "AMT-48291037", "Transaction Status": "Approved", "Notes": "Death benefit reduced to $490,000 while loan outstanding"},
    {"Policy Number": "LI-4401857", "Policyholder Name": "Marcus Williams", "Policy Type": "Universal Life", "Current Cash Value": "$11,820.00", "Cost Basis": "$9,840.00", "Available Loan (90%)": "$10,638.00", "Existing Loan Balance": "$2,500.00", "Net Available Loan": "$8,138.00", "Loan Interest Rate": "5.5% annually", "Death Benefit Impact": "Reduced by loan balance", "Requested Action": "Loan Request", "Request Amount": "$5,000.00", "Tax Implications": "None – loan not taxable", "Estimated Tax Owed": "$0.00", "Confirmation Number": "AMT-72938401", "Transaction Status": "Approved", "Notes": "Existing loan of $2,500 already outstanding; new total $7,500"},
    {"Policy Number": "LI-2201934", "Policyholder Name": "Sandra Torres", "Policy Type": "Whole Life", "Current Cash Value": "$41,200.00", "Cost Basis": "$33,000.00", "Available Loan (90%)": "$37,080.00", "Existing Loan Balance": "$0.00", "Net Available Loan": "$37,080.00", "Loan Interest Rate": "5.5% annually", "Death Benefit Impact": "Reduced by loan balance", "Requested Action": "Partial Withdrawal", "Request Amount": "$10,000.00", "Tax Implications": "$0 taxable (within cost basis)", "Estimated Tax Owed": "$0.00", "Confirmation Number": "AMT-66710293", "Transaction Status": "Approved", "Notes": "Withdrawal below cost basis; no tax event"},
    {"Policy Number": "LI-2201934", "Policyholder Name": "Sandra Torres", "Policy Type": "Whole Life", "Current Cash Value": "$31,200.00", "Cost Basis": "$33,000.00", "Available Loan (90%)": "$28,080.00", "Existing Loan Balance": "$0.00", "Net Available Loan": "$28,080.00", "Loan Interest Rate": "5.5% annually", "Death Benefit Impact": "Not applicable", "Requested Action": "Partial Withdrawal", "Request Amount": "$5,000.00", "Tax Implications": "$3,200 taxable (above cost basis)", "Estimated Tax Owed": "~$768 (24% bracket est.)", "Confirmation Number": "AMT-66710294", "Transaction Status": "Approved – Tax Advisory Sent", "Notes": "Second withdrawal exceeds cost basis; taxable gain generated"},
    {"Policy Number": "LI-6670045", "Policyholder Name": "Kevin Park", "Policy Type": "IUL", "Current Cash Value": "$15,640.00", "Cost Basis": "$13,200.00", "Available Loan (90%)": "$14,076.00", "Existing Loan Balance": "$0.00", "Net Available Loan": "$14,076.00", "Loan Interest Rate": "5.5% annually", "Death Benefit Impact": "Reduced by loan balance", "Requested Action": "Loan Request", "Request Amount": "$8,000.00", "Tax Implications": "None – loan not taxable", "Estimated Tax Owed": "$0.00", "Confirmation Number": "AMT-39482011", "Transaction Status": "Approved", "Notes": "Customer confirmed death benefit reduction acknowledged"},
    {"Policy Number": "LI-7723001", "Policyholder Name": "Harold Simmons", "Policy Type": "Whole Life", "Current Cash Value": "$9,300.00", "Cost Basis": "$7,800.00", "Available Loan (90%)": "$8,370.00", "Existing Loan Balance": "$0.00", "Net Available Loan": "$8,370.00", "Loan Interest Rate": "5.5% annually", "Death Benefit Impact": "Reduced by loan balance", "Requested Action": "Full Surrender", "Request Amount": "$9,300.00", "Tax Implications": "$1,500 taxable (above cost basis)", "Estimated Tax Owed": "~$360 (24% bracket est.)", "Confirmation Number": "AMT-91234567", "Transaction Status": "Pending – Surrender Charge Applied", "Notes": "Surrender value after charge: $8,649; customer advised on tax implications"},
    {"Policy Number": "LI-5590123", "Policyholder Name": "Brian Chen", "Policy Type": "Term Life", "Current Cash Value": "N/A", "Cost Basis": "N/A", "Available Loan (90%)": "N/A", "Existing Loan Balance": "N/A", "Net Available Loan": "N/A", "Loan Interest Rate": "N/A", "Death Benefit Impact": "N/A", "Requested Action": "Loan Request", "Request Amount": "N/A", "Tax Implications": "N/A", "Estimated Tax Owed": "N/A", "Confirmation Number": "N/A", "Transaction Status": "Denied", "Notes": "Term life has no cash value accumulation; loan not available"},
]
