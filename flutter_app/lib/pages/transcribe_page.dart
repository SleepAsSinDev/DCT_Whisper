// Simple demo page to pick audio, convert and send to the backend.
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/ffmpeg_service.dart';

class TranscribePage extends StatefulWidget {
  const TranscribePage({super.key});

  @override
  State<TranscribePage> createState() => _TranscribePageState();
}

class _TranscribePageState extends State<TranscribePage> {
  final _logs = <String>[];
  final _ffmpeg = const FfmpegService();
  final _api = ApiClient();

  bool _busy = false;
  String? _transcript;

  void _addLog(String message) {
    setState(() {
      _logs.insert(0, message);
    });
  }

  Future<void> _pickConvertAndUpload() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _transcript = null;
      _logs.clear();
    });
    try {
      _addLog('Selecting file...');
      final result = await FilePicker.platform.pickFiles();
      if (result == null || result.files.single.path == null) {
        _addLog('No file selected');
        return;
      }
      final input = File(result.files.single.path!);
      _addLog('Converting to mono 16k WAV...');
      final converted = await _ffmpeg.convertToMonoWav(input);
      _addLog('Uploading to backend...');
      final taskId = await _api.uploadTranscription(file: converted);
      _addLog('Task created: $taskId');
      _addLog('Polling status...');
      await for (final status in _api.pollStatus(taskId)) {
        _addLog('Status: ${status['status']}');
        if (status['status'] == 'completed') {
          _transcript = status['text']?.toString();
          break;
        }
        if (status['status'] == 'failed') {
          _addLog('Transcription failed');
          break;
        }
      }
      final usage = await _api.fetchUsage();
      _addLog('Usage today: ${usage['minutes_today']} min');
    } on Exception catch (error) {
      _addLog('Error: $error');
    } finally {
      setState(() {
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Whisper Proxy Demo')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ElevatedButton.icon(
              icon: const Icon(Icons.audiotrack),
              label: Text(_busy ? 'Processing...' : 'Pick & Transcribe'),
              onPressed: _busy ? null : _pickConvertAndUpload,
            ),
            const SizedBox(height: 16),
            if (_transcript != null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    _transcript!,
                    style: const TextStyle(fontSize: 16),
                  ),
                ),
              ),
            const SizedBox(height: 16),
            const Text('Activity Log'),
            const SizedBox(height: 8),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey.shade300),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: ListView.builder(
                  reverse: true,
                  itemCount: _logs.length,
                  itemBuilder: (context, index) => ListTile(
                    dense: true,
                    title: Text(_logs[index]),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
