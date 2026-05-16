import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:conduit_mobile/core/config/theme.dart';
import 'package:conduit_mobile/features/progress/domain/progress_report.dart';

class StatusPicker extends StatelessWidget {
  const StatusPicker({
    required this.current,
    required this.onChanged,
    super.key,
  });

  final ReportStatusPick current;
  final ValueChanged<ReportStatusPick> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Status',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            _StatusButton(
              status: ReportStatusPick.onTrack,
              current: current,
              color: ConduitTheme.successGreen,
              icon: Icons.check_circle_outline,
              onTap: onChanged,
            ),
            const SizedBox(width: 8),
            _StatusButton(
              status: ReportStatusPick.issues,
              current: current,
              color: ConduitTheme.warningYellow,
              icon: Icons.warning_amber_outlined,
              onTap: onChanged,
            ),
            const SizedBox(width: 8),
            _StatusButton(
              status: ReportStatusPick.blocked,
              current: current,
              color: ConduitTheme.errorRed,
              icon: Icons.block,
              onTap: onChanged,
            ),
          ],
        ),
      ],
    );
  }
}

class _StatusButton extends StatelessWidget {
  const _StatusButton({
    required this.status,
    required this.current,
    required this.color,
    required this.icon,
    required this.onTap,
  });

  final ReportStatusPick status;
  final ReportStatusPick current;
  final Color color;
  final IconData icon;
  final ValueChanged<ReportStatusPick> onTap;

  @override
  Widget build(BuildContext context) {
    final isActive = current == status;
    return Expanded(
      child: Material(
        color: isActive ? color : color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () {
            HapticFeedback.selectionClick();
            onTap(status);
          },
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color, width: isActive ? 0 : 2),
            ),
            child: Column(
              children: [
                Icon(
                  icon,
                  size: 28,
                  color: isActive ? Colors.white : color,
                ),
                const SizedBox(height: 4),
                Text(
                  status.label,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: isActive ? Colors.white : color,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
