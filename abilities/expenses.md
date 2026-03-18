# Expenses

Manage business expenses for tax filing. Receipts stored in S3, metadata in DynamoDB, with OCR for amount extraction.

## Setup

```python
import sys
sys.path.insert(0, "/Users/YOUR_USERNAME/telegram-claude-bot")

from modules.expenses import ExpenseManager, EXPENSE_CATEGORIES

em = ExpenseManager()
```

## Infrastructure

| Resource | Type | Details |
|----------|------|---------|
| `Expenses` | DynamoDB Table | Key: `expense_id` (HASH). GSIs: `CategoryIndex` (category + date), `YearIndex` (year + date) |
| `YOUR_BOT_NAME-expense-receipts` | S3 Bucket | Receipt images stored as `receipts/{expense_id}.{ext}` |

## Expense Categories

From the MyTaxFiler Business Organizer template (Altum Group):

Accounting, Advertising, Auto Expense, Bank Charges, Compensation of Officers, Delivery, Dues and Subscription, Employee Benefit Programs, Gifts, Business Insurance, Interest Paid, Internet and Hosting, Laundry, Legal and Professional, License, Meals and Entertainment, Miscellaneous, Office Expense, Outside Services/Contract Labor, Parking and Tolls, Pension and Profit-sharing, Postage, Printing, Professional Development and Training, Rents, Repairs and Maintenance, Salary and Wages, Supplies, Taxes, Telephone, Travel, Utilities, Home Office, AWS Fees, Business Mileage, Other Expense

## Process a Receipt (OCR + Store)

```python
result = em.add_receipt("/path/to/receipt.jpg", category="Office Expense", description="USB hub")

# result = {
#   "expense_id": "a1b2c3d4",
#   "amount": 45.99,        # OCR-detected amount (or None)
#   "ocr_text": "...",       # raw OCR text
#   "s3_key": "receipts/a1b2c3d4.jpg",
#   "status": "pending_confirmation" or "needs_amount"
# }

# If amount detected -> confirm with user, then:
em.confirm_amount("a1b2c3d4", 45.99)

# If amount is None -> ask user for amount, then:
em.confirm_amount("a1b2c3d4", 52.00)
```

## Add Expense Manually (no receipt)

```python
em.add_expense(
    amount=45.99,
    category="Office Expense",
    description="USB hub",
    date="2025-03-07",            # optional, defaults to today
    receipt_path="/path/to/img",  # optional
)
```

## Update / Delete

```python
em.update_expense("a1b2c3d4", category="Supplies", amount=50.00)
em.delete_expense("a1b2c3d4")
```

## Query Expenses

```python
# By year
expenses = em.query(year="2025")

# By category
expenses = em.query(category="Travel")

# By both
expenses = em.query(year="2025", category="Travel")

# All
expenses = em.get_all()

# Single
expense = em.get_expense("a1b2c3d4")
```

## Summary by Category

```python
summary = em.summary("2025")
# {
#   "year": "2025",
#   "total": 12345.67,
#   "expense_count": 42,
#   "by_category": {
#     "Travel": {"total": 3000.00, "count": 5},
#     "Office Expense": {"total": 2000.00, "count": 8},
#     ...
#   }
# }
```

## Export CSV

```python
em.export_csv("/tmp/expenses_2025.csv", year="2025")
```

Output columns: Expense ID, Date, Category, Description, Amount, Status

## Export Tax Excel (MyTaxFiler Format)

Generates the Business Organizer format that GuruTaxPro expects, with:
- **Business Profile** sheet: P&L with all expense categories, income fields, totals
- **Per-category detail sheets**: Item, Date, Amount for each category with expenses
- **All Expenses** sheet: flat list of every expense

```python
em.export_tax_excel(
    "/tmp/Altum_2025_Business_Organizer.xlsx",
    year="2025",
    business_name="Altum Group",
    income_1099=26000,
    real_estate_commissions=6461.71,
)
```

## Receipt Workflow

1. User sends a receipt image (photo/scan)
2. Call `em.add_receipt(image_path, category=..., description=...)`
3. If `amount` is returned: send confirmation message "Receipt processed: $XX.XX for [category]. Correct?"
4. If `amount` is None (OCR failed): ask user "Could not read the amount. What was the total?"
5. Once user confirms/provides amount: call `em.confirm_amount(expense_id, amount)`
6. Expense is stored with status "confirmed"

## View Receipt

```python
url = em.get_receipt_url("a1b2c3d4", "receipts/a1b2c3d4.jpg")
# Returns presigned S3 URL valid for 1 hour
```

## Tax Filing Notes

- **Meals and Entertainment**: only 50% deductible (the Excel export handles this automatically)
- **Home Office**: computed separately (sq ft percentage of rent/mortgage + utilities)
- **Business Mileage**: IRS standard rate per mile (check current year rate)
- **AWS Fees**: monthly cloud hosting costs
- **Receipts over $75**: IRS requires original receipts kept 3-6 years (stored in S3)
- The accountant is at GuruTaxPro (YOUR_ACCOUNTANT_EMAIL, YOUR_ACCOUNTANT_EMAIL_2)
