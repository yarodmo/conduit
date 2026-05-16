import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_api.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_repository.dart';

/// Identifier for a page tile request — composable family key.
class PageTileKey {
  const PageTileKey({required this.planId, required this.page});

  final String planId;
  final int page;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is PageTileKey &&
          other.planId == planId &&
          other.page == page);

  @override
  int get hashCode => Object.hash(planId, page);
}

final planMetadataProvider =
    FutureProvider.family<PlanMetadata, String>((ref, planId) async {
  return ref.watch(plansRepositoryProvider).fetchMetadata(planId);
});

final pageTileProvider =
    FutureProvider.family.autoDispose<Uint8List, PageTileKey>((ref, key) async {
  return ref.watch(plansRepositoryProvider).fetchTile(
        planId: key.planId,
        page: key.page,
      );
});

/// Current page index for a plan, controllable by the viewer.
final currentPageProvider =
    StateProvider.family.autoDispose<int, String>((ref, planId) => 1);
