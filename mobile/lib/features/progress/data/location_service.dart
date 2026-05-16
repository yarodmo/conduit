import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

/// One-shot GPS capture (per master prompt PROMPT 9: no continuous tracking
/// — battery preservation).
///
/// Returns null on permission denial or low accuracy.
class LocationService {
  const LocationService();

  Future<({double lat, double lng})?> captureCurrent({
    Duration timeout = const Duration(seconds: 12),
  }) async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return null;

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
    }

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: timeout,
        ),
      );
      return (lat: position.latitude, lng: position.longitude);
    } on Exception {
      return null;
    }
  }
}

final locationServiceProvider = Provider<LocationService>(
  (_) => const LocationService(),
);
