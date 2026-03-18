# Altum Realty CRM — Frontend

React + TypeScript sales CRM for land acquisition. Agents manage leads, call owners via Twilio, send SMS, and track pipeline.

**Repo**: `/Users/YOUR_USERNAME/land-sales-portal/`
**Stack**: React 19 + TypeScript + Vite + MUI + AWS Amplify + Twilio Voice SDK
**Dev**: `npm run dev`
**Build**: `npm run build` → `dist/`

---

## Architecture

```
Cognito Auth → React App → Lambda Functions → DynamoDB
                         → Twilio Voice SDK → Phone Calls
                         → SMS API → Text Messages
```

- **Auth**: AWS Cognito (email login, no signup — admin-only user creation)
- **API**: Lambda functions invoked via AWS SDK (`useCallLambdaFunction` hook)
- **Hosting**: AWS Amplify (App ID: `YOUR_AMPLIFY_APP_ID`)
- **State**: React Context (DialerContext) + component-level useState

---

## User Groups (Cognito)

| Group | Role | Access |
|-------|------|--------|
| **Archon** | Admin | Everything — agents, reports, voicemails |
| **Envoy** | Sales Manager | Leads, SMS, calling, dashboard |
| **Scout** | Sales Rep | Assigned leads, SMS, calling |

---

## Pages & Routes

| Route | Page | Access |
|-------|------|--------|
| `/dashboard` | Pipeline overview, daily/agent stats | All |
| `/search` | Search leads by owner_id, status, phone | All |
| `/assigned-leads` | Leads assigned to current user | All |
| `/owner/:ownerId` | Owner profile — properties, calls, notes | All |
| `/lot/:county/:accountId` | Property details, map, comps | All |
| `/sms` | SMS conversation threads | All |
| `/call/:ownerId[/:phoneNumber]` | Twilio call interface | All |
| `/voicemails` | Voicemail management | Archon |
| `/agents` | User CRUD, password reset | Archon |
| `/reports` | Generate/download reports | Archon |

---

## Lambda Functions

All invoked via `useCallLambdaFunction` hook. ARN base in `.env` as `VITE_LAMBDA_FUNCTION_BASE_ARN`.

| Function | Purpose |
|----------|---------|
| `getPropertyDetails` | Lot data by account_id + county |
| `getOwnerDetails` | Owner profile by owner_id |
| `editPropertyDetails` | Update lot fields |
| `editOwnerDetails` | Update owner fields |
| `getTwilioToken` | Twilio access token for calls |
| `submitAfterCallSummary` | Log after-call work |
| `getVoicemails` | List voicemails |
| `getVoicemailDetails` | Single voicemail |
| `deleteVoicemail` | Remove voicemail |
| `getCallDetails` | Call recording/transcript |
| `connectAgentToLead` | Bridge agent to lead call |
| `generateReport` | CSV/PDF reports |
| `getNextProspect` | Next lead for dialing |
| `searchLeads` | Search by status/criteria |
| `phoneNumberLookup` | Reverse phone lookup |
| `pipelineOverview` | Dashboard pipeline stats |

---

## Owner Statuses

```
NEW → COLD → CONTACT MADE → WARM → FOLLOW UP → OFFER MADE → UNDER CONTRACT → IN DISPO → CLOSED
                                                                                         → DEAD
                                                                              → FAILED SKIPTRACE
```

Status colors defined in `src/components/shared/StyledComponents.tsx`.

---

## Key Data Types

**Owner**: owner_id, name, address, phone, email, status, assignee, properties[], call_logs[], notes[], phones[], relatives[], associates[], bankruptcy, owner_flags, totals

**Lot (Property)**: account_id, county, address, acreage, lat/long, land_value, estimated_value, tax_data, zoning, comps_within_X_miles, property_flags, improvement_data

**Comparable**: mls_id, address, county, acres, close_price, closed_date, listing_price, days_on_market, zoning, lat/long

Types defined in `src/types/owner.types.ts`, `user.types.ts`, `sms.types.ts`, `phoneLookup.types.ts`.

---

## Calling Flow (Twilio)

1. Agent clicks "Call" on owner profile → opens Dialer panel
2. `useTwilioCall` fetches token via `getTwilioToken` Lambda
3. Twilio Device connects → call initiated
4. Contact list built: primary phone → alt phones → relatives → associates
5. Agent can: redial, dial next contact, transfer to manager, drop voicemail
6. On hangup → After-Call Work form (outcome, notes, duration)
7. ACW submitted via `submitAfterCallSummary` Lambda
8. `DialerContext.closeDialer(completed: true)` notifies OwnerDetailsPage to refetch

---

## Dialer Context

Global state for the collapsible dialer sidebar (72px collapsed, 400px expanded).

```typescript
openDialer(ownerId, { phoneNumber?, autoDial? })
closeDialer({ ownerId?, completed? })
setPanelOpen(open)
```

Persists across page navigation. Call completion triggers owner data refetch via postMessage + localStorage.

---

## Key Directories

```
src/
├── pages/           # 12 page components
├── hooks/           # 38 custom hooks (data fetching, mutations, Twilio)
├── components/
│   ├── owner/       # Owner profile components
│   ├── lot/         # Property + comparables components
│   ├── twilio/      # Call UI, wrap-up, bridge
│   ├── dialer/      # Dialer shell + content
│   ├── layout/      # Navbar, Layout
│   └── shared/      # StyledComponents, MapComponent, LoadingState
├── context/         # DialerContext
├── types/           # TypeScript interfaces
└── utils/           # Phone formatting
```

---

## Dev Notes

- Lambda responses are double-wrapped: `{ statusCode, body: "{...}" }` — `useCallLambdaFunction` parses both layers
- Editable owner fields: zip, exemptions, address, name, state, city, veteran, disabled, assignee, over_65, phone, email, status
- Google Maps API key in `.env` for map components
- Path alias: `~/*` → `./src/*` (in tsconfig + vite config)
- Cognito User Pool: `YOUR_COGNITO_USER_POOL_ID`, Client: `YOUR_COGNITO_CLIENT_ID`
