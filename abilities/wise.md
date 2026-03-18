# Wise Payments

Send international money transfers via the Wise (TransferWise) API.

## Location

Source: `/Users/YOUR_USERNAME/telegram-claude-bot/modules/wise.py`
API Key: AWS SSM `/altum/wise/api-key` (SecureString)

## Setup

```python
import sys
sys.path.insert(0, "/Users/YOUR_USERNAME/telegram-claude-bot")

from modules.wise import Wise, send_money, get_balance, get_exchange_rate
```

No extra pip install needed — uses `requests` and `boto3` (already in global venv).

## Quick Usage

```python
from modules.wise import Wise

w = Wise()

# Check profiles & balances
profiles = w.get_profiles()
balance = w.get_balance(w.profile_id)
rate = w.get_exchange_rate("USD", "INR")

# Full transfer in one call
result = w.send_money(
    source_currency="USD",
    target_currency="INR",
    recipient_name="John Doe",
    recipient_type="indian",
    recipient_details={
        "legalType": "PRIVATE",
        "ifscCode": "SBIN0001234",
        "accountNumber": "12345678901",
        "address": {"country": "IN", "city": "Mumbai", "firstLine": "123 Main St", "postCode": "400001"},
    },
    amount=500,            # USD 500
    reference="Invoice 42",
    fund=True,             # fund from Wise balance immediately
)
```

## Step-by-Step API

### 1. Get Profiles

```python
profiles = w.get_profiles()
# Returns list: [{"id": 123, "type": "personal", "details": {...}}, ...]
pid = w.profile_id  # auto-detects personal profile
```

### 2. Create Quote (locks rate for 30 min)

```python
quote = w.create_quote(pid, "USD", "INR", source_amount=500)
# OR specify target amount:
quote = w.create_quote(pid, "USD", "INR", target_amount=40000)
```

### 3. Create Recipient

```python
# USD (ACH)
recipient = w.create_recipient(pid, "USD", "aba", "Jane Smith", {
    "legalType": "PRIVATE",
    "routingNumber": "026009593",
    "accountNumber": "1234567890",
    "accountType": "CHECKING",
    "address": {"country": "US", "state": "TX", "city": "Dallas", "firstLine": "123 Main St", "postCode": "75001"},
})

# INR (Bank transfer)
recipient = w.create_recipient(pid, "INR", "indian", "Raj Kumar", {
    "legalType": "PRIVATE",
    "ifscCode": "SBIN0001234",
    "accountNumber": "12345678901",
    "address": {"country": "IN", "city": "Mumbai", "firstLine": "123 Main St", "postCode": "400001"},
})

# INR (UPI)
recipient = w.create_recipient(pid, "INR", "indian_upi", "Raj Kumar", {
    "legalType": "PRIVATE",
    "accountNumber": "raj@upi",
    "address": {"country": "IN", "city": "Mumbai", "firstLine": "123 Main St", "postCode": "400001"},
})

# GBP (Sort Code)
recipient = w.create_recipient(pid, "GBP", "sort_code", "John Smith", {
    "legalType": "PRIVATE",
    "sortCode": "040075",
    "accountNumber": "37778842",
})

# EUR (IBAN)
recipient = w.create_recipient(pid, "EUR", "iban", "Hans Mueller", {
    "legalType": "PRIVATE",
    "iban": "DE89370400440532013000",
})

# Email (Wise collects bank details from recipient)
recipient = w.create_recipient(pid, "USD", "email", "Anyone", {
    "email": "someone@example.com",
})
```

### 4. Create Transfer

```python
transfer = w.create_transfer(
    target_account_id=recipient["id"],
    quote_id=quote["id"],  # or quote["uuid"]
    reference="Invoice payment",
)
```

### 5. Fund Transfer (from Wise balance)

```python
funding = w.fund_transfer(pid, transfer["id"])
# Returns: {"type": "BALANCE", "status": "COMPLETED"} or "REJECTED"
```

## Other Operations

```python
# Check balances
balances = w.get_balance(pid)

# Exchange rates
rate = w.get_exchange_rate("USD", "INR")

# List recipients
recipients = w.list_recipients(pid, currency="INR")

# List transfers
transfers = w.list_transfers(pid, status="funds_converted", limit=10)

# Transfer status & issues
status = w.get_transfer(transfer_id)
issues = w.get_transfer_issues(transfer_id)
estimate = w.get_delivery_estimate(transfer_id)

# Cancel unfunded transfer (irreversible)
w.cancel_transfer(transfer_id)
```

## Recipient Types by Currency

| Currency | Type | Required Details |
|----------|------|-----------------|
| USD | `aba` | routingNumber, accountNumber, accountType, address |
| USD | `fedwire_local` | routingNumber, accountNumber, accountType, address |
| INR | `indian` | ifscCode, accountNumber, address (country, city, firstLine, postCode) |
| INR | `indian_upi` | accountNumber (UPI ID), address |
| GBP | `sort_code` | sortCode, accountNumber |
| EUR | `iban` | iban |
| Any | `swift_code` | swiftCode, accountNumber |
| Any | `email` | email (Wise collects bank info from recipient) |

Use `w.get_account_requirements("USD", "INR")` to discover valid types & fields for any route.

All detail objects should include `legalType`: `"PRIVATE"` or `"BUSINESS"`.

## API Details

- **Auth**: `Authorization: Bearer <token>`
- **Production**: `https://api.transferwise.com`
- **Sandbox**: `https://api.sandbox.transferwise.tech`
- **Rate lock**: Quotes lock the mid-market rate for 30 minutes
- **Transfer expiry**: Unfunded transfers auto-cancel after 14 days
- **One transfer per quote**: Cannot reuse a quote ID

## CLI Test

```bash
cd /Users/YOUR_USERNAME/telegram-claude-bot
python3 modules/wise.py
```

## Notes

- API key is stored in AWS SSM at `/altum/wise/api-key` (SecureString)
- Personal token has some limitations: cannot fund transfers in EU/UK due to PSD2
- For US-based transfers, personal token works fine
- The `send_money()` convenience method handles the full 4-step flow
- Always set `fund=True` only when you're sure — funding starts processing immediately
