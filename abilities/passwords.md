# Passwords Ability — SSM-Backed Credential Manager

All credentials are stored in **AWS SSM Parameter Store** as `SecureString` parameters (encrypted with the default `aws/ssm` KMS key). A lookup index at `memory/credentials.md` maps friendly service names to SSM paths.

## SSM Path Convention

```
/bartimaeus/creds/{service_name}
```

- `service_name` is lowercase, hyphenated (e.g., `propstream`, `mls-matrix`, `gmail-smtp`)
- Value is always a **JSON blob**: `{"password": "...", "api_key": "...", ...}`
- Username/ID is stored in the **index file only** (not in SSM)

## CLI Helper — `~/bin/creds`

```bash
creds get <service>           # Print decrypted JSON blob
creds get <service> <key>     # Print a single field (e.g., creds get twilio auth_token)
creds set <service> <json>    # Create or overwrite (prompts for confirmation)
creds list                    # List all services from SSM
creds delete <service>        # Delete from SSM (prompts for confirmation)
```

## Python — Quick Access

```python
import boto3, json

ssm = boto3.client('ssm', region_name='us-east-1')

def get_creds(service: str) -> dict:
    """Get decrypted credentials for a service."""
    resp = ssm.get_parameter(
        Name=f'/bartimaeus/creds/{service}',
        WithDecryption=True
    )
    return json.loads(resp['Parameter']['Value'])

def get_cred(service: str, key: str) -> str:
    """Get a single credential field."""
    return get_creds(service)[key]

def set_creds(service: str, creds: dict):
    """Store credentials for a service (overwrites existing)."""
    ssm.put_parameter(
        Name=f'/bartimaeus/creds/{service}',
        Value=json.dumps(creds),
        Type='SecureString',
        Overwrite=True
    )
```

### Usage in scrapers / land-bot modules

```python
# Instead of hardcoded:
#   MLS_PASSWORD = "!Hann1bal!"
# Use:
MLS_PASSWORD = get_cred('mls-matrix', 'password')

# For Twilio (multiple fields):
twilio = get_creds('twilio')
TWILIO_AUTH_TOKEN = twilio['auth_token']
TWILIO_API_KEY = twilio['api_key']
```

### Lambda compatibility

In Lambda, SSM calls add ~50-100ms cold start. For latency-sensitive Lambdas, pass credentials as encrypted environment variables instead, or use SSM caching:

```python
import os, json

def get_creds_with_env_fallback(service: str, env_prefix: str = '') -> dict:
    """Check env vars first (for Lambda), fall back to SSM."""
    env_val = os.environ.get(f'{env_prefix}CREDS_JSON')
    if env_val:
        return json.loads(env_val)
    return get_creds(service)
```

## Index File

The credential index lives at `memory/credentials.md`. It maps service names to SSM paths and stores non-sensitive metadata (usernames, URLs, notes). **Never put passwords or secrets in the index file.**

## Adding a New Credential

1. Store in SSM: `creds set <service> '{"password": "..."}'`
2. Add a row to `memory/credentials.md` with the service name, SSM path, username, and notes
3. Update any source code that was using hardcoded values

## Security Notes

- SSM SecureString uses the default `aws/ssm` KMS key (free, managed by AWS)
- IAM policy on this machine's credentials allows `ssm:GetParameter`, `ssm:PutParameter`, `ssm:DeleteParameter` on `/bartimaeus/creds/*`
- Never log or print decrypted credential values
- The index file is safe to commit — it contains no secrets
