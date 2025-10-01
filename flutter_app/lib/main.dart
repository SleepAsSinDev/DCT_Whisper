// Entry point initialising Firebase and showing the demo page.
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'pages/transcribe_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const WhisperApp());
}

class WhisperApp extends StatelessWidget {
  const WhisperApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Whisper Proxy Demo',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.deepPurple),
      home: const TranscribePage(),
    );
  }
}
