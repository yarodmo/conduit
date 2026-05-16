import 'dart:io';

import 'package:flutter/material.dart';
import 'package:conduit_mobile/features/progress/domain/captured_photo.dart';

class PhotoGrid extends StatelessWidget {
  const PhotoGrid({
    required this.photos,
    required this.onAdd,
    required this.onRemove,
    super.key,
  });

  static const int maxPhotos = 10;

  final List<CapturedPhoto> photos;
  final VoidCallback onAdd;
  final void Function(CapturedPhoto) onRemove;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Text(
              'Photos',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
            ),
            const Spacer(),
            Text(
              '${photos.length} / $maxPhotos',
              style: TextStyle(color: Theme.of(context).hintColor),
            ),
          ],
        ),
        const SizedBox(height: 8),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 3,
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
          ),
          itemCount: photos.length + (photos.length < maxPhotos ? 1 : 0),
          itemBuilder: (context, index) {
            if (index >= photos.length) {
              return _AddPhotoTile(onTap: onAdd);
            }
            return _PhotoTile(
              photo: photos[index],
              onRemove: () => onRemove(photos[index]),
            );
          },
        ),
      ],
    );
  }
}

class _AddPhotoTile extends StatelessWidget {
  const _AddPhotoTile({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border.all(
            color: Theme.of(context).colorScheme.primary,
            style: BorderStyle.solid,
            width: 2,
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.add_a_photo_outlined,
              size: 32,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 4),
            Text(
              'Add',
              style: TextStyle(
                color: Theme.of(context).colorScheme.primary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PhotoTile extends StatelessWidget {
  const _PhotoTile({required this.photo, required this.onRemove});
  final CapturedPhoto photo;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: Image.file(File(photo.compressedPath), fit: BoxFit.cover),
        ),
        Positioned(
          top: 2,
          right: 2,
          child: Material(
            color: Colors.black54,
            shape: const CircleBorder(),
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: onRemove,
              child: const Padding(
                padding: EdgeInsets.all(4),
                child:
                    Icon(Icons.close, color: Colors.white, size: 18),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
