"""
Porkbun DNS & Domain Management API Client

Wraps the Porkbun v3 API for domain management, DNS record CRUD,
pricing lookups, and availability checks.

All endpoints use POST with JSON body containing apikey and secretapikey.
Credentials are loaded from environment variables via dotenv.

API Docs: https://porkbun.com/api/json/v3/documentation
"""

from __future__ import annotations

import os
import logging
from typing import Dict, List, Optional, Any

import requests
from dotenv import load_dotenv

# Load .env from telegram-claude-bot root
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.porkbun.com/api/json/v3"


class PorkbunError(Exception):
    """Raised when a Porkbun API call returns an error status."""
    def __init__(self, message, status=None, raw_response=None):
        super().__init__(message)
        self.status = status
        self.raw_response = raw_response


class Porkbun:
    """
    Porkbun v3 API client.

    Usage:
        from modules.porkbun import Porkbun

        pb = Porkbun()
        pb.ping()
        domains = pb.list_domains()
        records = pb.get_dns_records("example.com")
    """

    def __init__(self, api_key=None, secret_key=None):
        """
        Initialize with API credentials.

        Args:
            api_key: Porkbun API key. Falls back to PORKBUN_API_KEY env var.
            secret_key: Porkbun secret key. Falls back to PORKBUN_SECRET_KEY env var.
        """
        self.api_key = api_key or os.environ.get("PORKBUN_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("PORKBUN_SECRET_KEY", "")

        if not self.api_key or not self.secret_key:
            raise PorkbunError(
                "Missing Porkbun credentials. Set PORKBUN_API_KEY and PORKBUN_SECRET_KEY "
                "environment variables or pass them to the constructor."
            )

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _auth_body(self):
        # type: () -> Dict[str, str]
        """Return the base auth payload required by every endpoint."""
        return {
            "apikey": self.api_key,
            "secretapikey": self.secret_key,
        }

    def _post(self, endpoint, extra_data=None):
        # type: (str, Optional[Dict[str, Any]]) -> Dict[str, Any]
        """
        Make an authenticated POST request to the Porkbun API.

        Args:
            endpoint: API path after /api/json/v3/ (e.g. "ping", "dns/create/example.com")
            extra_data: Additional JSON fields to merge with auth body.

        Returns:
            Parsed JSON response dict.

        Raises:
            PorkbunError: If the API returns a non-SUCCESS status.
        """
        url = "{}/{}".format(BASE_URL, endpoint.lstrip("/"))
        payload = self._auth_body()
        if extra_data:
            payload.update(extra_data)

        logger.debug("POST %s", url)

        try:
            resp = self.session.post(url, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise PorkbunError("HTTP request failed: {}".format(e))

        data = resp.json()

        if data.get("status") != "SUCCESS":
            msg = data.get("message", "Unknown error")
            raise PorkbunError(
                "API error: {}".format(msg),
                status=data.get("status"),
                raw_response=data,
            )

        return data

    # ── Connectivity ────────────────────────────────────────────

    def ping(self):
        # type: () -> Dict[str, Any]
        """
        Test API connectivity and verify credentials.

        Returns:
            Dict with 'status' and 'yourIp' fields.
        """
        data = self._post("ping")
        logger.info("Porkbun ping OK — your IP: %s", data.get("yourIp"))
        return data

    # ── Domains ─────────────────────────────────────────────────

    def list_domains(self, start=0, include_labels=False):
        # type: (int, bool) -> List[Dict[str, Any]]
        """
        List all domains on the account.

        Args:
            start: Pagination offset (default 0). Results come in batches of 1000.
            include_labels: Include domain labels in response.

        Returns:
            List of domain dicts with keys like 'domain', 'status', 'tld',
            'createDate', 'expireDate', 'securityLock', etc.
        """
        extra = {}  # type: Dict[str, Any]
        if start > 0:
            extra["start"] = str(start)
        if include_labels:
            extra["includeLabels"] = "yes"

        data = self._post("domain/listAll", extra if extra else None)
        domains = data.get("domains", [])
        logger.info("Listed %d domain(s)", len(domains))
        return domains

    def check_domain_availability(self, domain):
        # type: (str) -> Dict[str, Any]
        """
        Check if a domain is available for registration.

        Args:
            domain: Full domain name (e.g. "example.com").

        Returns:
            Dict with availability info: 'avail', 'pricing', etc.
            Note: Porkbun rate-limits this endpoint.
        """
        data = self._post("domain/checkDomain/{}".format(domain))
        return data

    def get_domain_pricing(self):
        # type: () -> Dict[str, Any]
        """
        Get pricing for all TLDs (registration, renewal, transfer).

        Returns:
            Dict keyed by TLD with pricing details. Auth is NOT required
            for this endpoint, but we include it anyway for consistency.
        """
        data = self._post("pricing/get")
        pricing = data.get("pricing", {})
        logger.info("Retrieved pricing for %d TLD(s)", len(pricing))
        return pricing

    # ── DNS Records ─────────────────────────────────────────────

    def get_dns_records(self, domain, record_id=None):
        # type: (str, Optional[str]) -> List[Dict[str, Any]]
        """
        Get DNS records for a domain.

        Args:
            domain: The domain name (e.g. "example.com").
            record_id: Optional specific record ID to retrieve.

        Returns:
            List of record dicts with keys: 'id', 'name', 'type',
            'content', 'ttl', 'prio', 'notes'.
        """
        endpoint = "dns/retrieve/{}".format(domain)
        if record_id:
            endpoint = "dns/retrieve/{}/{}".format(domain, record_id)

        data = self._post(endpoint)
        records = data.get("records", [])
        logger.info("Retrieved %d DNS record(s) for %s", len(records), domain)
        return records

    def create_dns_record(self, domain, record_type, name, content, ttl=600, prio=None):
        # type: (str, str, str, str, int, Optional[int]) -> Dict[str, Any]
        """
        Create a DNS record.

        Args:
            domain: The domain name (e.g. "example.com").
            record_type: Record type (A, AAAA, CNAME, MX, TXT, NS, SRV, etc.).
            name: Subdomain or '' for root. Do NOT include the domain itself
                  (e.g. for "www.example.com", pass "www").
            content: Record value (IP address, hostname, text, etc.).
            ttl: Time to live in seconds (default 600).
            prio: Priority (required for MX and SRV records).

        Returns:
            Dict with 'status' and 'id' of the created record.
        """
        extra = {
            "type": record_type.upper(),
            "name": name,
            "content": content,
            "ttl": str(ttl),
        }  # type: Dict[str, Any]
        if prio is not None:
            extra["prio"] = str(prio)

        data = self._post("dns/create/{}".format(domain), extra)
        record_id = data.get("id")
        logger.info(
            "Created %s record for %s.%s -> %s (id=%s)",
            record_type, name or "@", domain, content, record_id,
        )
        return data

    def update_dns_record(self, domain, record_id, record_type, name, content, ttl=600, prio=None):
        # type: (str, str, str, str, str, int, Optional[int]) -> Dict[str, Any]
        """
        Update an existing DNS record by ID.

        Args:
            domain: The domain name.
            record_id: The record ID to update.
            record_type: New record type.
            name: New subdomain (or '' for root).
            content: New record value.
            ttl: New TTL in seconds (default 600).
            prio: New priority (for MX/SRV).

        Returns:
            Dict with 'status'.
        """
        extra = {
            "type": record_type.upper(),
            "name": name,
            "content": content,
            "ttl": str(ttl),
        }  # type: Dict[str, Any]
        if prio is not None:
            extra["prio"] = str(prio)

        data = self._post("dns/edit/{}/{}".format(domain, record_id), extra)
        logger.info(
            "Updated record %s on %s: %s %s -> %s",
            record_id, domain, record_type, name or "@", content,
        )
        return data

    def delete_dns_record(self, domain, record_id):
        # type: (str, str) -> Dict[str, Any]
        """
        Delete a DNS record by ID.

        Args:
            domain: The domain name.
            record_id: The record ID to delete.

        Returns:
            Dict with 'status'.
        """
        data = self._post("dns/delete/{}/{}".format(domain, record_id))
        logger.info("Deleted record %s from %s", record_id, domain)
        return data

    # ── Convenience ─────────────────────────────────────────────

    def get_records_by_type(self, domain, record_type):
        # type: (str, str) -> List[Dict[str, Any]]
        """Get DNS records filtered by type (A, CNAME, MX, TXT, etc.)."""
        all_records = self.get_dns_records(domain)
        return [r for r in all_records if r.get("type", "").upper() == record_type.upper()]

    def get_nameservers(self, domain):
        # type: (str) -> List[str]
        """Get the NS records for a domain as a list of nameserver hostnames."""
        ns_records = self.get_records_by_type(domain, "NS")
        return [r.get("content", "") for r in ns_records]

    def set_a_record(self, domain, subdomain, ip_address, ttl=600):
        # type: (str, str, str, int) -> Dict[str, Any]
        """
        Convenience: create or replace an A record for a subdomain.

        If an A record already exists for that subdomain, it is deleted first.
        """
        existing = self.get_records_by_type(domain, "A")
        full_name = "{}.{}".format(subdomain, domain) if subdomain else domain
        for rec in existing:
            if rec.get("name") == full_name:
                self.delete_dns_record(domain, rec["id"])
                logger.info("Deleted existing A record %s for %s", rec["id"], full_name)

        return self.create_dns_record(domain, "A", subdomain, ip_address, ttl=ttl)

    def set_cname_record(self, domain, subdomain, target, ttl=600):
        # type: (str, str, str, int) -> Dict[str, Any]
        """
        Convenience: create or replace a CNAME record for a subdomain.

        If a CNAME record already exists for that subdomain, it is deleted first.
        """
        existing = self.get_records_by_type(domain, "CNAME")
        full_name = "{}.{}".format(subdomain, domain) if subdomain else domain
        for rec in existing:
            if rec.get("name") == full_name:
                self.delete_dns_record(domain, rec["id"])
                logger.info("Deleted existing CNAME record %s for %s", rec["id"], full_name)

        return self.create_dns_record(domain, "CNAME", subdomain, target, ttl=ttl)


# ── Module-level convenience functions ──────────────────────────

_client = None  # type: Optional[Porkbun]


def _get_client():
    # type: () -> Porkbun
    """Get or create the module-level singleton client."""
    global _client
    if _client is None:
        _client = Porkbun()
    return _client


def ping():
    # type: () -> Dict[str, Any]
    """Test API connectivity."""
    return _get_client().ping()


def list_domains(start=0):
    # type: (int) -> List[Dict[str, Any]]
    """List all domains on the account."""
    return _get_client().list_domains(start=start)


def get_dns_records(domain, record_id=None):
    # type: (str, Optional[str]) -> List[Dict[str, Any]]
    """Get DNS records for a domain."""
    return _get_client().get_dns_records(domain, record_id)


def create_dns_record(domain, record_type, name, content, ttl=600, prio=None):
    # type: (str, str, str, str, int, Optional[int]) -> Dict[str, Any]
    """Create a DNS record."""
    return _get_client().create_dns_record(domain, record_type, name, content, ttl, prio)


def update_dns_record(domain, record_id, record_type, name, content, ttl=600, prio=None):
    # type: (str, str, str, str, str, int, Optional[int]) -> Dict[str, Any]
    """Update a DNS record by ID."""
    return _get_client().update_dns_record(domain, record_id, record_type, name, content, ttl, prio)


def delete_dns_record(domain, record_id):
    # type: (str, str) -> Dict[str, Any]
    """Delete a DNS record by ID."""
    return _get_client().delete_dns_record(domain, record_id)


def get_domain_pricing():
    # type: () -> Dict[str, Any]
    """Get pricing for all TLDs."""
    return _get_client().get_domain_pricing()


def check_domain_availability(domain):
    # type: (str) -> Dict[str, Any]
    """Check if a domain is available for registration."""
    return _get_client().check_domain_availability(domain)


# ── CLI test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as _json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("=== Porkbun API Test ===\n")

    try:
        result = ping()
        print("Ping: {}".format(_json.dumps(result, indent=2)))
    except PorkbunError as e:
        print("Ping failed: {}".format(e))
        raise SystemExit(1)

    print()

    try:
        domains = list_domains()
        print("Domains ({} total):".format(len(domains)))
        for d in domains:
            print("  {} (expires: {}, status: {})".format(
                d.get("domain", "?"),
                d.get("expireDate", "?"),
                d.get("status", "?"),
            ))
    except PorkbunError as e:
        print("List domains failed: {}".format(e))

    print("\n=== Done ===")
