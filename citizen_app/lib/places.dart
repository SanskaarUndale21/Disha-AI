import 'dart:async';
import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

import 'api.dart';
import 'theme.dart';

class Place {
  final String name;
  final LatLng point;
  const Place(this.name, this.point);

  String get title => name.split(',').first.trim();
  String get subtitle {
    final parts = name.split(',').map((s) => s.trim()).toList();
    return parts.length > 1 ? parts.sublist(1).join(', ') : '';
  }
}

/// Place search through OpenStreetMap Nominatim. Requests are spaced at least a second apart (usage policy).
class Places {
  static DateTime _last = DateTime.fromMillisecondsSinceEpoch(0);
  static Future<void> _queue = Future.value();

  /// "12.97, 77.59" style input, or null.
  static LatLng? parseCoords(String s) {
    final m = RegExp(r'^\s*(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$').firstMatch(s);
    if (m == null) return null;
    final a = double.parse(m.group(1)!), b = double.parse(m.group(2)!);
    if (a.abs() > 90 || b.abs() > 180) return null;
    return LatLng(a, b);
  }

  static Future<List<Place>> search(String q, {int limit = 6}) {
    final done = Completer<List<Place>>();
    _queue = _queue.then((_) async {
      try {
        final wait = const Duration(milliseconds: 1100) - DateTime.now().difference(_last);
        if (!wait.isNegative) await Future<void>.delayed(wait);
        _last = DateTime.now();
        final uri = Uri.https('nominatim.openstreetmap.org', '/search',
            {'format': 'jsonv2', 'countrycodes': 'in', 'limit': '$limit', 'q': q});
        final r = await http.get(uri, headers: {'User-Agent': 'RoadWatchCitizen/1.1', 'Accept-Language': 'en'}).timeout(const Duration(seconds: 10));
        if (r.statusCode == 429 || r.statusCode >= 500) {
          throw ApiException('Place search is busy right now. Try again in a moment, or type latitude, longitude.');
        }
        if (r.statusCode >= 400) throw ApiException('Place search failed (${r.statusCode}).');
        final list = jsonDecode(r.body) as List;
        done.complete([
          for (final x in list)
            if (double.tryParse('${x['lat']}') != null && double.tryParse('${x['lon']}') != null)
              Place('${x['display_name']}', LatLng(double.parse('${x['lat']}'), double.parse('${x['lon']}')))
        ]);
      } on ApiException catch (e) {
        done.completeError(e);
      } catch (_) {
        done.completeError(ApiException("Can't search places. Check your internet connection."));
      }
    });
    return done.future;
  }
}

/// Text field with live place suggestions underneath (1 request per second at most).
class PlaceField extends StatefulWidget {
  const PlaceField({
    super.key,
    required this.controller,
    required this.hint,
    required this.icon,
    required this.onPicked,
    required this.onEdited,
    this.action = TextInputAction.next,
    this.onSubmit,
  });
  final TextEditingController controller;
  final String hint;
  final IconData icon;
  final void Function(Place) onPicked;
  final VoidCallback onEdited;
  final TextInputAction action;
  final VoidCallback? onSubmit;

  @override
  State<PlaceField> createState() => _PlaceFieldState();
}

class _PlaceFieldState extends State<PlaceField> {
  Timer? _t;
  int _seq = 0;
  List<Place> _sugg = const [];
  bool _busy = false;
  String? _err;
  bool _suppress = false;

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }

  void _changed(String v) {
    if (_suppress) return;
    widget.onEdited();
    _t?.cancel();
    final q = v.trim();
    if (q.length < 3 || Places.parseCoords(q) != null) {
      setState(() => (_sugg = const [], _busy = false, _err = null));
      return;
    }
    _t = Timer(const Duration(milliseconds: 900), () => _run(q));
  }

  Future<void> _run(String q) async {
    final id = ++_seq;
    setState(() => (_busy = true, _err = null));
    try {
      final r = await Places.search(q);
      if (!mounted || id != _seq) return;
      setState(() => (_sugg = r, _busy = false, _err = r.isEmpty ? 'No matching places. Try a landmark or area name.' : null));
    } catch (e) {
      if (!mounted || id != _seq) return;
      setState(() => (_sugg = const [], _busy = false, _err = '$e'));
    }
  }

  void _pick(Place p) {
    _suppress = true;
    widget.controller.text = p.title.isEmpty ? p.name : p.name.split(',').take(2).join(',').trim();
    _suppress = false;
    setState(() => _sugg = const []);
    FocusManager.instance.primaryFocus?.unfocus();
    widget.onPicked(p);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      TextField(
        controller: widget.controller,
        textInputAction: widget.action,
        onChanged: _changed,
        onSubmitted: (_) => widget.onSubmit?.call(),
        decoration: InputDecoration(
          hintText: widget.hint,
          prefixIcon: Icon(widget.icon, size: 18),
          suffixIcon: _busy
              ? const Padding(padding: EdgeInsets.all(14), child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)))
              : null,
          filled: true,
          fillColor: c.cardAlt,
          isDense: true,
          contentPadding: const EdgeInsets.symmetric(vertical: 14),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
        ),
      ),
      if (_err != null)
        Padding(padding: const EdgeInsets.fromLTRB(6, 6, 6, 0), child: Text(_err!, style: TextStyle(fontSize: 12.5, color: c.textSecondary))),
      for (final p in _sugg)
        Semantics(
          button: true,
          label: 'Choose ${p.name}',
          child: InkWell(
            onTap: () => _pick(p),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 9),
              child: Row(children: [
                Icon(CupertinoIcons.placemark, size: 16, color: c.textSecondary),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(p.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600)),
                    if (p.subtitle.isNotEmpty)
                      Text(p.subtitle, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12.5, color: c.textSecondary)),
                  ]),
                ),
              ]),
            ),
          ),
        ),
    ]);
  }
}
