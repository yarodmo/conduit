import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';
import 'package:conduit_mobile/features/plan_viewer/domain/takeoff_item.dart';

/// Bottom sheet shown when a zone is tapped on the plan.
/// Shows: zone info, cached takeoff items, action buttons.
class ZoneDetailSheet extends StatelessWidget {
  const ZoneDetailSheet({
    required this.zone,
    required this.items,
    super.key,
  });

  final Zone zone;
  final List<TakeoffItem> items;

  static Future<void> show(
    BuildContext context, {
    required Zone zone,
    required List<TakeoffItem> items,
  }) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => ZoneDetailSheet(zone: zone, items: items),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      minChildSize: 0.4,
      maxChildSize: 0.92,
      builder: (_, scrollController) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 48,
                height: 4,
                margin: const EdgeInsets.only(bottom: 12),
                decoration: BoxDecoration(
                  color: Theme.of(context).hintColor,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Text(
              zone.name,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 4),
            Wrap(
              spacing: 6,
              children: [
                Text(zone.status.displayLabel,
                    style: TextStyle(color: Theme.of(context).hintColor)),
                const Text('·'),
                Text(zone.systems.join(' · ')),
              ],
            ),
            const SizedBox(height: 16),
            Text(
              'Takeoff items (${items.length})',
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: items.isEmpty
                  ? _EmptyItems()
                  : ListView.separated(
                      controller: scrollController,
                      itemCount: items.length,
                      separatorBuilder: (_, __) =>
                          const Divider(height: 1),
                      itemBuilder: (_, i) => _TakeoffItemTile(item: items[i]),
                    ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.assignment_outlined),
                    label: const Text('View RFIs'),
                    onPressed: () {
                      Navigator.of(context).pop();
                      context.push('/rfis?zone_id=${zone.id}');
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    icon: const Icon(Icons.task_alt),
                    label: const Text('Report'),
                    onPressed: () {
                      Navigator.of(context).pop();
                      context.push('/zones/${zone.id}/report');
                    },
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyItems extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text(
          'No takeoff items cached for this zone.\n'
          'They download automatically when the zone is assigned.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Theme.of(context).hintColor),
        ),
      ),
    );
  }
}

class _TakeoffItemTile extends StatelessWidget {
  const _TakeoffItemTile({required this.item});
  final TakeoffItem item;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(
        item.specification,
        style: const TextStyle(fontWeight: FontWeight.w500),
      ),
      subtitle: Row(
        children: [
          Text(item.displayQty),
          if (item.system != null) ...[
            const Text(' · '),
            Text(item.system!),
          ],
          if (item.tag != null) ...[
            const Text(' · '),
            Text(item.tag!,
                style: TextStyle(color: Theme.of(context).hintColor)),
          ],
        ],
      ),
      leading: CircleAvatar(
        backgroundColor:
            Theme.of(context).colorScheme.primary.withValues(alpha: 0.15),
        child: Text(
          item.type.substring(0, item.type.length.clamp(0, 3)),
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
        ),
      ),
    );
  }
}
