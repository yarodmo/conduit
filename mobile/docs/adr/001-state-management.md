# ADR-001 — State Management: Riverpod

**Status:** Accepted | **Date:** 2026-05-15 | **Sprint:** 5

## Context

Conduit mobile needs reactive state management that:
1. Handles auth + JWT refresh transparently
2. Manages offline state (online/offline/syncing)
3. Persists Hive box state reactively to UI
4. Supports dependency injection for testability
5. Has compile-time safety + code generation

## Decision

**Use `flutter_riverpod` (^2.5.1) with `riverpod_annotation` for code generation.**

## Alternatives considered

| Option | Verdict | Reason |
|--------|---------|--------|
| **Bloc** | Rejected | More boilerplate, event-driven model heavier than needed for offline-first |
| **Provider** | Rejected | Lacks compile-time provider safety, deprecated in favor of Riverpod |
| **GetX** | Rejected | Magic globals, no compile-time DI verification, opinionated routing conflicts with go_router |
| **MobX** | Rejected | Requires build_runner for everything, adds friction |
| **Riverpod** | ✅ Accepted | Compile-time DI, supports async providers, integrates with Hive listeners, dev-tools mature |

## Consequences

**Positive:**
- Provider overrides for testing
- Async providers handle network + offline transparently
- `keepAlive: false` for screen-scoped state
- Code generation via `riverpod_generator` reduces boilerplate

**Negative:**
- Learning curve for team members familiar with Bloc
- Code generation step adds build time (~3-5s incremental)

## Implementation pattern

```dart
@riverpod
class AuthState extends _$AuthState {
  @override
  AsyncValue<User?> build() => const AsyncLoading();

  Future<void> login(String email, String password) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => ref.read(authRepoProvider).login(email, password));
  }
}
```

## References
- Master prompt v11 ADR-002 (Mobile stack: "Flutter 3.x / Riverpod / Hive")
