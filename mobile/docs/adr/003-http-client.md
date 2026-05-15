# ADR-003 — HTTP Client: Dio + Retrofit

**Status:** Accepted | **Date:** 2026-05-15 | **Sprint:** 5

## Decision

**Use Dio (^5.7.0) as the HTTP client with Retrofit (^4.4.1) for typed API surfaces.**

## Rationale

- **Dio** supports interceptors (JWT injection, retry, refresh, logging) cleanly
- **Retrofit** generates type-safe API clients from annotations; matches FastAPI OpenAPI shape
- **No dart:io HTTP** — lacks interceptor and cancellation primitives

## Configuration

```dart
final dio = Dio(BaseOptions(
  baseUrl: Env.apiBaseUrl,                      // https://api.climbpeakdigital.com
  connectTimeout: const Duration(seconds: 10),
  receiveTimeout: const Duration(seconds: 30),
  headers: {'Content-Type': 'application/json'},
))
  ..interceptors.add(AuthInterceptor(ref))      // Injects JWT, handles 401 refresh
  ..interceptors.add(OrgIdInterceptor(ref))     // Injects X-Organization-ID
  ..interceptors.add(OfflineQueueInterceptor()) // Catches network errors → queue
  ..interceptors.add(LogInterceptor(...));      // Dev only
```

## Interceptor responsibilities

| Interceptor | Order | Responsibility |
|-------------|-------|----------------|
| AuthInterceptor | 1 | Reads JWT from secure storage → `Authorization: Bearer`. On 401, attempts refresh via `/auth/refresh`; on refresh failure, redirects to login. |
| OrgIdInterceptor | 2 | Reads current `org_id` from `authStateProvider` → `X-Organization-ID` header. |
| OfflineQueueInterceptor | 3 | On `DioException` with `type == connectionError`: enqueues mutation to `sync_queue_box`, returns a synthetic 202 response so UI doesn't error. Only applies to writes (POST/PATCH/DELETE), reads bubble up the error. |
| LogInterceptor | 4 | Dev only — logs request + response. Stripped in release. |

## API surface generation

```dart
@RestApi()
abstract class ZonesApi {
  factory ZonesApi(Dio dio, {String baseUrl}) = _ZonesApi;

  @GET('/api/v1/projects/{project_id}/zones')
  Future<List<Zone>> listZones(@Path('project_id') String projectId);

  @PATCH('/api/v1/projects/{project_id}/zones/{zone_id}/status')
  Future<Zone> updateStatus(
    @Path('project_id') String projectId,
    @Path('zone_id') String zoneId,
    @Body() ZoneStatusUpdate update,
  );
}
```

## Consequences

**Positive:**
- API drift detected at compile time
- 401 refresh handled in one place
- Offline writes auto-queued

**Negative:**
- Code generation step (~5s incremental)
- Retrofit's URL-encoding edge cases require attention
