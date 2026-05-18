import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:conduit_mobile/features/ai_assistant/data/ai_assistant_repository.dart';
import 'package:conduit_mobile/features/ai_assistant/domain/ai_response.dart';

class AiQueryState {
  const AiQueryState({
    this.query = '',
    this.response,
    this.loading = false,
    this.projectId,
  });

  final String query;
  final AiResponse? response;
  final bool loading;
  final String? projectId;

  AiQueryState copyWith({
    String? query,
    AiResponse? response,
    bool? loading,
    String? projectId,
    bool clearResponse = false,
  }) =>
      AiQueryState(
        query: query ?? this.query,
        response: clearResponse ? null : (response ?? this.response),
        loading: loading ?? this.loading,
        projectId: projectId ?? this.projectId,
      );
}

class AiQueryController extends AutoDisposeNotifier<AiQueryState> {
  @override
  AiQueryState build() => const AiQueryState();

  void setQuery(String q) => state = state.copyWith(query: q);

  void setProjectId(String? id) => state = state.copyWith(projectId: id);

  Future<void> submit() async {
    if (state.query.trim().isEmpty) return;
    state = state.copyWith(loading: true, clearResponse: true);
    final response = await ref.read(aiAssistantRepositoryProvider).ask(
          state.query.trim(),
          projectId: state.projectId,
        );
    state = state.copyWith(loading: false, response: response);
  }
}

/// AutoDispose so each sheet open starts with fresh state.
final aiQueryControllerProvider =
    NotifierProvider.autoDispose<AiQueryController, AiQueryState>(
  AiQueryController.new,
);
