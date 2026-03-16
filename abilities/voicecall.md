# Voice Call

Make outbound AI voice calls via Twilio with real-time speech recognition and conversational AI responses.

## Architecture

```
Outbound: Twilio REST API → call connects → Lambda webhook
Call flow: <Say> greeting → <Gather input="speech"> → Lambda → Bedrock AI → <Say> response → loop
Storage: DynamoDB (BartVoiceCalls) — conversation history per CallSid
AI: AWS Bedrock (Amazon Nova Lite) for fast conversational responses
```

## Location

| Component | Path |
|-----------|------|
| Voice Webhook (Lambda) | `/Users/bartimaeus/agent-dashboard/handlers/voice_webhook.py` |
| Call Script | `/Users/bartimaeus/agent-dashboard/voice_call.py` |
| CloudFormation (webhook + table) | `/Users/bartimaeus/agent-dashboard/templates/fragments/sqs.yaml` |
| DynamoDB Table Fragment | `/Users/bartimaeus/agent-dashboard/templates/fragments/tables.yaml` |
| IAM (Bedrock perms) | `/Users/bartimaeus/agent-dashboard/templates/fragments/iam.yaml` |

## Making a Call

```python
import sys
sys.path.insert(0, "/Users/bartimaeus/land-bot")
sys.path.insert(0, "/Users/bartimaeus/agent-dashboard")
from voice_call import make_call

# Call with default Bartimaeus number (+1XXXXXXXXXX)
make_call("+1XXXXXXXXXX")

# Call from the voice-only number
make_call("+1XXXXXXXXXX", from_number="+1XXXXXXXXXX")
```

### CLI

```bash
PYTHONPATH=/Users/bartimaeus/land-bot py /Users/bartimaeus/agent-dashboard/voice_call.py +1XXXXXXXXXX
PYTHONPATH=/Users/bartimaeus/land-bot py /Users/bartimaeus/agent-dashboard/voice_call.py +1XXXXXXXXXX --from +1XXXXXXXXXX
```

## DynamoDB Table

| Table | PK | Purpose |
|-------|------|---------|
| `BartVoiceCalls` | `call_sid` | Per-call conversation history (24h TTL) |

## Call Flow

1. `voice_call.py` calls Twilio REST API to initiate outbound call
2. Twilio connects and POSTs to `voiceWebhook` Lambda Function URL
3. Lambda returns TwiML: `<Say>` greeting + `<Gather input="speech">`
4. User speaks → Twilio transcribes → POSTs `SpeechResult` to Lambda
5. Lambda reads conversation history from DynamoDB, calls Bedrock (Nova Lite)
6. Lambda returns TwiML: `<Say>` AI response + `<Gather>` for next input
7. Loop continues until hangup or goodbye

## Config

- **Voice Webhook URL**: `YOUR_VOICE_WEBHOOK_URL`
- **Twilio numbers**: `+1XXXXXXXXXX` (SMS+voice), `+1XXXXXXXXXX` (voice only)
- **AI Model**: Amazon Nova Lite (`amazon.nova-lite-v1:0`) via Bedrock
- **TTS Voice**: `Polly.Matthew` (male US English)
- **Lambda timeout**: 60 seconds
- **Lambda memory**: 256 MB
- **Conversation TTL**: 24 hours in DynamoDB

## Deployment

Part of the `agent-dashboard` CloudFormation stack. Deploy with:

```bash
cd /Users/bartimaeus/agent-dashboard && make update_handlers
```

## Notes

- Phone numbers must be E.164 format: `+1` followed by 10 digits
- AI responses kept to 2-3 sentences for natural speech
- Call auto-ends if AI detects goodbye words in its response
- Two `<Gather>` retries if no speech detected before hanging up
- Conversation history persists for the duration of the call via DynamoDB
- `speechTimeout="auto"` — Twilio auto-detects when user stops speaking
