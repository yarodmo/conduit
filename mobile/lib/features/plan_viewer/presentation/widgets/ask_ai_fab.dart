import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Floating action button that opens the AI assistant sheet.
/// Voice input wiring lives in Turn 5 (assistant integration).
class AskAiFab extends StatelessWidget {
  const AskAiFab({required this.onPressed, super.key});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton.extended(
      onPressed: () {
        HapticFeedback.mediumImpact();
        onPressed();
      },
      icon: const Icon(Icons.auto_awesome),
      label: const Text('Ask AI'),
    );
  }
}
