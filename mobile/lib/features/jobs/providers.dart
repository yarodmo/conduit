import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/jobs/data/jobs_repository.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';

/// Asynchronously loads the user's jobs bundle (projects + zones).
final jobsBundleProvider = FutureProvider.autoDispose<JobsBundle>((ref) async {
  return ref.watch(jobsRepositoryProvider).fetchJobs();
});

/// Convenience: reactive blocked zone count.
final blockedZonesCountProvider = Provider<int>((ref) {
  return ref.watch(jobsBundleProvider).asData?.value.blockedCount ?? 0;
});

/// Single-zone updater. UI calls this on action buttons.
class ZoneStatusUpdater {
  ZoneStatusUpdater(this._ref);

  final Ref _ref;

  Future<void> markInProgress({
    required String projectId,
    required String zoneId,
  }) async {
    await _ref.read(jobsRepositoryProvider).updateZoneStatus(
          projectId: projectId,
          zoneId: zoneId,
          newStatus: ZoneStatus.inProgress,
        );
    _ref.invalidate(jobsBundleProvider);
  }

  Future<void> markCompleted({
    required String projectId,
    required String zoneId,
  }) async {
    await _ref.read(jobsRepositoryProvider).updateZoneStatus(
          projectId: projectId,
          zoneId: zoneId,
          newStatus: ZoneStatus.completed,
        );
    _ref.invalidate(jobsBundleProvider);
  }

  Future<void> markBlocked({
    required String projectId,
    required String zoneId,
    required String reason,
  }) async {
    await _ref.read(jobsRepositoryProvider).updateZoneStatus(
          projectId: projectId,
          zoneId: zoneId,
          newStatus: ZoneStatus.blocked,
          blockedReason: reason,
        );
    _ref.invalidate(jobsBundleProvider);
  }
}

final zoneStatusUpdaterProvider = Provider<ZoneStatusUpdater>(
  ZoneStatusUpdater.new,
);
