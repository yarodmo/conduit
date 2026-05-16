import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/features/jobs/data/jobs_repository.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';
import 'package:conduit_mobile/features/progress/data/progress_api.dart';
import 'package:conduit_mobile/features/progress/domain/progress_report.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';

class ProgressSubmissionResult {
  const ProgressSubmissionResult({
    required this.queued,
    this.report,
  });

  /// True when submission was offline-queued rather than synced.
  final bool queued;
  final ProgressReportResponse? report;
}

class ProgressRepository {
  ProgressRepository(this._api, this._syncQueue, this._jobsRepo);

  final ProgressApi _api;
  final SyncQueueService _syncQueue;
  final JobsRepository _jobsRepo;

  Future<ProgressSubmissionResult> submit({
    required String projectId,
    required String zoneId,
    required ProgressReportCreate body,
    String? blockedReason,
  }) async {
    // Blocked status: update zone status FIRST so backend auto-creates RFI.
    final isBlocked = body.status == 'BLOCKED';
    if (isBlocked) {
      await _jobsRepo.updateZoneStatus(
        projectId: projectId,
        zoneId: zoneId,
        newStatus: ZoneStatus.blocked,
        blockedReason: blockedReason ?? body.notes ?? 'See report notes',
      );
    }

    try {
      final response = await _api.submitReport(projectId, zoneId, body);
      return ProgressSubmissionResult(queued: false, report: response);
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        await _syncQueue.enqueue(
          operation: SyncOpType.createReport,
          payload: {
            'project_id': projectId,
            'zone_id': zoneId,
            'body': body.toJson(),
            if (blockedReason != null) 'blocked_reason': blockedReason,
          },
        );
        return const ProgressSubmissionResult(queued: true);
      }
      rethrow;
    }
  }
}

final progressApiProvider = Provider<ProgressApi>(
  (ref) => ProgressApi(ref.watch(dioProvider)),
);

final progressRepositoryProvider = Provider<ProgressRepository>(
  (ref) => ProgressRepository(
    ref.watch(progressApiProvider),
    ref.watch(syncQueueServiceProvider),
    ref.watch(jobsRepositoryProvider),
  ),
);
