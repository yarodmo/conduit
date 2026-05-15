import 'package:flutter/material.dart';
import 'package:conduit_mobile/features/jobs/domain/project.dart';
import 'package:conduit_mobile/features/jobs/domain/zone.dart';
import 'package:conduit_mobile/features/jobs/presentation/widgets/zone_card.dart';

class ProjectSection extends StatelessWidget {
  const ProjectSection({
    required this.project,
    required this.zones,
    required this.onZoneTap,
    super.key,
  });

  final Project project;
  final List<Zone> zones;
  final void Function(Zone zone) onZoneTap;

  @override
  Widget build(BuildContext context) {
    final blockedCount = zones.where((z) => z.isBlocked).length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      project.name,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      project.locationLabel,
                      style: TextStyle(
                        fontSize: 14,
                        color: Theme.of(context).hintColor,
                      ),
                    ),
                  ],
                ),
              ),
              if (blockedCount > 0)
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.error,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    '$blockedCount blocked',
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                ),
            ],
          ),
        ),
        ...zones.map((z) => ZoneCard(zone: z, onTap: () => onZoneTap(z))),
        const SizedBox(height: 12),
      ],
    );
  }
}
