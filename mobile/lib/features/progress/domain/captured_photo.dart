/// A photo captured during a progress report — kept in memory until submit.
///
/// The compressed file is what gets uploaded; original preserved locally
/// (master prompt PROMPT 9: NUNCA borrar original).
class CapturedPhoto {
  const CapturedPhoto({
    required this.originalPath,
    required this.compressedPath,
    required this.capturedAt,
    required this.fileSizeBytes,
    this.caption,
  });

  final String originalPath;
  final String compressedPath;
  final DateTime capturedAt;
  final int fileSizeBytes;
  final String? caption;

  CapturedPhoto withCaption(String? newCaption) => CapturedPhoto(
        originalPath: originalPath,
        compressedPath: compressedPath,
        capturedAt: capturedAt,
        fileSizeBytes: fileSizeBytes,
        caption: newCaption,
      );
}
