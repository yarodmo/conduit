import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/ai_assistant/data/ai_assistant_repository.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_repository.dart';

/// Downloads zone assets in background on FCM `zone_assigned` event.
///
/// Fires both AI cache and plan tiles in parallel — order doesn't matter,
/// both are best-effort (any failure is silently swallowed so the user
/// is never blocked).
class ZonePreloadService {
  ZonePreloadService(this._aiRepo, this._plansRepo);

  final AiAssistantRepository _aiRepo;
  final PlansRepository _plansRepo;

  Future<void> preloadForProject(String projectId) async {
    await Future.wait([
      _aiRepo.preloadCache(projectId),
      _preloadPlans(projectId),
    ]);
  }

  Future<void> _preloadPlans(String projectId) async {
    try {
      final plans = await _plansRepo.listPlans(projectId);
      for (final plan in plans) {
        final meta = await _plansRepo.fetchMetadata(plan.id);
        await _plansRepo.precachePlan(plan.id, meta.plan.pageCount);
      }
    } catch (_) {
      // Best-effort — user can still open cached plans if available
    }
  }
}

final zonePreloadServiceProvider = Provider<ZonePreloadService>(
  (ref) => ZonePreloadService(
    ref.watch(aiAssistantRepositoryProvider),
    ref.watch(plansRepositoryProvider),
  ),
);
