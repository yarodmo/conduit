import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum ConnectivityState { online, offline }

/// Listens to connectivity_plus and exposes a Riverpod stream.
///
/// Used by:
///  - SyncEngine (to trigger queue drain on reconnect)
///  - OfflineBanner (to show persistent indicator)
final connectivityProvider = StreamProvider<ConnectivityState>((ref) {
  final connectivity = Connectivity();
  return connectivity.onConnectivityChanged.map(_mapResult);
});

ConnectivityState _mapResult(List<ConnectivityResult> result) {
  final offline = result.isEmpty ||
      result.every((r) => r == ConnectivityResult.none);
  return offline ? ConnectivityState.offline : ConnectivityState.online;
}

/// Convenience boolean — true when device has any active connection.
final isOnlineProvider = Provider<bool>((ref) {
  final state = ref.watch(connectivityProvider).asData?.value;
  return state == ConnectivityState.online;
});
