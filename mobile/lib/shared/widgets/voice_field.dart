import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// TextField with an integrated mic button for speech-to-text input.
///
/// Voice transcript appends to (or replaces) the field content and fires
/// [onChanged] — same contract as a plain TextField.
class VoiceField extends StatefulWidget {
  const VoiceField({
    required this.label,
    required this.hint,
    required this.value,
    required this.onChanged,
    this.prefixIcon,
    this.maxLines = 3,
    this.maxLength,
    super.key,
  });

  final String label;
  final String hint;
  final String value;
  final ValueChanged<String> onChanged;
  final Widget? prefixIcon;
  final int maxLines;
  final int? maxLength;

  @override
  State<VoiceField> createState() => _VoiceFieldState();
}

class _VoiceFieldState extends State<VoiceField> {
  late TextEditingController _ctrl;
  final _speech = SpeechToText();
  bool _speechAvailable = false;
  bool _listening = false;

  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: widget.value)
      ..selection = TextSelection.collapsed(offset: widget.value.length);
    _speech
        .initialize(
          onError: (_) => setState(() => _listening = false),
          onStatus: (s) {
            if (s == SpeechToText.doneStatus ||
                s == SpeechToText.notListeningStatus) {
              setState(() => _listening = false);
            }
          },
        )
        .then((v) => setState(() => _speechAvailable = v));
  }

  @override
  void didUpdateWidget(VoiceField old) {
    super.didUpdateWidget(old);
    // Sync external value when not actively listening
    if (!_listening && widget.value != _ctrl.text) {
      _ctrl
        ..text = widget.value
        ..selection =
            TextSelection.collapsed(offset: widget.value.length);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _speech.cancel();
    super.dispose();
  }

  Future<void> _toggle() async {
    if (_listening) {
      await _speech.stop();
      setState(() => _listening = false);
      return;
    }
    HapticFeedback.mediumImpact();
    setState(() => _listening = true);
    await _speech.listen(
      onResult: (r) {
        if (r.finalResult) {
          setState(() => _listening = false);
          _ctrl.text = r.recognizedWords;
          _ctrl.selection = TextSelection.collapsed(
            offset: r.recognizedWords.length,
          );
          widget.onChanged(r.recognizedWords);
        }
      },
      listenOptions: SpeechListenOptions(
        listenMode: ListenMode.confirmation,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _ctrl,
      maxLines: widget.maxLines,
      maxLength: widget.maxLength,
      onChanged: widget.onChanged,
      decoration: InputDecoration(
        labelText: widget.label,
        hintText: widget.hint,
        prefixIcon: widget.prefixIcon,
        suffixIcon: _speechAvailable
            ? IconButton(
                icon: Icon(
                  _listening ? Icons.mic : Icons.mic_none,
                  color: _listening
                      ? Theme.of(context).colorScheme.error
                      : null,
                ),
                tooltip: _listening ? 'Stop' : 'Voice input',
                onPressed: _toggle,
              )
            : null,
      ),
    );
  }
}
