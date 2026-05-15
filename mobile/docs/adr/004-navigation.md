# ADR-004 — Navigation: go_router

**Status:** Accepted | **Date:** 2026-05-15 | **Sprint:** 5

## Decision

**Use `go_router` (^14.6.0) with declarative route configuration and auth guards.**

## Rationale

- Declarative routing (single source of truth)
- Built-in support for deep links (required for FCM push → specific RFI/zone)
- Auth guards via redirect callback (clean integration with Riverpod)
- Type-safe routes via `go_router_builder` if needed later
- Official Flutter team support

## Route tree

```
/login                                   → LoginScreen
/                                        → MyJobsScreen (HOME, default after login)
/zones/:zoneId                           → ZoneDetailScreen
/zones/:zoneId/plan                      → PlanViewerScreen
/zones/:zoneId/report                    → ProgressReportScreen
/rfis                                    → RFIListScreen
/rfis/:rfiId                             → RFIDetailScreen (read-only)
/assistant                               → AssistantScreen
/settings                                → SettingsScreen
```

## Auth guard

```dart
GoRouter(
  redirect: (context, state) {
    final isAuthed = ref.read(authStateProvider).value != null;
    final isLoginRoute = state.matchedLocation == '/login';

    if (!isAuthed && !isLoginRoute) return '/login';
    if (isAuthed && isLoginRoute) return '/';
    return null;
  },
  ...
)
```

## Deep linking from FCM

When a push notification arrives with payload `{type: 'rfi_answered', rfi_id: 'X'}`:
1. `firebase_messaging` `onMessageOpenedApp` fires
2. Handler calls `router.go('/rfis/X')`
3. Auth guard ensures user is logged in first

## Consequences

**Positive:**
- Single routing source
- Deep links work out of the box
- Bottom navigation can use `StatefulShellRoute` for tab persistence

**Negative:**
- Path-based navigation requires careful URL design
- StatefulShellRoute API is verbose

## References
- Master prompt PROMPT 9 (line 6115): "Push notifications FCM con deep linking a zona/RFI específico"
