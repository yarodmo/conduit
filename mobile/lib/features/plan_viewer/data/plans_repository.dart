import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_ce_flutter/hive_flutter.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/core/storage/hive_setup.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_api.dart';

/// Cache-first plan + tile loader.
///
/// Tile bytes are stored in `plans_cache_box` keyed by `{planId}/{page}/{z}/{x}/{y}`.
/// On cache miss, fetches from network and persists. On offline, returns cached
/// bytes or throws `PlanCacheMissException`.
class PlanCacheMissException implements Exception {
  const PlanCacheMissException(this.key);
  final String key;
  @override
  String toString() => 'No cached tile for $key';
}

class PlansRepository {
  PlansRepository(this._api, this._cache);

  final PlansApi _api;
  final Box<List<int>> _cache;

  static String _tileKey(
    String planId,
    int page,
    int z,
    int x,
    int y,
  ) =>
      '$planId/$page/$z/$x/$y';

  Future<Uint8List> fetchTile({
    required String planId,
    required int page,
    int z = 0,
    int x = 0,
    int y = 0,
  }) async {
    final key = _tileKey(planId, page, z, x, y);
    final cached = _cache.get(key);
    if (cached != null) return Uint8List.fromList(cached);

    try {
      final resp = await _api.getTile(planId, page, z, x, y);
      final bytes = Uint8List.fromList(resp.data);
      await _cache.put(key, bytes);
      return bytes;
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        throw PlanCacheMissException(key);
      }
      rethrow;
    }
  }

  Future<PlanMetadata> fetchMetadata(String planId) async {
    return _api.getMetadata(planId);
  }

  /// Pre-cache all pages at lowest zoom for offline viewer.
  /// Called by the FCM background isolate on `zone_assigned` push.
  Future<int> precachePlan(String planId, int pageCount) async {
    var ok = 0;
    for (var page = 1; page <= pageCount; page++) {
      try {
        await fetchTile(planId: planId, page: page);
        ok++;
      } on Exception {
        // skip — best effort
      }
    }
    return ok;
  }

  bool isPageCached({required String planId, required int page}) {
    return _cache.containsKey(_tileKey(planId, page, 0, 0, 0));
  }

  Future<void> evictPlan(String planId) async {
    final keysToDelete =
        _cache.keys.where((k) => k.toString().startsWith('$planId/')).toList();
    await _cache.deleteAll(keysToDelete);
  }
}

final plansApiProvider = Provider<PlansApi>(
  (ref) => PlansApi(ref.watch(dioProvider)),
);

final plansRepositoryProvider = Provider<PlansRepository>(
  (ref) => PlansRepository(
    ref.watch(plansApiProvider),
    Hive.box<List<int>>(HiveSetup.plansCacheBox),
  ),
);
