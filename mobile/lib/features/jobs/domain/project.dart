import 'package:json_annotation/json_annotation.dart';

part 'project.g.dart';

enum ProjectComplexity {
  @JsonValue('simple')
  simple,
  @JsonValue('standard')
  standard,
  @JsonValue('complex')
  complex,
}

@JsonSerializable(fieldRename: FieldRename.snake)
class Project {
  const Project({
    required this.id,
    required this.name,
    required this.complexity,
    required this.isActive,
    required this.createdAt,
    this.type,
    this.address,
    this.city,
    this.state,
    this.generalContractor,
  });

  factory Project.fromJson(Map<String, dynamic> json) =>
      _$ProjectFromJson(json);

  final String id;
  final String name;
  final String? type;
  final ProjectComplexity complexity;
  final String? address;
  final String? city;
  final String? state;
  final String? generalContractor;
  final bool isActive;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => _$ProjectToJson(this);

  String get locationLabel {
    final parts = [city, state].whereType<String>().toList();
    return parts.isEmpty ? '—' : parts.join(', ');
  }
}
