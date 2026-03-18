# YOUR_BOT_NAME Mobile — Build Process

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
aws cloudfront create-invalidation --distribution-id E2BMAFSRPEI2SX --paths "/*"
```

### iOS — IMPORTANT: Always use Release mode

**Debug mode** (default `expo run:ios`) does NOT embed the JS bundle — it requires Metro bundler running at localhost:8081. This causes "No script URL provided" errors when the app launches without Metro.

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
npx expo run:ios   # Debug — requires Metro running
```

### Dev Server (Web + Expo Go)
```bash
npx expo start --web
```

## Critical: Kill Other Metro Servers Before Building

**ALWAYS kill other Expo/Metro processes before building.** Multiple Expo apps share port 8081 by default. If another app's Metro bundler is running (e.g., Altum Realty on port 8081), the YOUR_BOT_NAME build can load the WRONG app's JS bundle — resulting in the correct native shell but completely wrong app content.

```bash
# Before any build, kill stray Metro processes:
pkill -f metro; pkill -f "expo start"
# Verify port 8081 is free:
lsof -i :8081
```

This happened Feb 2026: Altum Realty's Metro was on 8081, YOUR_BOT_NAME builds grabbed Altum's JS code. The app showed the YOUR_BOT_NAME splash screen then loaded Altum Realty. Fix was applied in `AppDelegate.swift` — Release mode now ignores deep link bundle URL overrides and always uses the embedded `main.jsbundle`.

## Common Issues

### "No script URL provided, make sure the packager is running"
The app was built in **Debug mode** without Metro running. Rebuild with `--configuration Release` to embed the JS bundle. See iOS section above.

### "Cannot find native module ExpoClipboard / ExponentAI"
**Not a real error.** Harmless Expo runtime warnings — Expo probes for optional native modules at startup and logs warnings for uninstalled ones. They do not affect the app.

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
├── app/                    # Expo Router screens (file-based routing)
│   ├── _layout.tsx         # Root layout (auth, theme, fonts)
│   ├── (tabs)/             # Tab navigator
│   │   ├── index.tsx       # Agents list
│   │   ├── updates.tsx     # System updates feed
│   │   └── settings.tsx    # Settings
│   ├── agent/[id].tsx      # Agent detail (Info/Chat/Logs)
│   └── mocks/              # UX iteration screens (v1/v2/v3)
├── src/
│   ├── components/         # Reusable UI (ChatBubble, StatusBadge, etc.)
│   ├── hooks/              # Data hooks (useAgents, useAgentChat, etc.)
│   ├── services/           # API clients (Lambda, upload, auth)
│   └── types/              # TypeScript interfaces
├── reference/              # UX reference mocks (not production screens)
├── ios/                    # Native iOS project (auto-generated)
├── android/                # Native Android project (auto-generated)
├── app.json                # Expo config
├── eas.json                # EAS Build config
└── .env                    # EXPO_PUBLIC_AWS_* env vars
```

## Key Types

All defined in `src/types/agent.ts`:
- `Agent` — agent_id, agent_name, title, status, goal, metrics, etc.
- `AgentChatMessage` — agent_id, timestamp (number), direction, message, sender
- `AgentChatMessageOptimistic` — extends AgentChatMessage with optimistic/pending flags
- `AgentLog` — agent_id, timestamp (number), level, message, metadata

## Tech Stack
- Expo SDK 54, React 19, React Native 0.81
- TypeScript 5.9 (strict mode)
- AWS Amplify v6 (Cognito auth)
- AWS SDK v3 (Lambda invocation)
- Expo Router v6 (typed routes)
