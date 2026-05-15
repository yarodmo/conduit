# ADR-002 — Offline Architecture: Hive + Sync Queue

**Status:** Accepted | **Date:** 2026-05-15 | **Sprint:** 5

## Context

Field technicians lose connectivity routinely (basements, equipment rooms, rural sites). The Conduit mobile app MUST work offline indefinitely — write progress reports, view zones, view RFIs, query AI assistant — all without network.

Master prompt PROMPT 9 mandates:
- Hive boxes for: projects, zones (with cached takeoff items), plans tiles, AI cache, sync queue
- Sync engine processes queue on reconnect, idempotent via `client_uuid`
- Server resolves conflicts; client accepts silently
- Photos compressed before queue, original preserved locally

## Decision

**Use Hive CE (community edition) v2.x with the following box topology and an async sync engine driven by `connectivity_plus`.**

## Box topology

| Box | Type | Purpose |
|-----|------|---------|
| `auth_box` | `Box<dynamic>` | Stores user_id, org_id, refresh_token hint (JWT in flutter_secure_storage) |
| `projects_box` | `Box<ProjectHive>` | Cached projects assigned to user |
| `zones_box` | `Box<ZoneHive>` | Zones with `cached_takeoff_items` JSON inlined |
| `plans_cache_box` | `Box<Uint8List>` | Plan tile bytes keyed by `plan_id/page/z/x/y` |
| `ai_cache_box` | `Box<AICacheHive>` | Pre-fetched AI responses (24h TTL) |
| `sync_queue_box` | `Box<SyncOpHive>` | Pending mutations |
| `reports_drafts_box` | `Box<ReportDraftHive>` | Local-only progress reports being composed |

## Sync queue entry shape

```dart
class SyncOpHive {
  String clientUuid;           // For server-side dedup
  DateTime clientTimestamp;
  String operation;            // 'create_report' | 'update_zone_status' | etc.
  Map<String, dynamic> payload;
  int retryCount;
  String? lastError;
}
```

## Sync engine algorithm

1. Listen to `connectivity_plus` stream
2. On `online` event: drain `sync_queue_box`
3. Per op: POST to backend with `client_uuid` in payload
4. Backend deduplicates by `client_uuid` (already implemented in M6 `/sync/push`)
5. On success: delete from queue
6. On 4xx (validation error): mark `lastError`, increment `retryCount`, abandon after 5 retries
7. On 5xx / network error: keep in queue, exponential backoff (2s → 4s → 8s → 16s → 32s)
8. After full drain: pull updates via `/sync/pull?since=<last_sync>`

## Conflict resolution

- **COMPLETED zones cannot be reverted** (server returns conflict, client logs but does not retry)
- **Last-write-wins for status updates** (handled server-side per M6 service)
- **Photos**: append-only, no conflict possible

## Photo handling

```
1. User captures photo via camera
2. Compress to <1MB JPEG (preserve EXIF GPS)
3. Save original to app docs dir as `<report_id>_<idx>.original.jpg`
4. Save compressed as `<report_id>_<idx>.upload.jpg`
5. Enqueue upload op with compressed path
6. After successful upload, optionally delete compressed (keep original)
```

## Auto-download on zone assignment

When backend FCM push notifies "zone_assigned":
1. Mobile receives push payload `{type: 'zone_assigned', zone_id, project_id}`
2. Background isolate fetches:
   - Zone metadata + cached_takeoff_items
   - Plan tiles for relevant pages
   - Open RFIs for project
   - Top 20 AI cache responses via `/assistant/cache/generate`
3. All persisted to Hive boxes before notification displays

## Consequences

**Positive:**
- Indefinite offline work
- Zero data loss on app close
- Idempotent sync — safe to retry
- Compatible with existing backend M6 sync endpoints (no changes needed)

**Negative:**
- Hive boxes can grow large (plans cache eviction policy needed — LRU at 500MB)
- Adapter registration boilerplate (mitigated by `hive_ce_generator`)
- Background isolates for download require platform-specific setup

## References
- Backend M6: `/api/v1/projects/{id}/sync/push` + `/sync/pull` (already in prod)
- Master prompt v11 PROMPT 9 (lines 6086-6128)
