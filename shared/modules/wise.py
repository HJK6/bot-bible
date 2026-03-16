"""
Wise (TransferWise) Payments API Client

Wraps the Wise API for sending money internationally. Supports the full
transfer flow: profiles, quotes, recipients, transfers, and funding.

API key is stored in AWS SSM Parameter Store at /altum/wise/api-key.

API Docs: https://docs.wise.com/api-docs/api-reference
"""

from __future__ import annotations

import os
import uuid
import logging
from typing import Dict, List, Optional, Any

import boto3
import requests

logger = logging.getLogger(__name__)

# AWS credentials (same as tracker.py)
AWS_ACCESS_KEY = os.environ.get("TRACKER_AWS_ACCESS_KEY", "YOUR_AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("TRACKER_AWS_SECRET_KEY", "YOUR_AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("TRACKER_AWS_REGION", "us-east-1")

SANDBOX_URL = "https://api.sandbox.transferwise.tech"
PRODUCTION_URL = "https://api.transferwise.com"


def _get_api_key_from_ssm():
    """Fetch the Wise API key from AWS SSM Parameter Store."""
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )
    ssm = session.client("ssm")
    resp = ssm.get_parameter(Name="/altum/wise/api-key", WithDecryption=True)
    return resp["Parameter"]["Value"]


class WiseError(Exception):
    """Raised when a Wise API call fails."""
    def __init__(self, message, status_code=None, raw_response=None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class Wise:
    """
    Wise API client.

    Usage:
        from modules.wise import Wise

        w = Wise()                      # production, key from SSM
        w = Wise(sandbox=True)          # sandbox mode
        w = Wise(api_key="xxx")         # explicit key

        profiles = w.get_profiles()
        quote = w.create_quote(profile_id, "USD", "INR", source_amount=500)
        recipient = w.create_recipient(profile_id, "INR", "ifsc", "John Doe", {...})
        transfer = w.create_transfer(recipient["id"], quote["id"], "invoice payment")
        w.fund_transfer(profile_id, transfer["id"])
    """

    def __init__(self, api_key=None, sandbox=False):
        self.api_key = api_key or os.environ.get("WISE_API_KEY") or _get_api_key_from_ssm()
        self.base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        self._profile_id = None

    def _request(self, method, path, json=None, params=None):
        url = f"{self.base_url}{path}"
        logger.debug("%s %s", method, url)
        try:
            resp = self.session.request(method, url, json=json, params=params, timeout=30)
        except requests.RequestException as e:
            raise WiseError(f"HTTP request failed: {e}")

        if resp.status_code >= 400:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            raise WiseError(
                f"API error {resp.status_code}: {error_body}",
                status_code=resp.status_code,
                raw_response=error_body,
            )

        if resp.status_code == 204:
            return {}
        return resp.json()

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, json=None):
        return self._request("POST", path, json=json)

    def _put(self, path, json=None):
        return self._request("PUT", path, json=json)

    # ── Profiles ─────────────────────────────────────────────────

    def get_profiles(self):
        """List all profiles (personal + business) for the authenticated user."""
        return self._get("/v1/profiles")

    def get_profile(self, profile_id):
        """Get a single profile by ID."""
        return self._get(f"/v1/profiles/{profile_id}")

    @property
    def profile_id(self):
        """Auto-detect and cache the personal profile ID."""
        if self._profile_id is None:
            profiles = self.get_profiles()
            for p in profiles:
                if p.get("type") == "personal":
                    self._profile_id = p["id"]
                    break
            if self._profile_id is None and profiles:
                self._profile_id = profiles[0]["id"]
            if self._profile_id is None:
                raise WiseError("No profiles found for this API key")
        return self._profile_id

    # ── Quotes ───────────────────────────────────────────────────

    def create_quote(self, profile_id, source_currency, target_currency,
                     source_amount=None, target_amount=None):
        """
        Create a quote. Locks the exchange rate for 30 minutes.

        Specify either source_amount OR target_amount, not both.
        """
        if source_amount and target_amount:
            raise WiseError("Specify source_amount or target_amount, not both")

        payload = {
            "sourceCurrency": source_currency,
            "targetCurrency": target_currency,
            "sourceAmount": source_amount,
            "targetAmount": target_amount,
        }
        # v3 endpoint
        result = self._post(f"/v3/profiles/{profile_id}/quotes", json=payload)
        logger.info(
            "Quote created: %s %s -> %s %s (rate: %s, fee: %s)",
            result.get("sourceAmount"), source_currency,
            result.get("targetAmount"), target_currency,
            result.get("rate"), result.get("fee"),
        )
        return result

    def get_quote(self, profile_id, quote_id):
        """Get an existing quote by ID."""
        return self._get(f"/v3/profiles/{profile_id}/quotes/{quote_id}")

    # ── Recipients ───────────────────────────────────────────────

    def get_account_requirements(self, source_currency, target_currency, source_amount=10):
        """
        Discover valid recipient types and required fields for a currency route.

        Returns list of dicts, each with 'type' and 'fields' describing the
        required details for that recipient type.
        """
        return self._get("/v1/account-requirements", params={
            "source": source_currency,
            "target": target_currency,
            "sourceAmount": source_amount,
        })

    def create_recipient(self, profile_id, currency, account_type,
                         account_holder_name, details, owned_by_customer=False):
        """
        Create a recipient account.

        Args:
            profile_id: Sender's profile ID
            currency: 3-letter currency code (USD, INR, GBP, EUR, etc.)
            account_type: Type string — use get_account_requirements() to discover.
                Common types: aba (USD), indian (INR), sort_code (GBP),
                iban (EUR), indian_upi (INR UPI), email, swift_code
            account_holder_name: Full name of recipient
            details: Dict of type-specific fields. Common fields by type:
                aba (USD): routingNumber, accountNumber, accountType, address
                indian (INR): ifscCode, accountNumber, address
                indian_upi (INR): accountNumber (UPI ID), address
                sort_code (GBP): sortCode, accountNumber
                iban (EUR): iban
                email: email
            owned_by_customer: True if recipient is the sender themselves
        """
        payload = {
            "currency": currency,
            "type": account_type,
            "profile": profile_id,
            "accountHolderName": account_holder_name,
            "ownedByCustomer": owned_by_customer,
            "details": details,
        }
        result = self._post("/v1/accounts", json=payload)
        logger.info("Recipient created: %s (%s/%s) id=%s",
                     account_holder_name, currency, account_type, result.get("id"))
        return result

    def list_recipients(self, profile_id=None, currency=None):
        """List recipient accounts, optionally filtered by profile and/or currency."""
        params = {}
        if profile_id:
            params["profile"] = profile_id
        if currency:
            params["currency"] = currency
        return self._get("/v1/accounts", params=params)

    def get_recipient(self, account_id):
        """Get a single recipient account by ID."""
        return self._get(f"/v1/accounts/{account_id}")

    def delete_recipient(self, account_id):
        """Delete a recipient account."""
        return self._request("DELETE", f"/v1/accounts/{account_id}")

    # ── Transfers ────────────────────────────────────────────────

    def create_transfer(self, target_account_id, quote_id, reference=None,
                        transfer_purpose=None, source_of_funds=None):
        """
        Create a transfer (payment order). Must be funded within 14 days.

        One transfer per quote — cannot reuse a quote ID.
        """
        details = {}
        if reference:
            details["reference"] = reference
        if transfer_purpose:
            details["transferPurpose"] = transfer_purpose
        if source_of_funds:
            details["sourceOfFunds"] = source_of_funds

        payload = {
            "targetAccount": target_account_id,
            "quoteUuid": quote_id,
            "customerTransactionId": str(uuid.uuid4()),
            "details": details,
        }
        result = self._post("/v1/transfers", json=payload)
        logger.info("Transfer created: id=%s, %s %s -> %s %s, status=%s",
                     result.get("id"),
                     result.get("sourceValue"), result.get("sourceCurrency"),
                     result.get("targetValue"), result.get("targetCurrency"),
                     result.get("status"))
        return result

    def get_transfer(self, transfer_id):
        """Get transfer details by ID."""
        return self._get(f"/v1/transfers/{transfer_id}")

    def list_transfers(self, profile_id=None, status=None, limit=100, offset=0):
        """List transfers with optional filters."""
        params = {"limit": limit, "offset": offset}
        if profile_id:
            params["profile"] = profile_id
        if status:
            params["status"] = status
        return self._get("/v1/transfers", params=params)

    def cancel_transfer(self, transfer_id):
        """Cancel an unfunded transfer. This is irreversible."""
        return self._put(f"/v1/transfers/{transfer_id}/cancel")

    # ── Funding ──────────────────────────────────────────────────

    def fund_transfer(self, profile_id, transfer_id):
        """
        Fund a transfer from the Wise balance. This starts processing.

        Returns dict with 'type', 'status' (COMPLETED/REJECTED), and
        optionally 'errorCode' on failure.
        """
        result = self._post(
            f"/v3/profiles/{profile_id}/transfers/{transfer_id}/payments",
            json={"type": "BALANCE"},
        )
        logger.info("Fund transfer %s: status=%s", transfer_id, result.get("status"))
        return result

    # ── Status & Info ────────────────────────────────────────────

    def get_delivery_estimate(self, transfer_id):
        """Get estimated delivery time for a transfer."""
        return self._get(f"/v1/delivery-estimates/{transfer_id}")

    def get_transfer_issues(self, transfer_id):
        """Get any active issues blocking a transfer."""
        return self._get(f"/v1/transfers/{transfer_id}/issues")

    def get_balance(self, profile_id):
        """Get all currency balances for a profile."""
        return self._get(f"/v4/profiles/{profile_id}/balances?types=STANDARD")

    def get_exchange_rate(self, source, target):
        """Get the current mid-market exchange rate."""
        rates = self._get("/v1/rates", params={"source": source, "target": target})
        if rates:
            return rates[0]
        return {}

    # ── Convenience ──────────────────────────────────────────────

    def send_money(self, source_currency, target_currency, recipient_name,
                   recipient_details, recipient_type, amount, amount_is_source=True,
                   reference=None, fund=False):
        """
        High-level: create quote -> create recipient -> create transfer -> optionally fund.

        Args:
            source_currency: e.g. "USD"
            target_currency: e.g. "INR"
            recipient_name: Full name of recipient
            recipient_details: Dict of type-specific fields (routingNumber, ifscCode, etc.)
            recipient_type: e.g. "aba", "ifsc", "iban", "email"
            amount: Amount to send
            amount_is_source: If True, amount is in source currency. If False, target currency.
            reference: Payment reference/memo
            fund: If True, fund from balance immediately

        Returns:
            Dict with 'quote', 'recipient', 'transfer', and optionally 'funding' keys.
        """
        pid = self.profile_id

        # Step 1: Quote
        quote = self.create_quote(
            pid, source_currency, target_currency,
            source_amount=amount if amount_is_source else None,
            target_amount=amount if not amount_is_source else None,
        )

        # Step 2: Recipient
        recipient = self.create_recipient(
            pid, target_currency, recipient_type,
            recipient_name, recipient_details,
        )

        # Step 3: Transfer
        quote_id = quote.get("id") or quote.get("uuid")
        transfer = self.create_transfer(
            recipient["id"], quote_id,
            reference=reference,
        )

        result = {
            "quote": quote,
            "recipient": recipient,
            "transfer": transfer,
        }

        # Step 4: Fund (optional)
        if fund:
            funding = self.fund_transfer(pid, transfer["id"])
            result["funding"] = funding

        return result


# ── Module-level convenience functions ──────────────────────────

_client = None


def _get_client(sandbox=False):
    global _client
    if _client is None:
        _client = Wise(sandbox=sandbox)
    return _client


def get_profiles():
    return _get_client().get_profiles()


def get_balance(profile_id=None):
    c = _get_client()
    pid = profile_id or c.profile_id
    return c.get_balance(pid)


def get_exchange_rate(source, target):
    return _get_client().get_exchange_rate(source, target)


def list_recipients(profile_id=None, currency=None):
    c = _get_client()
    pid = profile_id or c.profile_id
    return c.list_recipients(pid, currency)


def list_transfers(profile_id=None, status=None, limit=100):
    c = _get_client()
    pid = profile_id or c.profile_id
    return c.list_transfers(pid, status=status, limit=limit)


def send_money(source_currency, target_currency, recipient_name,
               recipient_details, recipient_type, amount,
               amount_is_source=True, reference=None, fund=False):
    return _get_client().send_money(
        source_currency, target_currency, recipient_name,
        recipient_details, recipient_type, amount,
        amount_is_source=amount_is_source, reference=reference, fund=fund,
    )


# ── CLI test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as _json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("=== Wise API Test ===\n")

    try:
        w = Wise()
        profiles = w.get_profiles()
        print(f"Profiles ({len(profiles)}):")
        for p in profiles:
            print(f"  {p.get('type')}: id={p['id']} - {p.get('details', {}).get('firstName', '')} {p.get('details', {}).get('lastName', '')}")

        pid = w.profile_id
        print(f"\nUsing profile: {pid}")

        balances = w.get_balance(pid)
        print(f"\nBalances:")
        print(_json.dumps(balances, indent=2, default=str))

        rate = w.get_exchange_rate("USD", "INR")
        print(f"\nUSD->INR rate: {rate}")

    except WiseError as e:
        print(f"Error: {e}")
        raise SystemExit(1)

    print("\n=== Done ===")
