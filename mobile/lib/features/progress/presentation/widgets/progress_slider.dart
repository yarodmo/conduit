import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class ProgressSlider extends StatelessWidget {
  const ProgressSlider({
    required this.value,
    required this.onChanged,
    super.key,
  });

  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Progress: $value%',
          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            trackHeight: 14,
            thumbShape:
                const RoundSliderThumbShape(enabledThumbRadius: 18),
            overlayShape: const RoundSliderOverlayShape(overlayRadius: 32),
          ),
          child: Slider(
            value: value.toDouble(),
            divisions: 20,
            label: '$value%',
            onChanged: (v) {
              HapticFeedback.selectionClick();
              onChanged(v.round());
            },
          ),
        ),
      ],
    );
  }
}
