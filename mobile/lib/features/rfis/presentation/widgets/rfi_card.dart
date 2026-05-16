import 'package:flutter/material.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/features/rfis/domain/rfi.dart';

class RfiCard extends StatelessWidget {
  const RfiCard({
    required this.rfi,
    required this.onTap,
    super.key,
  });

  final RfiListItem rfi;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: _urgencyColor(rfi.urgency)
                          .withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      rfi.urgency.label,
                      style: TextStyle(
                        color: _urgencyColor(rfi.urgency),
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    rfi.rfiNumber,
                    style: TextStyle(
                      color: Theme.of(context).hintColor,
                      fontFamily: 'monospace',
                      fontSize: 13,
                    ),
                  ),
                  const Spacer(),
                  _StatusChip(status: rfi.status),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                rfi.title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Icon(Icons.schedule,
                      size: 14, color: Theme.of(context).hintColor),
                  const SizedBox(width: 4),
                  Text(
                    _formatDate(rfi.createdAt),
                    style: TextStyle(
                      color: Theme.of(context).hintColor,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Color _urgencyColor(RfiUrgency urgency) => switch (urgency) {
        RfiUrgency.low => Colors.grey,
        RfiUrgency.medium => Colors.blue.shade700,
        RfiUrgency.high => ConduitTheme.warningYellow,
        RfiUrgency.critical => ConduitTheme.errorRed,
      };

  String _formatDate(DateTime d) {
    final now = DateTime.now();
    final diff = now.difference(d);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inHours < 1) return '${diff.inMinutes}m ago';
    if (diff.inDays < 1) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});
  final RfiStatus status;

  @override
  Widget build(BuildContext context) {
    final (color, icon) = switch (status) {
      RfiStatus.draft => (Colors.grey, Icons.edit_note),
      RfiStatus.submitted =>
        (Colors.blue.shade700, Icons.arrow_circle_up_outlined),
      RfiStatus.underReview =>
        (Colors.deepPurple, Icons.rate_review_outlined),
      RfiStatus.answered =>
        (ConduitTheme.successGreen, Icons.mark_email_read_outlined),
      RfiStatus.closed =>
        (Colors.green.shade900, Icons.check_circle_outline),
      RfiStatus.rejected =>
        (ConduitTheme.errorRed, Icons.cancel_outlined),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 16),
        const SizedBox(width: 4),
        Text(
          status.label,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}
