// Handle authenticated communication with the FastAPI backend via Dio.
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';

const BACKEND_BASE_URL = 'https://api.example-th.dev'; // 🔧TODO

class ApiClient {
  ApiClient({Dio? dio}) : _dio = dio ?? Dio(BaseOptions(baseUrl: BACKEND_BASE_URL));

  final Dio _dio;

  Future<String> uploadTranscription({
    required File file,
    String language = 'th',
    String format = 'text',
    String modelSize = 'large-v3',
    bool wordTimestamps = false,
    bool diarization = false,
  }) async {
    final token = await _fetchToken();
    final formData = FormData.fromMap({
      'language': language,
      'format': format,
      'model_size': modelSize,
      'word_timestamps': wordTimestamps,
      'diarization': diarization,
      'file': await MultipartFile.fromFile(
        file.path,
        filename: file.uri.pathSegments.isNotEmpty ? file.uri.pathSegments.last : 'audio.wav',
      ),
    });
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/v1/transcribe',
        data: formData,
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
      final data = response.data ?? {};
      final taskId = data['task_id'] as String?;
      if (taskId == null) {
        throw ApiException('Missing task_id in response');
      }
      return taskId;
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Stream<Map<String, dynamic>> pollStatus(
    String taskId, {
    Duration interval = const Duration(seconds: 3),
  }) async* {
    while (true) {
      final payload = await fetchStatus(taskId);
      yield payload;
      if (payload['status'] == 'completed' || payload['status'] == 'failed') {
        break;
      }
      await Future.delayed(interval);
    }
  }

  Future<Map<String, dynamic>> fetchStatus(String taskId) async {
    final token = await _fetchToken();
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/v1/status/$taskId',
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
      return Map<String, dynamic>.from(response.data ?? <String, dynamic>{});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<Map<String, dynamic>> fetchUsage() async {
    final token = await _fetchToken();
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/v1/me/usage',
        options: Options(headers: {'Authorization': 'Bearer $token'}),
      );
      return Map<String, dynamic>.from(response.data ?? <String, dynamic>{});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<String> _fetchToken() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      throw const ApiException('User not signed in');
    }
    final token = await user.getIdToken();
    if (token == null || token.isEmpty) {
      throw const ApiException('Failed to obtain Firebase ID token');
    }
    return token;
  }
}

class ApiException implements Exception {
  const ApiException(this.message, {this.code});

  factory ApiException.fromDio(DioException error) {
    final statusCode = error.response?.statusCode;
    final detail = error.response?.data is Map
        ? (error.response?.data['detail'] ?? error.message)
        : error.message;
    return ApiException(detail?.toString() ?? 'Network error', code: statusCode);
  }

  final String message;
  final int? code;

  @override
  String toString() => 'ApiException(code: $code, message: $message)';
}
