// Utility helpers to convert media into mono 16k WAV before upload.
import 'dart:io';

import 'package:ffmpeg_kit_flutter_min_gpl/ffmpeg_kit.dart';

class FfmpegService {
  const FfmpegService();

  /// Convert any media file into a temporary mono 16 kHz WAV file.
  Future<File> convertToMonoWav(File input) async {
    final tempDir = Directory.systemTemp.createTempSync('whisper');
    final output = File('${tempDir.path}/transcoded_${DateTime.now().millisecondsSinceEpoch}.wav');
    final inputPath = _quotePath(input.path);
    final outputPath = _quotePath(output.path);
    final command = '-i $inputPath -ac 1 -ar 16000 -vn -y $outputPath';
    final session = await FFmpegKit.execute(command);
    final returnCode = await session.getReturnCode();
    if (returnCode?.isValueSuccess() != true) {
      throw FFmpegConversionException('FFmpeg failed with code: ${returnCode?.getValue()}');
    }
    if (!output.existsSync()) {
      throw FFmpegConversionException('Failed to create WAV output file');
    }
    return output;
  }

  /// Quote paths with spaces safely for FFmpeg.
  String _quotePath(String path) => '\'' + path.replaceAll("'", "'\\''") + '\'';
}

class FFmpegConversionException implements Exception {
  final String message;
  const FFmpegConversionException(this.message);
  @override
  String toString() => 'FFmpegConversionException: $message';
}
