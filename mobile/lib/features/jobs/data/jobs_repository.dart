import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_ce_flutter/hive_flutter.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/core/storage/hive_setup.dart';
import 'package:conduit_mobile/core/storage/secure_storage_service.dart';
import 'package:conduit_mobile/features/jobs/data/zones_api.dart';
import 'package:conduit_mobile/features/jobs/domain/project.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';
import 'package:conduit_mobile/shared/sync/sync_op.dart';
import 'package:conduit_mobile/shared/sync/sync_queue_service.dart';

/// Bundle of zones grouped by their parent project. The home screen
/// uses this directly.
class JobsBundle {
  const JobsBundle({
    required this.projects,
    required this.zonesByProject,
    required this.blockedCount,
  });

  final List<Project> projects;
  final Map<String, List<Zone>> zonesByProject;
  final int blockedCount;

  int get totalZones =>
      zonesByProject.values.fold(0, (a, b) => a + b.length);

  bool get isEmpty => projects.isEmpty;
}

/// Cache-first repository: serves from Hive immediately, refreshes from
/// network in the background. On network failure, returns cached data.
class JobsRepository {
  JobsRepository(this._api, this._storage, this._syncQueue);

  final ZonesApi _api;
  final SecureStorageService _storage;
  final SyncQueueService _syncQueue;

  static const _projectsCacheKey = 'projects_list';
  static const _zonesCacheKeyPrefix = 'zones_for_';

  Box<dynamic> get _projectsBox =>
      Hive.box<dynamic>(HiveSetup.projectsBox);
  Box<dynamic> get _zonesBox => Hive.box<dynamic>(HiveSetup.zonesBox);

  /// Fetches all jobs (projects + their zones) for the current user.
  ///
  /// Strategy:
  ///  1. Read fresh from network, persist to Hive, return.
  ///  2. On network failure: read from Hive cache.
  Future<JobsBundle> fetchJobs({bool forceRefresh = false}) async {
    final userId = await _storage.readUserId();
    if (userId == null) {
      return const JobsBundle(
        projects: [],
        zonesByProject: {},
        blockedCount: 0,
      );
    }

    try {
      final projects = await _api.listProjects();
      await _cacheProjects(projects);

      final zonesByProject = <String, List<Zone>>{};
      var blocked = 0;

      for (final project in projects) {
        final zones = await _api.listZones(project.id);
        final myZones =
            zones.where((z) => z.assignedTo == userId).toList()
              ..sort((a, b) => a.orderIndex.compareTo(b.orderIndex));

        if (myZones.isEmpty) continue;
        zonesByProject[project.id] = myZones;
        blocked += myZones.where((z) => z.isBlocked).length;
        await _cacheZones(project.id, myZones);
      }

      // Filter out projects the user has no zones in
      final filteredProjects =
          projects.where((p) => zonesByProject.containsKey(p.id)).toList();

      return JobsBundle(
        projects: filteredProjects,
        zonesByProject: zonesByProject,
        blockedCount: blocked,
      );
    } on DioException {
      return _loadFromCache(userId);
    }
  }

  Future<JobsBundle> _loadFromCache(String userId) async {
    final rawProjects = _projectsBox.get(_projectsCacheKey);
    if (rawProjects is! List) {
      return const JobsBundle(
        projects: [],
        zonesByProject: {},
        blockedCount: 0,
      );
    }

    final projects = rawProjects
        .whereType<String>()
        .map((s) => Project.fromJson(jsonDecode(s) as Map<String, dynamic>))
        .toList();

    final zonesByProject = <String, List<Zone>>{};
    var blocked = 0;

    for (final project in projects) {
      final raw = _zonesBox.get('$_zonesCacheKeyPrefix${project.id}');
      if (raw is! List) continue;
      final zones = raw
          .whereType<String>()
          .map((s) => Zone.fromJson(jsonDecode(s) as Map<String, dynamic>))
          .where((z) => z.assignedTo == userId)
          .toList();
      if (zones.isEmpty) continue;
      zonesByProject[project.id] = zones;
      blocked += zones.where((z) => z.isBlocked).length;
    }

    final filteredProjects =
        projects.where((p) => zonesByProject.containsKey(p.id)).toList();

    return JobsBundle(
      projects: filteredProjects,
      zonesByProject: zonesByProject,
      blockedCount: blocked,
    );
  }

  Future<void> _cacheProjects(List<Project> projects) async {
    final serialized = projects.map((p) => jsonEncode(p.toJson())).toList();
    await _projectsBox.put(_projectsCacheKey, serialized);
  }

  Future<void> _cacheZones(String projectId, List<Zone> zones) async {
    final serialized = zones.map((z) => jsonEncode(z.toJson())).toList();
    await _zonesBox.put('$_zonesCacheKeyPrefix$projectId', serialized);
  }

  /// Update zone status. Online: PATCH directly. Offline: enqueue.
  Future<void> updateZoneStatus({
    required String projectId,
    required String zoneId,
    required ZoneStatus newStatus,
    String? blockedReason,
  }) async {
    final body = ZoneStatusUpdate(
      status: newStatus.serverValue,
      blockedReason: blockedReason,
    );
    try {
      await _api.updateStatus(projectId, zoneId, body);
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        await _syncQueue.enqueue(
          operation: SyncOpType.updateZoneStatus,
          payload: {
            'project_id': projectId,
            'zone_id': zoneId,
            'status': newStatus.serverValue,
            if (blockedReason != null) 'blocked_reason': blockedReason,
          },
        );
        return;
      }
      rethrow;
    }
  }
}

final zonesApiProvider = Provider<ZonesApi>(
  (ref) => ZonesApi(ref.watch(dioProvider)),
);

final jobsRepositoryProvider = Provider<JobsRepository>(
  (ref) => JobsRepository(
    ref.watch(zonesApiProvider),
    ref.watch(secureStorageProvider),
    ref.watch(syncQueueServiceProvider),
  ),
);
