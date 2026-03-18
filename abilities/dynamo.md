# DynamoDB

Read and write to DynamoDB tables via the `Table` class.

## Location

Source: `/Users/YOUR_USERNAME/land-bot/modules/Dynamo.py`
AWS session: `/Users/YOUR_USERNAME/land-bot/modules/AWS.py` (uses credentials from `modules/Config.py`)

## Setup

Requires AWS credentials configured in `land-bot/modules/Config.py` (`AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `AWS_REGION`).

```python
# PYTHONPATH must include land-bot root
import sys
sys.path.insert(0, "/Users/YOUR_USERNAME/land-bot")

from modules.Dynamo import Table
```

## Table Class API

### Read

| Method | Description |
|--------|-------------|
| `table.get(key)` | Get one item by primary key. Returns dict or `{}` |
| `table.get_all()` | Scan entire table (paginated). Returns list of dicts |
| `table.getCount()` | Return item count (scan) |
| `table.filter(attribute, value, eq=True)` | Scan with single attribute filter. `eq=False` for not-equal |
| `table.filterMultiple(filters)` | Scan with up to 5 `DynamoFilter` conditions (AND) |
| `table.query_index(index_name, key_name, key_value)` | Query a GSI by partition key. Paginates automatically |
| `table.query_index_composite(index_name, hash_key_name, hash_key_value, range_key_name, range_key_value)` | Query GSI with composite key (hash + range) |
| `table.scan_projection(projection_expression, expression_attribute_names)` | Scan returning only specified attributes |

### Write

| Method | Description |
|--------|-------------|
| `table.write(data)` | Put one item. Accepts dict or dataclass |
| `table.put_if_not_exists(data, key_attr)` | Put only if key doesn't exist. Returns `True`/`False` |
| `table.batch_write_items(items)` | Put many items in batches of 25 |
| `table.updateItem(key, updateExpression, expressionAttributeValues)` | Update one item with UpdateExpression |

### Delete

| Method | Description |
|--------|-------------|
| `table.delete(key)` | Delete one item by key |
| `table.batch_delete_items(keys)` | Delete many items by key in batches of 25 |
| `table.clear_all_items()` | Delete every item in the table |

## DynamoFilter

```python
from modules.Models import DynamoFilter

filters = [
    DynamoFilter(attribute="status", value="NEW", eq=True),
    DynamoFilter(attribute="assignee", value="none", eq=False),
]
results = table.filterMultiple(filters)
```

## Examples

```python
from modules.Dynamo import Table

# Get a single owner
owners = Table("Owners")
owner = owners.get({"owner_id": "abc123"})

# Query by GSI
cold_leads = owners.query_index("StatusIndex", "status", "COLD")
assigned = owners.query_index("AssigneeIndex", "assignee", "user-123")
by_phone = owners.query_index("PhoneIndex", "phone", "+1XXXXXXXXXX")

# Write an item
owners.write({"owner_id": "new-1", "name": "John Doe", "status": "NEW"})

# Update a field
owners.updateItem(
    {"owner_id": "abc123"},
    "SET #s = :val",
    {":val": "CONTACTED", "#s": "status"}  # note: use ExpressionAttributeNames for reserved words
)

# Scan with projection (only get specific fields)
owners.scan_projection("#s, #o", {"#s": "status", "#o": "owner_id"})
```

## Notes

- All Decimal values are auto-converted to int/float on reads
- All float values are auto-converted to Decimal on writes
- Scans paginate automatically — no manual pagination needed
- `updateItem` requires DynamoDB UpdateExpression syntax
