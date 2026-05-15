import 'package:flutter/material.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';

class ZoneCard extends StatelessWidget {
  const ZoneCard({
    required this.zone,
    required this.onTap,
    super.key,
  });

  final Zone zone;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final (statusColor, statusIcon) = _statusVisuals(zone.status);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      clipBehavior: Clip.antiAlias,
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
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      zone.name,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Icon(statusIcon, color: statusColor),
                ],
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: zone.systems
                    .map((s) => Chip(
                          label: Text(s, style: const TextStyle(fontSize: 12)),
                          materialTapTargetSize:
                              MaterialTapTargetSize.shrinkWrap,
                          visualDensity: VisualDensity.compact,
                        ))
                    .toList(),
              ),
              if (zone.isBlocked && zone.blockedReason != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: ConduitTheme.errorRed.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: ConduitTheme.errorRed.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.report_problem,
                          color: ConduitTheme.errorRed, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          zone.blockedReason!,
                          style: TextStyle(
                            color: colorScheme.onSurface,
                            fontSize: 14,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 8),
              Text(
                zone.status.displayLabel,
                style: TextStyle(color: statusColor, fontSize: 14),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static (Color, IconData) _statusVisuals(ZoneStatus status) {
    return switch (status) {
      ZoneStatus.notStarted => (Colors.grey, Icons.radio_button_unchecked),
      ZoneStatus.inProgress =>
        (ConduitTheme.warningYellow, Icons.play_circle_outline),
      ZoneStatus.completed =>
        (ConduitTheme.successGreen, Icons.check_circle),
      ZoneStatus.blocked =>
        (ConduitTheme.errorRed, Icons.block),
    };
  }
}
