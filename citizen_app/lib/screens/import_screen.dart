import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:image_picker/image_picker.dart';
import 'package:latlong2/latlong.dart';

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';

/// How the clip gets its location. Never the phone's current position by default:
/// an old clip stamped with where the phone is now would put potholes on the wrong road.
enum _Where { gpx, pin, none }

class ImportScreen extends StatefulWidget {
  const ImportScreen({super.key});
  @override
  State<ImportScreen> createState() => _ImportScreenState();
}

class _ImportScreenState extends State<ImportScreen> {
  XFile? _video;
  List<int>? _gpx;
  String? _gpxName;
  _Where _where = _Where.none;
  LatLng? _pin;
  bool _sending = false;
  double _progress = 0;
  String? _status;
  Map<String, dynamic>? _result;

  Future<void> _pickVideo() async {
    final v = await ImagePicker().pickVideo(source: ImageSource.gallery);
    if (v != null) setState(() => (_video = v, _result = null));
  }

  Future<void> _pickGpx() async {
    try {
      final files = await FilePicker.pickFiles(dialogTitle: 'Choose the GPX track for this clip');
      if (files.isEmpty) return;
      final f = files.first;
      if (!f.name.toLowerCase().endsWith('.gpx')) {
        if (mounted) toast(context, 'That is not a .gpx file.', error: true);
        return;
      }
      final bytes = await f.xFile.readAsBytes();
      setState(() => (_gpx = bytes, _gpxName = f.name, _where = _Where.gpx));
    } catch (_) {
      if (mounted) toast(context, 'Could not open the file picker.', error: true);
    }
  }

  bool get _ready => _video != null && !_sending && (_where != _Where.pin || _pin != null) && (_where != _Where.gpx || _gpx != null);

  Future<void> _upload() async {
    if (!_ready) return;
    setState(() => (_sending = true, _progress = 0.05, _status = 'Uploading the clip...'));
    try {
      final r = await api.importVideo(
        _video!,
        gpx: _where == _Where.gpx ? _gpx : null,
        gpxName: _gpxName,
        lat: _where == _Where.pin ? _pin!.latitude : null,
        lon: _where == _Where.pin ? _pin!.longitude : null,
        onProgress: (p) => mounted ? setState(() => _progress = p * 0.4) : null,
      );
      final job = r['job_id'] as String?;
      if (job == null) {
        setState(() => (_result = r, _sending = false, _status = null));
        return;
      }
      setState(() => _status = 'Scanning the video frame by frame...');
      while (mounted) {
        await Future<void>.delayed(const Duration(seconds: 3));
        final j = await api.jobStatus(job);
        final p = ((j['progress'] ?? 0) as num).toDouble();
        if (mounted) setState(() => _progress = 0.4 + 0.6 * p);
        if (j['status'] == 'done') {
          if (mounted) setState(() => (_result = Map<String, dynamic>.from(j['inspection'] ?? {}), _sending = false));
          refreshTick.value++;
          return;
        }
        if (j['status'] == 'error') throw ApiException('The video could not be processed: ${j['error'] ?? 'unknown error'}');
      }
    } catch (e) {
      if (mounted) {
        setState(() => (_sending = false, _status = null));
        toast(context, '$e', error: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final summary = _result?['summary'] as Map<String, dynamic>?;
    return Scaffold(
      appBar: AppBar(title: const Text('Import dashcam video'), backgroundColor: c.bg),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 40),
        children: [
          Text('Upload a clip you recorded earlier. Every pothole in it is tracked once and added to the city map.',
              style: T.sub(context)),
          const SectionLabel('1. The video'),
          CardBox(
            child: Row(children: [
              IconBadge(CupertinoIcons.film_fill, _video == null ? AppColors.blue : AppColors.green, size: 42),
              const SizedBox(width: 12),
              Expanded(
                child: Text(_video == null ? 'No clip chosen' : _video!.name,
                    maxLines: 2, overflow: TextOverflow.ellipsis, style: T.headline(context)),
              ),
              CupertinoButton(onPressed: _sending ? null : _pickVideo, child: Text(_video == null ? 'Choose' : 'Change')),
            ]),
          ),
          const SectionLabel('2. Where was it recorded?'),
          Text('An old clip must not be stamped with where your phone is now, so pick one of these.', style: T.sub(context)),
          const SizedBox(height: 10),
          _option(_Where.gpx, CupertinoIcons.map_fill, 'Use a GPX track',
              _gpxName ?? 'Most accurate. Each frame gets its own position.', trailing: CupertinoButton(
                  padding: EdgeInsets.zero, onPressed: _sending ? null : _pickGpx, child: Text(_gpx == null ? 'Choose' : 'Change'))),
          _option(_Where.pin, CupertinoIcons.location_solid, 'Drop a pin where you recorded it',
              _pin == null ? 'Tap the map below.' : '${_pin!.latitude.toStringAsFixed(5)}, ${_pin!.longitude.toStringAsFixed(5)}'),
          if (_where == _Where.pin)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: SizedBox(
                  height: 200,
                  child: FlutterMap(
                    options: MapOptions(
                      initialCenter: locator.spot != null
                          ? LatLng(locator.spot!.lat, locator.spot!.lon)
                          : const LatLng(12.9716, 77.5946),
                      initialZoom: 14,
                      onTap: (_, p) => setState(() => _pin = p),
                    ),
                    children: [
                      const MapTiles(),
                      if (_pin != null)
                        MarkerLayer(markers: [Marker(point: _pin!, width: 32, height: 32, child: const MapPin(size: 32))]),
                      const MapCredit(),
                    ],
                  ),
                ),
              ),
            ),
          _option(_Where.none, CupertinoIcons.location_slash_fill, 'Send without a location',
              'Potholes are still detected, but marked as location unknown.'),
          const SizedBox(height: 20),
          if (_status != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(value: _progress, minHeight: 6, backgroundColor: c.fill, color: AppColors.blue),
            ),
            const SizedBox(height: 8),
            Text(_status!, style: T.sub(context)),
            const SizedBox(height: 16),
          ],
          if (_result != null)
            CardBox(
              child: Row(children: [
                const IconBadge(CupertinoIcons.checkmark_seal_fill, AppColors.green, size: 42),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('Video processed', style: T.headline(context)),
                    const SizedBox(height: 2),
                    Text(
                      summary == null
                          ? 'Thanks. The defects are now on the city map.'
                          : 'Unique defects found: ${summary['unique_tracks'] ?? summary['total'] ?? 0}. '
                              'Frames scanned: ${summary['frames_processed'] ?? '?'}.',
                      style: T.sub(context),
                    ),
                  ]),
                ),
              ]),
            ),
          const SizedBox(height: 16),
          Pressable(
            onTap: _ready ? _upload : null,
            child: Container(
              height: 56,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                  color: _ready ? AppColors.blue : c.fill, borderRadius: BorderRadius.circular(18)),
              child: _sending
                  ? const CupertinoActivityIndicator(color: Colors.white)
                  : Text('Upload and scan',
                      style: TextStyle(
                          color: _ready ? Colors.white : c.textTertiary, fontSize: 17, fontWeight: FontWeight.w600)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _option(_Where w, IconData icon, String title, String detail, {Widget? trailing}) {
    final sel = _where == w;
    final c = AppColors.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Pressable(
        onTap: _sending ? null : () => setState(() => _where = w),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: c.card,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: sel ? AppColors.blue : Colors.transparent, width: 2),
          ),
          child: Row(children: [
            Icon(sel ? CupertinoIcons.largecircle_fill_circle : CupertinoIcons.circle,
                color: sel ? AppColors.blue : c.textTertiary, size: 22),
            const SizedBox(width: 12),
            Icon(icon, size: 18, color: c.textSecondary),
            const SizedBox(width: 8),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: T.headline(context).copyWith(fontSize: 15.5)),
                Text(detail, style: T.sub(context).copyWith(fontSize: 13)),
              ]),
            ),
            ?trailing,
          ]),
        ),
      ),
    );
  }
}
