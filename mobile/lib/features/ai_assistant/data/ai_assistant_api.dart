import 'package:dio/dio.dart';
import 'package:json_annotation/json_annotation.dart';
import 'package:retrofit/retrofit.dart';

part 'ai_assistant_api.g.dart';

@RestApi()
abstract class AiAssistantApi {
  factory AiAssistantApi(Dio dio, {String baseUrl}) = _AiAssistantApi;

  @POST('/api/v1/assistant/ask')
  Future<AiAskResponse> ask(@Body() AiAskRequest body);

  @POST('/api/v1/assistant/cache/generate')
  Future<AiCacheGenerateResponse> generateCache(
    @Body() AiCacheRequest body,
  );
}

@JsonSerializable(fieldRename: FieldRename.snake, includeIfNull: false)
class AiAskRequest {
  const AiAskRequest({required this.query, this.projectId});

  factory AiAskRequest.fromJson(Map<String, dynamic> json) =>
      _$AiAskRequestFromJson(json);

  final String query;
  final String? projectId;

  Map<String, dynamic> toJson() => _$AiAskRequestToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class AiAskResponse {
  const AiAskResponse({required this.answer, required this.cached});

  factory AiAskResponse.fromJson(Map<String, dynamic> json) =>
      _$AiAskResponseFromJson(json);

  final String answer;
  final bool cached;

  Map<String, dynamic> toJson() => _$AiAskResponseToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class AiCacheRequest {
  const AiCacheRequest({required this.projectId});

  factory AiCacheRequest.fromJson(Map<String, dynamic> json) =>
      _$AiCacheRequestFromJson(json);

  final String projectId;

  Map<String, dynamic> toJson() => _$AiCacheRequestToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class AiCacheEntry {
  const AiCacheEntry({required this.query, required this.answer});

  factory AiCacheEntry.fromJson(Map<String, dynamic> json) =>
      _$AiCacheEntryFromJson(json);

  final String query;
  final String answer;

  Map<String, dynamic> toJson() => _$AiCacheEntryToJson(this);
}

@JsonSerializable(fieldRename: FieldRename.snake)
class AiCacheGenerateResponse {
  const AiCacheGenerateResponse({required this.entries});

  factory AiCacheGenerateResponse.fromJson(Map<String, dynamic> json) =>
      _$AiCacheGenerateResponseFromJson(json);

  final List<AiCacheEntry> entries;

  Map<String, dynamic> toJson() => _$AiCacheGenerateResponseToJson(this);
}
