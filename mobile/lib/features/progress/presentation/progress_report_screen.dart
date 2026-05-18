import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:conduit_mobile/features/progress/data/photo_capture_service.dart';
import 'package:conduit_mobile/features/progress/domain/progress_report.dart';
import 'package:conduit_mobile/features/progress/presentation/widgets/photo_grid.dart';
import 'package:conduit_mobile/features/progress/presentation/widgets/progress_slider.dart';
import 'package:conduit_mobile/features/progress/presentation/widgets/status_picker.dart';
import 'package:conduit_mobile/features/progress/providers.dart';
import 'package:conduit_mobile/shared/widgets/offline_banner.dart';
import 'package:conduit_mobile/shared/widgets/voice_field.dart';

class ProgressReportScreen extends ConsumerWidget {
  const ProgressReportScreen({
    required this.projectId,
    required this.zoneId,
    super.key,
  });

  final String projectId;
  final String zoneId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final form = ref.watch(progressFormControllerProvider);
    final ctrl = ref.read(progressFormControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Report progress'),
      ),
      body: Column(
        children: [
          const OfflineBanner(),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ProgressSlider(
                    value: form.progressPct,
                    onChanged: ctrl.setProgressPct,
                  ),
                  const SizedBox(height: 24),
                  StatusPicker(
                    current: form.status,
                    onChanged: ctrl.setStatus,
                  ),
                  if (form.status == ReportStatusPick.blocked) ...[
                    const SizedBox(height: 16),
                    VoiceField(
                      label: 'Why is this blocked? *',
                      hint: 'e.g., Missing structural drawing for wall opening',
                      value: form.blockedReason,
                      onChanged: ctrl.setBlockedReason,
                      prefixIcon: const Icon(Icons.report_problem_outlined),
                      maxLength: 1000,
                    ),
                  ],
                  const SizedBox(height: 24),
                  PhotoGrid(
                    photos: form.photos,
                    onAdd: () async {
                      final photo = await ref
                          .read(photoCaptureServiceProvider)
                          .captureFromCamera();
                      if (photo != null) ctrl.addPhoto(photo);
                    },
                    onRemove: ctrl.removePhoto,
                  ),
                  const SizedBox(height: 24),
                  VoiceField(
                    label: 'Notes (optional)',
                    hint: 'Anything else worth flagging?',
                    value: form.notes,
                    onChanged: ctrl.setNotes,
                    prefixIcon: const Icon(Icons.notes_outlined),
                    maxLines: 4,
                    maxLength: 2000,
                  ),
                  if (form.error != null) ...[
                    const SizedBox(height: 16),
                    Text(
                      form.error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: FilledButton.icon(
                icon: form.submitting
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.send),
                label: const Text('Submit Report'),
                onPressed: form.submitting || !form.isValid
                    ? null
                    : () async {
                        HapticFeedback.heavyImpact();
                        final success = await ctrl.submit(
                          projectId: projectId,
                          zoneId: zoneId,
                        );
                        if (success && context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Report submitted'),
                              behavior: SnackBarBehavior.floating,
                            ),
                          );
                          context.pop();
                        }
                      },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
