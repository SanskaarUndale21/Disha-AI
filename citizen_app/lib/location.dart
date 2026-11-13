import 'package:flutter/foundation.dart';
import 'package:geocoding/geocoding.dart';
import 'package:geolocator/geolocator.dart';

class Spot {
  final double lat, lon;
  final double? accuracy;
  final String? address, area;
  const Spot(this.lat, this.lon, {this.accuracy, this.address, this.area});
}

/// One shared, cached fix of where the citizen is.
class Locator extends ChangeNotifier {
  Spot? spot;
  String? error;
  bool busy = false;

  Future<Spot?> locate({bool force = false}) async {
    if (busy) return spot;
    if (spot != null && !force) return spot;
    busy = true;
    error = null;
    notifyListeners();
    try {
      if (!await Geolocator.isLocationServiceEnabled()) throw 'Location is off. Turn it on to pin the spot.';
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) perm = await Geolocator.requestPermission();
      if (perm == LocationPermission.denied || perm == LocationPermission.deniedForever) {
        throw 'Location permission is off. Allow it in Settings, or tap the map to place the pin.';
      }
      final p = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 20)),
      );
      spot = await describe(p.latitude, p.longitude, accuracy: p.accuracy);
    } catch (e) {
      error = '$e';
    } finally {
      busy = false;
      notifyListeners();
    }
    return spot;
  }

  /// Street address and neighbourhood for a point (mobile only; web has no geocoder).
  static Future<Spot> describe(double lat, double lon, {double? accuracy}) async {
    String? addr, area;
    if (!kIsWeb) {
      try {
        final pm = (await Geocoding().placemarkFromCoordinates(lat, lon)).first;
        final parts = [pm.street, pm.subLocality, pm.locality]
            .whereType<String>()
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty && !RegExp(r'^[A-Z0-9+]{4,}\+').hasMatch(s))
            .toSet()
            .toList();
        addr = parts.join(', ');
        area = [pm.subLocality, pm.locality].whereType<String>().where((s) => s.trim().isNotEmpty).join(', ');
      } catch (_) {}
    }
    return Spot(lat, lon, accuracy: accuracy, address: addr, area: area);
  }
}
