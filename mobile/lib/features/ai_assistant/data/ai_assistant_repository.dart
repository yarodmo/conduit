import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_ce/hive.dart';
import 'package:conduit_mobile/core/network/dio_client.dart';
import 'package:conduit_mobile/core/storage/hive_setup.dart';
import 'package:conduit_mobile/features/ai_assistant/data/ai_assistant_api.dart';
import 'package:conduit_mobile/features/ai_assistant/domain/ai_response.dart';

/// Cache-first AI query handler.
///
/// On ask:
///  1. Hash query+projectId → check Hive ai_cache_box
///  2. Cache hit  → return immediately (works offline)
///  3. Cache miss → call /assistant/ask, return live answer
///
/// On preload:
///  Calls /assistant/cache/generate which returns top-20 Q&A pairs
///  for the project; stores each in ai_cache_box for offline access.
class AiAssistantRepository {
  AiAssistantRepository(this._api, this._cacheBox);

  final AiAssistantApi _api;
  final Box<dynamic> _cacheBox;

  Future<AiResponse> ask(String query, {String? projectId}) async {
    final key = _cacheKey(projectId, query);
    final cached = _cacheBox.get(key) as String?;
    if (cached != null) {
      return AiResponse(answer: cached, fromCache: true);
    }

    try {
      final response = await _api.ask(
        AiAskRequest(query: query, projectId: projectId),
      );
      return AiResponse(answer: response.answer, fromCache: false);
    } on DioException {
      return const AiResponse(
        answer:
            'Unable to reach Conduit AI. Check your connection and try again.',
        fromCache: false,
      );
    }
  }

  Future<void> preloadCache(String projectId) async {
    try {
      final response =
          await _api.generateCache(AiCacheRequest(projectId: projectId));
      for (final entry in response.entries) {
        final key = _cacheKey(projectId, entry.query);
        await _cacheBox.put(key, entry.answer);
      }
    } on DioException {
      // Non-fatal — offline or server unavailable; will retry next assignment
    }
  }

  /// Stable key derived from (projectId, normalized query).
  /// base64url-encoded UTF-8 — handles any unicode, no length cap needed.
  String _cacheKey(String? projectId, String query) {
    final raw = '${projectId ?? ""}|${query.toLowerCase().trim()}';
    return base64Url.encode(utf8.encode(raw));
  }
}

final aiAssistantApiProvider = Provider<AiAssistantApi>(
  (ref) => AiAssistantApi(ref.watch(dioProvider)),
);

final aiAssistantRepositoryProvider = Provider<AiAssistantRepository>(
  (ref) => AiAssistantRepository(
    ref.watch(aiAssistantApiProvider),
    Hive.box<dynamic>(HiveSetup.aiCacheBox),
  ),
);
