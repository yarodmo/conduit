# ADR-005 — FCM Push + Background Downloads

**Status:** Accepted | **Date:** 2026-05-15 | **Sprint:** 5

## Decision

**Use `firebase_messaging` (^15.1.5) with backend M8 FCM token registry. Background isolate pre-fetches zone bundles on `zone_assigned` push.**

## Push notification types (server → mobile)

Defined in backend `NotificationType` enum (`backend/app/models/notifications.py`):

| Type | Mobile action |
|------|---------------|
| `rfi_assigned` | Deep link to `/rfis/{rfi_id}`, in-app banner |
| `rfi_answered` | Deep link to `/rfis/{rfi_id}`, banner |
| `rfi_approaching_deadline` | Banner reminder, deep link |
| `zone_assigned` | **Trigger background download** + deep link to `/zones/{zone_id}` |
| `zone_blocked` | (For PMs — mobile may not display) |
| `takeoff_completed` | Notification only |
| `takeoff_requires_review` | Notification only |
| `mention_in_comment` | Deep link to comment context |
| `login_new_device` | Security alert banner |

## Token registration flow

```
1. App startup → request notification permission
2. firebase_messaging.getToken() → fcm_token
3. POST /api/v1/devices/fcm-token (M8 endpoint, already in prod)
   { token: fcm_token, platform: 'ios'|'android', device_name: model }
4. Backend stores in fcm_tokens table (upsert)
```

## Token rotation

`firebase_messaging.onTokenRefresh` re-registers on rotation. Old tokens marked `is_active=false` server-side via DELETE `/devices/fcm-token/{id}`.

## Background message handler

```dart
@pragma('vm:entry-point')
Future<void> _backgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  final type = message.data['type'];

  if (type == 'zone_assigned') {
    // Spawn isolate for pre-fetch
    await _prefetchZoneBundle(message.data['zone_id']);
  }
}
```

The pre-fetch isolate calls the backend bundle endpoint (sync/pull subset) and writes to Hive.

## Permission UX

- iOS: Show pre-permission rationale screen before native prompt (improves grant rate)
- Android 13+: Show permission rationale + handle denial gracefully
- If denied: app continues to work, just no push (in-app polling fallback every 5 min when foregrounded)

## Consequences

**Positive:**
- True offline-first: zones download automatically when assigned, even if app is killed
- Deep links from any state (background, killed)

**Negative:**
- Requires google-services.json (Android) + GoogleService-Info.plist (iOS) — NOT committed to repo (in .gitignore)
- Firebase project setup is a manual deploy step (documented in `docs/runbooks/firebase-setup.md` — to be created)

## References
- Backend M8 endpoints: `POST /api/v1/devices/fcm-token`, `GET /devices/fcm-tokens`, `DELETE /devices/fcm-token/{id}`
- Backend M10 pre-fetch: `POST /api/v1/assistant/cache/generate`
