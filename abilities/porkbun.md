# Porkbun (Domain & DNS Management)

Manage domains and DNS records via the Porkbun API. Supports full DNS CRUD, domain listing, availability checks, and pricing lookups.

## Location

Source: `/Users/bartimaeus/telegram-claude-bot/modules/porkbun.py`

## Setup

Requires `PORKBUN_API_KEY` and `PORKBUN_SECRET_KEY` in the `.env` file (already configured).

```bash
pip install requests python-dotenv
```

## Usage

```python
from modules.porkbun import Porkbun

pb = Porkbun()

# Test connectivity
pb.ping()

# List all domains
domains = pb.list_domains()

# DNS records
records = pb.get_dns_records("example.com")
pb.create_dns_record("example.com", "A", "www", "1.2.3.4", ttl=600)
pb.update_dns_record("example.com", "123456", "A", "www", "5.6.7.8")
pb.delete_dns_record("example.com", "123456")

# Convenience: set A or CNAME (auto-replaces existing)
pb.set_a_record("example.com", "www", "1.2.3.4")
pb.set_cname_record("example.com", "blog", "myblog.example.com")

# Domain availability & pricing
pb.check_domain_availability("coolname.com")
pricing = pb.get_domain_pricing()
```

Module-level shortcut functions are also available:

```python
from modules.porkbun import ping, list_domains, get_dns_records, create_dns_record
```

## Capabilities

| Function | Description |
|----------|-------------|
| `ping()` | Test API connectivity, returns your public IP |
| `list_domains()` | List all domains on the Porkbun account |
| `get_dns_records(domain)` | Get all DNS records for a domain |
| `get_dns_records(domain, record_id)` | Get a specific DNS record by ID |
| `create_dns_record(domain, type, name, content, ttl, prio)` | Create a DNS record |
| `update_dns_record(domain, record_id, type, name, content, ttl, prio)` | Update a DNS record |
| `delete_dns_record(domain, record_id)` | Delete a DNS record |
| `get_domain_pricing()` | Get registration/renewal/transfer pricing for all TLDs |
| `check_domain_availability(domain)` | Check if a domain is available for registration |
| `get_records_by_type(domain, type)` | Filter records by type (A, CNAME, MX, TXT, etc.) |
| `get_nameservers(domain)` | Get NS records as a list of hostnames |
| `set_a_record(domain, subdomain, ip)` | Create/replace an A record |
| `set_cname_record(domain, subdomain, target)` | Create/replace a CNAME record |

## DNS Record Types

- **A** — IPv4 address
- **AAAA** — IPv6 address
- **CNAME** — Canonical name (alias)
- **MX** — Mail exchange (requires `prio`)
- **TXT** — Text record (SPF, DKIM, verification, etc.)
- **NS** — Nameserver
- **SRV** — Service record (requires `prio`)

## CLI Test

```bash
cd /Users/bartimaeus/telegram-claude-bot
python3 modules/porkbun.py
```

## Notes

- All Porkbun API endpoints use POST with JSON body
- The `name` field in DNS records is the subdomain only (e.g. "www"), not the full FQDN
- For root domain records, pass an empty string as `name`
- MX and SRV records require a `prio` (priority) parameter
- Domain availability checks are rate-limited by Porkbun
- Credentials are loaded from `.env` via dotenv, or can be passed to the constructor
