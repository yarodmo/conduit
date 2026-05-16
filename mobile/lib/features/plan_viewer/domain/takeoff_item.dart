import 'package:json_annotation/json_annotation.dart';

part 'takeoff_item.g.dart';

/// Cached read-only takeoff item shown in the zone detail bottom sheet.
/// Mirrors backend TakeoffItem schema (M5).
@JsonSerializable(fieldRename: FieldRename.snake)
class TakeoffItem {
  const TakeoffItem({
    required this.id,
    required this.type,
    required this.quantity,
    required this.unit,
    required this.specification,
    this.tag,
    this.system,
    this.cfmOrGpm,
    this.confidence,
  });

  factory TakeoffItem.fromJson(Map<String, dynamic> json) =>
      _$TakeoffItemFromJson(json);

  final String id;
  final String type;
  final String? tag;
  final num quantity;
  final String unit;
  final String specification;
  final String? system;
  final num? cfmOrGpm;
  final int? confidence;

  Map<String, dynamic> toJson() => _$TakeoffItemToJson(this);

  String get displayQty {
    final qStr = quantity.toString().replaceAll(RegExp(r'\.0+$'), '');
    return '$qStr $unit';
  }
}
