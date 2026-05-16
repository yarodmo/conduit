import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/features/jobs/providers.dart';
import 'package:conduit_mobile/features/rfis/data/rfis_api.dart';
import 'package:conduit_mobile/features/rfis/domain/rfi.dart';

class RfisRepository {
  RfisRepository(this._api);

  final RfisApi _api;

  /// Aggregates RFIs across all projects the user has zones assigned in.
  Future<List<RfiListItem>> listAcrossUserProjects(
    List<String> projectIds, {
    String? statusFilter,
  }) async {
    final all = <RfiListItem>[];
    for (final pid in projectIds) {
      try {
        final batch = await _api.listForProject(pid, statusFilter);
        all.addAll(batch);
      } on Exception {
        // Best effort — skip projects that fail
      }
    }
    all.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return all;
  }

  Future<Rfi> getRfi(String rfiId) => _api.getRfi(rfiId);
}

final rfisApiProvider = Provider<RfisApi>(
  (ref) => RfisApi(ref.watch(dioProvider)),
);

final rfisRepositoryProvider = Provider<RfisRepository>(
  (ref) => RfisRepository(ref.watch(rfisApiProvider)),
);

/// Lists RFIs across all the user's projects (derived from JobsBundle).
final myRfisProvider =
    FutureProvider.autoDispose<List<RfiListItem>>((ref) async {
  final bundle = await ref.watch(jobsBundleProvider.future);
  final projectIds = bundle.projects.map((p) => p.id).toList();
  if (projectIds.isEmpty) return [];
  return ref
      .watch(rfisRepositoryProvider)
      .listAcrossUserProjects(projectIds);
});

final rfiDetailProvider =
    FutureProvider.autoDispose.family<Rfi, String>((ref, rfiId) async {
  return ref.watch(rfisRepositoryProvider).getRfi(rfiId);
});
