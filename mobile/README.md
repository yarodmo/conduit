# Conduit Mobile — Flutter App

Field technician app for Conduit MEP platform.
**Status:** Sprint 5 — foundation in place, features building turn by turn.

## Quick start (first time)

This codebase is hand-authored. To bootstrap platform-specific files
(Android `android/`, iOS `ios/`, generated plugin registrants):

```bash
cd mobile
# Generates platform code WITHOUT overwriting lib/, pubspec.yaml, test/, docs/
flutter create --project-name=conduit_mobile \
  --org=com.blissystems \
  --platforms=android,ios .

flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter test
```

## Stack (see `docs/adr/`)

| Layer | Choice | ADR |
|-------|--------|-----|
| State management | flutter_riverpod ^2.5.1 + riverpod_annotation | 001 |
| Offline persistence | Hive CE + sync queue | 002 |
| HTTP client | Dio + Retrofit | 003 |
| Navigation | go_router | 004 |
| Push notifications | firebase_messaging | 005 |

## Project structure

```
mobile/
├── lib/
│   ├── main.dart                  Entry point
│   ├── app.dart                   MaterialApp + theme + router
│   ├── core/
│   │   ├── config/                Env, theme
│   │   ├── network/               Dio client + interceptors
│   │   ├── router/                go_router config
│   │   └── storage/               Hive boot + secure storage
│   ├── shared/
│   │   ├── sync/                  Offline queue (Hive)
│   │   └── widgets/               OfflineBanner, SyncStatusIndicator
│   └── features/
│       ├── auth/                  Sprint 5 Turn 1
│       ├── jobs/                  Sprint 5 Turn 2 (in progress)
│       ├── plan-viewer/           Sprint 5 Turn 3
│       ├── progress/              Sprint 5 Turn 4
│       ├── rfis/                  Sprint 5 Turn 5
│       └── sync/                  Sprint 5 Turn 6 (engine)
├── test/                          Widget + unit tests
└── docs/adr/                      Architecture Decision Records
```

## Environment variables

Build with `--dart-define`:

```bash
flutter build apk \
  --dart-define=API_BASE_URL=https://api.climbpeakdigital.com \
  --dart-define=ENVIRONMENT=production
```

Available variables (see `lib/core/config/env.dart`):
- `API_BASE_URL` — defaults to production endpoint
- `ENVIRONMENT` — `production` | `staging` | `development`

## Firebase setup

Required for FCM push (ADR-005). NOT in repo (gitignored):
- `android/app/google-services.json`
- `ios/Runner/GoogleService-Info.plist`

Generate via `flutterfire configure` against the Conduit Firebase project.

## Backend dependency

Mobile consumes APIs from `../backend/`. Production backend lives at
`https://api.climbpeakdigital.com`. All endpoints documented in
`../CONDUIT_MASTER_PROMPT_v11.md`.
