import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:conduit_mobile/features/ai_assistant/domain/ai_response.dart';
import 'package:conduit_mobile/features/ai_assistant/providers.dart';

/// Bottom sheet with voice + text query to Conduit AI.
///
/// Shows cached badge (📶 offline icon) vs live (⚡) indicator on response.
/// Uses AutoDispose provider — fresh state on each open.
class AiAssistantSheet extends ConsumerStatefulWidget {
  const AiAssistantSheet({this.projectId, super.key});

  final String? projectId;

  static Future<void> show(BuildContext context, {String? projectId}) =>
      showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        useSafeArea: true,
        builder: (_) => AiAssistantSheet(projectId: projectId),
      );

  @override
  ConsumerState<AiAssistantSheet> createState() => _AiAssistantSheetState();
}

class _AiAssistantSheetState extends ConsumerState<AiAssistantSheet> {
  final _textCtrl = TextEditingController();
  final _speech = SpeechToText();
  bool _speechAvailable = false;
  bool _listening = false;

  @override
  void initState() {
    super.initState();
    // Set project context before first build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        ref
            .read(aiQueryControllerProvider.notifier)
            .setProjectId(widget.projectId);
      }
    });
    _initSpeech();
  }

  Future<void> _initSpeech() async {
    final available = await _speech.initialize(
      onError: (_) => setState(() => _listening = false),
      onStatus: (status) {
        if (status == SpeechToText.doneStatus ||
            status == SpeechToText.notListeningStatus) {
          setState(() => _listening = false);
        }
      },
    );
    if (mounted) setState(() => _speechAvailable = available);
  }

  Future<void> _toggleListening() async {
    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      return;
    }
    HapticFeedback.mediumImpact();
    setState(() => _listening = true);
    await _speech.listen(
      onResult: (result) {
        if (result.finalResult) {
          _textCtrl.text = result.recognizedWords;
          ref
              .read(aiQueryControllerProvider.notifier)
              .setQuery(result.recognizedWords);
          setState(() => _listening = false);
        }
      },
      listenOptions: SpeechListenOptions(
        listenMode: ListenMode.confirmation,
      ),
    );
  }

  @override
  void dispose() {
    _textCtrl.dispose();
    _speech.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(aiQueryControllerProvider);

    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ── Header ──────────────────────────────────────
            Row(
              children: [
                const Icon(Icons.auto_awesome, size: 22),
                const SizedBox(width: 8),
                const Text(
                  'Ask Conduit AI',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
            // ── Response card ───────────────────────────────
            if (state.response != null) ...[
              const SizedBox(height: 12),
              _ResponseCard(state.response!),
            ],
            const SizedBox(height: 16),
            // ── Query input ─────────────────────────────────
            TextField(
              controller: _textCtrl,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.send,
              onChanged: (v) =>
                  ref.read(aiQueryControllerProvider.notifier).setQuery(v),
              onSubmitted: (_) =>
                  ref.read(aiQueryControllerProvider.notifier).submit(),
              decoration: InputDecoration(
                hintText: 'Ask anything about this project…',
                border: const OutlineInputBorder(),
                suffixIcon: _speechAvailable
                    ? IconButton(
                        icon: Icon(
                          _listening ? Icons.mic : Icons.mic_none,
                          color: _listening
                              ? Theme.of(context).colorScheme.error
                              : null,
                        ),
                        tooltip: _listening ? 'Stop listening' : 'Voice input',
                        onPressed: _toggleListening,
                      )
                    : null,
              ),
            ),
            const SizedBox(height: 12),
            // ── Send button ─────────────────────────────────
            FilledButton.icon(
              onPressed: state.loading || state.query.trim().isEmpty
                  ? null
                  : () {
                      HapticFeedback.lightImpact();
                      ref.read(aiQueryControllerProvider.notifier).submit();
                    },
              icon: state.loading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.send),
              label: Text(state.loading ? 'Asking…' : 'Ask'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ResponseCard extends StatelessWidget {
  const _ResponseCard(this.response);

  final AiResponse response;

  @override
  Widget build(BuildContext context) {
    final color = response.fromCache
        ? Theme.of(context).colorScheme.secondary
        : Theme.of(context).colorScheme.primary;

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  response.fromCache ? Icons.offline_pin : Icons.bolt,
                  size: 14,
                  color: color,
                ),
                const SizedBox(width: 4),
                Text(
                  response.fromCache ? 'Cached answer' : 'Live answer',
                  style: Theme.of(context)
                      .textTheme
                      .labelSmall
                      ?.copyWith(color: color),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SelectableText(
              response.answer,
              style: const TextStyle(fontSize: 15),
            ),
          ],
        ),
      ),
    );
  }
}
