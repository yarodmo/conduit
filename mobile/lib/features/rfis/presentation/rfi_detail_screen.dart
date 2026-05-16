import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/features/rfis/data/rfis_repository.dart';
import 'package:conduit_mobile/features/rfis/domain/rfi.dart';

class RfiDetailScreen extends ConsumerWidget {
  const RfiDetailScreen({required this.rfiId, super.key});

  final String rfiId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rfiAsync = ref.watch(rfiDetailProvider(rfiId));
    return Scaffold(
      appBar: AppBar(
        title: rfiAsync.maybeWhen(
          data: (r) => Text(r.rfiNumber),
          orElse: () => const Text('RFI'),
        ),
      ),
      body: rfiAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Could not load RFI: $e')),
        data: (rfi) => _RfiBody(rfi: rfi),
      ),
    );
  }
}

class _RfiBody extends StatelessWidget {
  const _RfiBody({required this.rfi});
  final Rfi rfi;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            _UrgencyBadge(urgency: rfi.urgency),
            const SizedBox(width: 8),
            _StatusBadge(status: rfi.status),
          ],
        ),
        const SizedBox(height: 16),
        Text(
          rfi.title,
          style:
              const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 4),
        Text(
          'Created ${_relative(rfi.createdAt)} · Source: ${rfi.source}',
          style: TextStyle(color: Theme.of(context).hintColor),
        ),
        const SizedBox(height: 24),
        const Text(
          'Description',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 4),
        Text(rfi.description, style: const TextStyle(fontSize: 16)),
        const SizedBox(height: 24),
        if (rfi.comments.isNotEmpty) ...[
          const Text(
            'Timeline',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 8),
          ...rfi.comments.map((c) => _CommentTile(comment: c)),
        ],
        if (rfi.changeOrderId != null) ...[
          const SizedBox(height: 24),
          Card(
            color: ConduitTheme.successGreen.withValues(alpha: 0.1),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: const [
                  Icon(Icons.assignment_turned_in_outlined,
                      color: ConduitTheme.successGreen),
                  SizedBox(width: 8),
                  Text(
                    'Change Order created from this RFI',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _UrgencyBadge extends StatelessWidget {
  const _UrgencyBadge({required this.urgency});
  final RfiUrgency urgency;

  @override
  Widget build(BuildContext context) {
    final color = switch (urgency) {
      RfiUrgency.low => Colors.grey,
      RfiUrgency.medium => Colors.blue.shade700,
      RfiUrgency.high => ConduitTheme.warningYellow,
      RfiUrgency.critical => ConduitTheme.errorRed,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        urgency.label,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.bold,
          fontSize: 13,
        ),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final RfiStatus status;

  @override
  Widget build(BuildContext context) {
    return Chip(
      label: Text(status.label),
      visualDensity: VisualDensity.compact,
    );
  }
}

class _CommentTile extends StatelessWidget {
  const _CommentTile({required this.comment});
  final RfiComment comment;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: comment.isOfficialResponse
              ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.08)
              : Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: Theme.of(context).dividerColor,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (comment.isOfficialResponse) ...[
                  const Icon(Icons.verified, size: 16, color: Colors.blue),
                  const SizedBox(width: 4),
                  const Text(
                    'Official response',
                    style:
                        TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                  ),
                ],
                const Spacer(),
                Text(
                  _relative(comment.createdAt),
                  style: TextStyle(
                    color: Theme.of(context).hintColor,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(comment.content),
          ],
        ),
      ),
    );
  }
}

String _relative(DateTime d) {
  final diff = DateTime.now().difference(d);
  if (diff.inMinutes < 1) return 'just now';
  if (diff.inHours < 1) return '${diff.inMinutes}m ago';
  if (diff.inDays < 1) return '${diff.inHours}h ago';
  if (diff.inDays < 7) return '${diff.inDays}d ago';
  return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
