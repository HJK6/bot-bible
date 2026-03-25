# YOUR_BOT_NAME Mobile -- Build Process

## Quick Reference

| Command | What it does | Time |
|---------|-------------|------|
| `npm run typecheck` | TypeScript strict check (`tsc --noEmit`) | ~3s |
| `npm run validate` | TypeScript check + JS bundle export | ~10s |
| `npm run ios:release` | iOS Release build for simulator (embeds JS) | ~3min |
| `npm run ios:device` | iOS Release build for physical device (embeds JS) | ~3min |
| `npm run deploy:web` | Build + deploy to YOUR_DOMAIN | ~30s |

## Validation Checklist

**Before every commit or deploy**, run:
```bash
npm run validate
```

This catches:
- TypeScript errors (strict mode)
- Missing imports / broken references
- Metro bundler failures (bad JSX, circular deps)
- Asset resolution issues

## Build Targets

### Web (Production)
```bash
npm run deploy:web
# or manually:
npx expo export --platform web
aws s3 sync dist/ s3://agent-dashboard-frontend/ --delete
aws cloudfront create-invalidation --distribution-id YOUR_CF_DIST_ID --paths "/*"
```

### iOS -- IMPORTANT: Always use Release mode

**Debug mode** (default `expo run:ios`) does NOT embed the JS bundle -- it requires Metro bundler running at localhost:8081. This causes "No script URL provided" errors when the app launches without Metro.

**Release mode** embeds the JS bundle in the .app so it works standalone:
```bash
# Simulator
npm run ios:release
# or: npx expo run:ios --configuration Release

# Physical device
npm run ios:device
# or: npx expo run:ios --device --configuration Release
```

Only use Debug mode during active development when Metro is running:
```bash
npx expo run:ios   # Debug -- requires Metro running
```

### Dev Server (Web + Expo Go)
```bash
npx expo start --web
```

## Critical: Kill Other Metro Servers Before Building

**ALWAYS kill other Expo/Metro processes before building.** Multiple Expo apps share port 8081 by default. If another app's Metro bundler is running, the build can load the WRONG app's JS bundle.

```bash
# Before any build, kill stray Metro processes:
pkill -f metro; pkill -f "expo start"
# Verify port 8081 is free:
lsof -i :8081
```

## OTA Updates (EAS Update)

The app supports over-the-air JS updates via `expo-updates`:
- Channel: `production`
- Check policy: `ON_LOAD` (checks on every app launch)
- Fallback timeout: 2 seconds

To push a JS-only update without rebuilding native:
```bash
npx eas update --branch production --message "description of change"
```

## Common Issues

### "No script URL provided, make sure the packager is running"
The app was built in **Debug mode** without Metro running. Rebuild with `--configuration Release` to embed the JS bundle. See iOS section above.

### "Cannot find native module ExpoClipboard / ExponentAI"
**Not a real error.** Harmless Expo runtime warnings -- Expo probes for optional native modules at startup and logs warnings for uninstalled ones. They do not affect the app.

### TypeScript Route Errors
The app uses `typedRoutes: true` in app.json. Files outside `app/` (like `reference/`) need `as any` casts on `router.push()` calls since those paths aren't registered routes.

### Native Module Changes
If you add a new Expo module (e.g., `expo-camera`):
1. `npx expo install expo-camera`
2. Add plugin config to `app.json` if needed
3. Run `npx expo prebuild` to regenerate native projects
4. Run `npm run ios:release` to rebuild native layer

Simple JS-only changes don't need a native rebuild.

## Project Structure

```
YOUR_BOT_NAME-mobile/
├── app/                        # Expo Router screens (file-based routing)
│   ├── _layout.tsx             # Root layout (auth, theme, fonts, biometric lock)
│   ├── (tabs)/                 # Tab navigator
│   │   ├── _layout.tsx         # Tab bar config
│   │   ├── index.tsx           # Agents list
│   │   ├── chats.tsx           # Chat conversations
│   │   ├── projects.tsx        # Project tracking
│   │   ├── updates.tsx         # System updates feed
│   │   └── settings.tsx        # Settings (biometrics, push notifications)
│   ├── agent/[id].tsx          # Agent detail (Info/Chat/Logs)
│   ├── bot/[id].tsx            # Bot detail view
│   ├── memory.tsx              # Memory event viewer
│   ├── output/
│   │   ├── index.tsx           # Output list
│   │   └── [slug].tsx          # Output detail (markdown render)
│   ├── project/[id].tsx        # Project detail
│   ├── public/[id].tsx         # Public shared view
│   ├── stocks/
│   │   ├── _layout.tsx         # Stocks tab layout
│   │   ├── all.tsx             # All stocks overview
│   │   ├── trades.tsx          # Trade history
│   │   └── volume-shocks.tsx   # Volume shock alerts
│   └── mocks/                  # UX iteration screens
├── src/
│   ├── components/             # Reusable UI
│   │   ├── AgentListItem.tsx   # Agent row in list
│   │   ├── BotListItem.tsx     # Bot row in list
│   │   ├── ChatBubble.tsx      # Chat message bubble
│   │   ├── ChatInput.tsx       # Message input with image picker
│   │   ├── ScheduledJobItem.tsx # Scheduled job row
│   │   ├── StatusBadge.tsx     # Agent status indicator
│   │   ├── TypingIndicator.tsx # Typing animation
│   │   └── UpdateCard.tsx      # System update card
│   ├── hooks/                  # Data hooks
│   │   ├── useAgents.ts        # Agent list + polling
│   │   ├── useAgentChat.ts     # Agent chat messages
│   │   ├── useAgentLogs.ts     # Agent execution logs
│   │   ├── useAutoRefresh.ts   # Auto-refresh timer
│   │   ├── useBiometricLock.ts # Face ID / fingerprint lock
│   │   ├── useBots.ts          # Bot list
│   │   ├── useChats.ts         # Chat conversations
│   │   ├── useCreateCommand.ts # Send command to agent
│   │   ├── useProjects.ts      # Project data
│   │   ├── usePushNotifications.ts # Expo push token registration
│   │   ├── useResponsive.ts    # Responsive layout breakpoints
│   │   ├── useScheduledJobs.ts # Scheduled job list
│   │   ├── useUnreadNotifications.ts # Unread badge count
│   │   ├── useUpdates.ts       # System updates feed
│   │   └── useUsage.ts         # Usage/billing data
│   ├── services/               # API clients
│   │   ├── api.ts              # Base API client
│   │   ├── auth.ts             # Cognito auth (Amplify v6)
│   │   ├── lambda.ts           # Lambda invocation (SDK v3)
│   │   └── upload.ts           # S3 presigned upload
│   └── types/
│       └── agent.ts            # TypeScript interfaces
├── ios/                        # Native iOS project (auto-generated)
├── android/                    # Native Android project (auto-generated)
├── app.json                    # Expo config
├── eas.json                    # EAS Build config
└── .env                        # EXPO_PUBLIC_AWS_* env vars
```

## Key Types

All defined in `src/types/agent.ts`:
- `Agent` -- agent_id, agent_name, title, status, goal, metrics, etc.
- `AgentChatMessage` -- agent_id, timestamp (number), direction, message, sender
- `AgentChatMessageOptimistic` -- extends AgentChatMessage with optimistic/pending flags
- `AgentLog` -- agent_id, timestamp (number), level, message, metadata

## Key Features

- **Biometric Lock** -- Face ID / Touch ID via `expo-local-authentication` + `expo-secure-store`
- **Push Notifications** -- Expo push notifications for agent updates
- **Image Messages** -- Send images via `expo-image-picker` + S3 presigned upload
- **OTA Updates** -- JS-only updates via `expo-updates` without App Store rebuild
- **Responsive Layout** -- Adapts between phone/tablet/web via `useResponsive`
- **Typing Indicators** -- Real-time agent activity feedback

## Tech Stack
- Expo SDK 54, React 19, React Native 0.81
- TypeScript 5.9 (strict mode)
- AWS Amplify v6 (Cognito auth)
- AWS SDK v3 (Lambda invocation)
- Expo Router v6 (typed routes)
