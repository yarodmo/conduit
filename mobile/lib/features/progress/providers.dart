import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/progress/data/progress_repository.dart';
import 'package:conduit_mobile/features/progress/data/location_service.dart';
import 'package:conduit_mobile/features/progress/domain/captured_photo.dart';
import 'package:conduit_mobile/features/progress/domain/progress_report.dart';

/// Local form state for the progress report screen.
class ProgressFormState {
  const ProgressFormState({
    this.progressPct = 0,
    this.status = ReportStatusPick.onTrack,
    this.notes = '',
    this.materials = const [],
    this.photos = const [],
    this.blockedReason = '',
    this.submitting = false,
    this.error,
  });

  final int progressPct;
  final ReportStatusPick status;
  final String notes;
  final List<MaterialUsedEntry> materials;
  final List<CapturedPhoto> photos;
  final String blockedReason;
  final bool submitting;
  final String? error;

  ProgressFormState copyWith({
    int? progressPct,
    ReportStatusPick? status,
    String? notes,
    List<MaterialUsedEntry>? materials,
    List<CapturedPhoto>? photos,
    String? blockedReason,
    bool? submitting,
    String? error,
    bool clearError = false,
  }) {
    return ProgressFormState(
      progressPct: progressPct ?? this.progressPct,
      status: status ?? this.status,
      notes: notes ?? this.notes,
      materials: materials ?? this.materials,
      photos: photos ?? this.photos,
      blockedReason: blockedReason ?? this.blockedReason,
      submitting: submitting ?? this.submitting,
      error: clearError ? null : (error ?? this.error),
    );
  }

  /// True when Submit can be pressed.
  bool get isValid {
    if (status == ReportStatusPick.blocked && blockedReason.trim().isEmpty) {
      return false;
    }
    return progressPct >= 0 && progressPct <= 100;
  }
}

class ProgressFormController extends Notifier<ProgressFormState> {
  @override
  ProgressFormState build() => const ProgressFormState();

  void setProgressPct(int pct) =>
      state = state.copyWith(progressPct: pct.clamp(0, 100));

  void setStatus(ReportStatusPick pick) => state = state.copyWith(status: pick);

  void setNotes(String value) => state = state.copyWith(notes: value);

  void setBlockedReason(String value) =>
      state = state.copyWith(blockedReason: value);

  void addPhoto(CapturedPhoto photo) {
    if (state.photos.length >= 10) return;
    state = state.copyWith(photos: [...state.photos, photo]);
  }

  void removePhoto(CapturedPhoto photo) {
    state = state.copyWith(
      photos: state.photos.where((p) => p != photo).toList(),
    );
  }

  void addMaterial(MaterialUsedEntry entry) {
    final existing = state.materials
        .where((m) => m.catalogItemId != entry.catalogItemId)
        .toList()
      ..add(entry);
    state = state.copyWith(materials: existing);
  }

  void removeMaterial(String catalogItemId) {
    state = state.copyWith(
      materials:
          state.materials.where((m) => m.catalogItemId != catalogItemId).toList(),
    );
  }

  /// Submits the report. Captures GPS at this moment (battery-friendly).
  /// Returns true on success (synced or queued), false on validation error.
  Future<bool> submit({
    required String projectId,
    required String zoneId,
  }) async {
    if (!state.isValid) {
      state = state.copyWith(
        error: state.status == ReportStatusPick.blocked
            ? 'Reason is required when status is Blocked.'
            : 'Invalid form state.',
      );
      return false;
    }

    state = state.copyWith(submitting: true, clearError: true);

    final gps = await ref.read(locationServiceProvider).captureCurrent();
    final body = ProgressReportCreate(
      progressPct: state.progressPct,
      status: state.status.zoneStatus,
      notes: state.notes.isEmpty ? null : state.notes,
      materialsUsed: state.materials.isEmpty ? null : state.materials,
      gpsLat: gps?.lat,
      gpsLng: gps?.lng,
    );

    try {
      await ref.read(progressRepositoryProvider).submit(
            projectId: projectId,
            zoneId: zoneId,
            body: body,
            blockedReason: state.status == ReportStatusPick.blocked
                ? state.blockedReason.trim()
                : null,
          );
      state = const ProgressFormState();
      return true;
    } on Exception catch (e) {
      state = state.copyWith(submitting: false, error: e.toString());
      return false;
    }
  }
}

final progressFormControllerProvider =
    NotifierProvider<ProgressFormController, ProgressFormState>(
  ProgressFormController.new,
);
