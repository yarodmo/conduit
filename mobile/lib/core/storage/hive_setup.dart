import 'package:hive_ce_flutter/hive_flutter.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';

/// Bootstraps all Hive boxes. Called once from `main()` before `runApp`.
///
/// Box topology defined in ADR-002 (docs/adr/002-offline-architecture.md).
class HiveSetup {
  const HiveSetup._();

  static const String authBox = 'auth_box';
  static const String projectsBox = 'projects_box';
  static const String zonesBox = 'zones_box';
  static const String plansCacheBox = 'plans_cache_box';
  static const String aiCacheBox = 'ai_cache_box';
  static const String syncQueueBox = 'sync_queue_box';
  static const String reportsDraftsBox = 'reports_drafts_box';

  static Future<void> initialize() async {
    await Hive.initFlutter();

    // Register adapters
    Hive.registerAdapter(SyncOpAdapter());

    // Open boxes
    await Future.wait([
      Hive.openBox<dynamic>(authBox),
      Hive.openBox<dynamic>(projectsBox),
      Hive.openBox<dynamic>(zonesBox),
      Hive.openBox<List<int>>(plansCacheBox),
      Hive.openBox<dynamic>(aiCacheBox),
      Hive.openBox<SyncOp>(syncQueueBox),
      Hive.openBox<dynamic>(reportsDraftsBox),
    ]);
  }

  static Future<void> closeAll() async {
    await Hive.close();
  }

  static Future<void> clearAll() async {
    for (final name in [
      authBox, projectsBox, zonesBox, plansCacheBox,
      aiCacheBox, syncQueueBox, reportsDraftsBox,
    ]) {
      if (Hive.isBoxOpen(name)) {
        await Hive.box<dynamic>(name).clear();
      }
    }
  }
}
