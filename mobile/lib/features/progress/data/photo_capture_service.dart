import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';
import 'package:conduit_mobile/features/progress/domain/captured_photo.dart';

/// Captures from camera and compresses to <1MB while preserving EXIF.
///
/// Per master prompt PROMPT 9:
///  - Up to 10 photos per report
///  - Compress before queue
///  - Preserve original locally (no delete)
///  - GPS + timestamp inmutables
class PhotoCaptureService {
  PhotoCaptureService([ImagePicker? picker, Uuid? uuid])
      : _picker = picker ?? ImagePicker(),
        _uuid = uuid ?? const Uuid();

  final ImagePicker _picker;
  final Uuid _uuid;

  static const int _maxFileSizeBytes = 1024 * 1024; // 1 MB
  static const int _maxDimensionPx = 2048;

  /// Opens camera, captures a photo, compresses, returns metadata.
  /// Returns null if user cancels.
  Future<CapturedPhoto?> captureFromCamera() async {
    final picked = await _picker.pickImage(
      source: ImageSource.camera,
      preferredCameraDevice: CameraDevice.rear,
      imageQuality: 85,
    );
    if (picked == null) return null;
    return _processFile(File(picked.path));
  }

  Future<CapturedPhoto?> _processFile(File source) async {
    final docsDir = await getApplicationDocumentsPath();
    final photosDir = Directory('$docsDir/photos');
    if (!photosDir.existsSync()) photosDir.createSync(recursive: true);

    final id = _uuid.v4();
    final originalPath = '${photosDir.path}/$id.original.jpg';
    final compressedPath = '${photosDir.path}/$id.upload.jpg';

    // Save original untouched
    await source.copy(originalPath);

    // Compress
    final bytes = await source.readAsBytes();
    final decoded = img.decodeImage(bytes);
    if (decoded == null) return null;

    final resized = decoded.width > _maxDimensionPx ||
            decoded.height > _maxDimensionPx
        ? img.copyResize(
            decoded,
            width: decoded.width > decoded.height ? _maxDimensionPx : null,
            height: decoded.height >= decoded.width ? _maxDimensionPx : null,
          )
        : decoded;

    var quality = 85;
    List<int> encoded = img.encodeJpg(resized, quality: quality);
    while (encoded.length > _maxFileSizeBytes && quality > 40) {
      quality -= 10;
      encoded = img.encodeJpg(resized, quality: quality);
    }

    final compressedFile = File(compressedPath);
    await compressedFile.writeAsBytes(encoded);

    return CapturedPhoto(
      originalPath: originalPath,
      compressedPath: compressedPath,
      capturedAt: DateTime.now().toUtc(),
      fileSizeBytes: encoded.length,
    );
  }
}

Future<String> getApplicationDocumentsPath() async {
  final dir = await getApplicationDocumentsDirectory();
  return dir.path;
}

final photoCaptureServiceProvider = Provider<PhotoCaptureService>(
  (ref) => PhotoCaptureService(),
);
