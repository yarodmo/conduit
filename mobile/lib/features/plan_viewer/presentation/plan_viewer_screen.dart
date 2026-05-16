import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';
import 'package:conduit_mobile/features/plan_viewer/data/plans_repository.dart';
import 'package:conduit_mobile/features/plan_viewer/domain/plan.dart';
import 'package:conduit_mobile/features/plan_viewer/providers.dart';
import 'package:conduit_mobile/features/plan_viewer/presentation/widgets/ask_ai_fab.dart';
import 'package:conduit_mobile/features/plan_viewer/presentation/widgets/zone_detail_sheet.dart';

/// Touch-optimized plan viewer with InteractiveViewer for pinch/zoom.
/// Tiles fetched from cache-first repository; works offline.
class PlanViewerScreen extends ConsumerWidget {
  const PlanViewerScreen({
    required this.planId,
    this.zones = const [],
    super.key,
  });

  final String planId;

  /// Optional: zones overlay (chips at top). Tapping shows detail sheet.
  final List<Zone> zones;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metadataAsync = ref.watch(planMetadataProvider(planId));
    final currentPage = ref.watch(currentPageProvider(planId));

    return Scaffold(
      appBar: AppBar(
        title: metadataAsync.maybeWhen(
          data: (m) => Text(m.plan.name),
          orElse: () => const Text('Plan viewer'),
        ),
        actions: [
          metadataAsync.maybeWhen(
            data: (m) => _PageSelector(
              current: currentPage,
              total: m.plan.pageCount,
              onChange: (p) =>
                  ref.read(currentPageProvider(planId).notifier).state = p,
            ),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: metadataAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Could not load plan: $e')),
        data: (meta) => _PlanBody(
          plan: meta.plan,
          page: currentPage,
          zones: zones,
        ),
      ),
      floatingActionButton: AskAiFab(
        onPressed: () => _openAskAiSheet(context),
      ),
    );
  }

  void _openAskAiSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _AskAiSheet(),
    );
  }
}

class _PlanBody extends ConsumerWidget {
  const _PlanBody({
    required this.plan,
    required this.page,
    required this.zones,
  });

  final Plan plan;
  final int page;
  final List<Zone> zones;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tileAsync =
        ref.watch(pageTileProvider(PageTileKey(planId: plan.id, page: page)));

    return Stack(
      children: [
        Positioned.fill(
          child: tileAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => _TileErrorView(error: e),
            data: (bytes) => _ZoomablePlan(bytes: bytes),
          ),
        ),
        if (zones.isNotEmpty)
          Positioned(
            top: 12,
            left: 12,
            right: 12,
            child: _ZoneChipBar(zones: zones),
          ),
      ],
    );
  }
}

class _ZoomablePlan extends StatelessWidget {
  const _ZoomablePlan({required this.bytes});

  final Uint8List bytes;

  @override
  Widget build(BuildContext context) {
    return InteractiveViewer(
      minScale: 0.5,
      maxScale: 5.0,
      boundaryMargin: const EdgeInsets.all(80),
      child: Center(
        child: Image.memory(
          bytes,
          fit: BoxFit.contain,
          gaplessPlayback: true,
        ),
      ),
    );
  }
}

class _TileErrorView extends StatelessWidget {
  const _TileErrorView({required this.error});
  final Object error;

  @override
  Widget build(BuildContext context) {
    final isCacheMiss = error is PlanCacheMissException;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isCacheMiss ? Icons.cloud_off : Icons.broken_image,
              size: 64,
              color: Theme.of(context).hintColor,
            ),
            const SizedBox(height: 16),
            Text(
              isCacheMiss
                  ? 'This page is not cached for offline viewing.'
                  : 'Could not load page.',
              textAlign: TextAlign.center,
              style:
                  const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
            ),
          ],
        ),
      ),
    );
  }
}

class _ZoneChipBar extends StatelessWidget {
  const _ZoneChipBar({required this.zones});
  final List<Zone> zones;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.92),
      borderRadius: BorderRadius.circular(24),
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: zones
                .map(
                  (zone) => Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: ActionChip(
                      avatar: CircleAvatar(
                        backgroundColor: _statusColor(zone.status),
                        radius: 6,
                      ),
                      label: Text(zone.name),
                      onPressed: () => ZoneDetailSheet.show(
                        context,
                        zone: zone,
                        items: const [], // populated from cache in Turn 6
                      ),
                    ),
                  ),
                )
                .toList(),
          ),
        ),
      ),
    );
  }

  Color _statusColor(ZoneStatus status) => switch (status) {
        ZoneStatus.notStarted => Colors.grey,
        ZoneStatus.inProgress => const Color(0xFFFDD835),
        ZoneStatus.completed => const Color(0xFF43A047),
        ZoneStatus.blocked => const Color(0xFFE53935),
      };
}

class _PageSelector extends StatelessWidget {
  const _PageSelector({
    required this.current,
    required this.total,
    required this.onChange,
  });

  final int current;
  final int total;
  final void Function(int) onChange;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        IconButton(
          icon: const Icon(Icons.chevron_left),
          onPressed: current > 1 ? () => onChange(current - 1) : null,
        ),
        Text('$current / $total', style: const TextStyle(fontSize: 16)),
        IconButton(
          icon: const Icon(Icons.chevron_right),
          onPressed: current < total ? () => onChange(current + 1) : null,
        ),
      ],
    );
  }
}

/// Lightweight placeholder — full AI assistant integration in Turn 5.
class _AskAiSheet extends StatelessWidget {
  const _AskAiSheet();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Ask Conduit AI',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                'Voice + text Q&A wired in Turn 5.',
                style: TextStyle(color: Theme.of(context).hintColor),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close),
                label: const Text('Close'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
