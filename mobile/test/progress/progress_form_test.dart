import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:conduit_mobile/features/progress/domain/captured_photo.dart';
import 'package:conduit_mobile/features/progress/domain/progress_report.dart';
import 'package:conduit_mobile/features/progress/providers.dart';

void main() {
  late ProviderContainer container;

  setUp(() {
    container = ProviderContainer();
  });

  tearDown(() => container.dispose());

  ProgressFormController get ctrl =>
      container.read(progressFormControllerProvider.notifier);

  ProgressFormState get state =>
      container.read(progressFormControllerProvider);

  test('default state: 0% on track, valid by default', () {
    expect(state.progressPct, 0);
    expect(state.status, ReportStatusPick.onTrack);
    expect(state.isValid, isTrue);
  });

  test('setProgressPct clamps to 0-100', () {
    ctrl.setProgressPct(150);
    expect(state.progressPct, 100);
    ctrl.setProgressPct(-10);
    expect(state.progressPct, 0);
    ctrl.setProgressPct(55);
    expect(state.progressPct, 55);
  });

  test('isValid false when Blocked without reason', () {
    ctrl.setStatus(ReportStatusPick.blocked);
    expect(state.isValid, isFalse);
    ctrl.setBlockedReason('Pipe conflict at column line C');
    expect(state.isValid, isTrue);
  });

  test('isValid false when Blocked with only whitespace reason', () {
    ctrl.setStatus(ReportStatusPick.blocked);
    ctrl.setBlockedReason('   ');
    expect(state.isValid, isFalse);
  });

  test('photo grid caps at 10', () {
    for (var i = 0; i < 12; i++) {
      ctrl.addPhoto(_fakePhoto(i));
    }
    expect(state.photos.length, 10);
  });

  test('removePhoto removes the exact instance', () {
    final p = _fakePhoto(1);
    ctrl.addPhoto(p);
    ctrl.addPhoto(_fakePhoto(2));
    ctrl.removePhoto(p);
    expect(state.photos.length, 1);
  });

  test('addMaterial replaces existing entry for same catalog item', () {
    ctrl.addMaterial(const MaterialUsedEntry(catalogItemId: 'item-1', qty: 2));
    ctrl.addMaterial(const MaterialUsedEntry(catalogItemId: 'item-1', qty: 5));
    expect(state.materials.length, 1);
    expect(state.materials.first.qty, 5);
  });

  test('removeMaterial removes by catalog id', () {
    ctrl.addMaterial(const MaterialUsedEntry(catalogItemId: 'a', qty: 1));
    ctrl.addMaterial(const MaterialUsedEntry(catalogItemId: 'b', qty: 1));
    ctrl.removeMaterial('a');
    expect(state.materials.length, 1);
    expect(state.materials.first.catalogItemId, 'b');
  });

  test('status zoneStatus mapping', () {
    expect(ReportStatusPick.onTrack.zoneStatus, 'IN_PROGRESS');
    expect(ReportStatusPick.issues.zoneStatus, 'IN_PROGRESS');
    expect(ReportStatusPick.blocked.zoneStatus, 'BLOCKED');
  });
}

CapturedPhoto _fakePhoto(int idx) => CapturedPhoto(
      originalPath: '/tmp/$idx.orig.jpg',
      compressedPath: '/tmp/$idx.up.jpg',
      capturedAt: DateTime.now(),
      fileSizeBytes: 100_000,
    );
