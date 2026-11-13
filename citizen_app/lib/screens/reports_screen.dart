import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

import '../api.dart';
import '../main.dart';
import '../theme.dart';
import '../widgets.dart';
import 'detail_screen.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});
  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  List<Complaint>? _items;
  String? _error;
  int _filter = 0; // 0 open, 1 fixed or closed, 2 all

  @override
  void initState() {
    super.initState();
    _load();
    refreshTick.addListener(_load);
  }

  @override
  void dispose() {
    refreshTick.removeListener(_load);
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final r = await api.myComplaints();
      if (mounted) setState(() => (_items = r, _error = null));
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  bool _open(Complaint x) => x.status != 'resolved' && x.status != 'rejected';

  @override
  Widget build(BuildContext context) {
    final all = _items ?? [];
    final open = all.where(_open).toList();
    final closed = all.where((x) => !_open(x)).toList();
    final list = switch (_filter) { 0 => open, 1 => closed, _ => all };
    final c = AppColors.of(context);
    return SafeArea(
      bottom: false,
      child: RefreshIndicator(
        onRefresh: _load,
        color: Palette.asphalt,
        backgroundColor: Palette.yellow,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
          children: [
            Text('Your reports', style: T.display(context)),
            const SizedBox(height: 6),
            Text(
              all.isEmpty
                  ? 'Reports you send appear here.'
                  : '${all.length} sent, ${all.where((x) => x.status == 'resolved').length} fixed so far.',
              style: T.sub(context),
            ),
            const SizedBox(height: 20),
            Row(children: [
              _tab(0, 'Open', open.length),
              _tab(1, 'Fixed or closed', closed.length),
              _tab(2, 'All', all.length),
            ]),
            Divider(height: 1, thickness: 1, color: c.line),
            const SizedBox(height: 8),
            if (_items == null && _error == null)
              const Padding(padding: EdgeInsets.all(40), child: CupertinoActivityIndicator())
            else if (_error != null && all.isEmpty)
              Padding(padding: const EdgeInsets.symmetric(vertical: 32), child: Text(_error!, style: T.sub(context)))
            else if (list.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 48),
                child: Column(children: [
                  Icon(_filter == 1 ? PhosphorIconsBold.hourglassMedium : PhosphorIconsBold.checkCircle,
                      size: 40, color: c.inkFaint),
                  const SizedBox(height: 10),
                  Text(_filter == 1 ? 'Nothing fixed yet' : 'No open reports', style: T.h3(context)),
                  const SizedBox(height: 4),
                  Text(
                      _filter == 1
                          ? 'When the city fixes or closes a report, it moves here.'
                          : 'Spot something? Report it from the map.',
                      textAlign: TextAlign.center,
                      style: T.sub(context)),
                ]),
              )
            else
              for (final x in list) ComplaintRow(x),
          ],
        ),
      ),
    );
  }

  Widget _tab(int i, String label, int count) {
    final c = AppColors.of(context);
    final active = _filter == i;
    return Pressable(
      onTap: () => setState(() => _filter = i),
      child: Padding(
        padding: const EdgeInsets.only(right: 22),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('$label  $count',
              style: TextStyle(
                  fontSize: 15.5, fontWeight: active ? FontWeight.w700 : FontWeight.w500, color: active ? c.ink : c.inkFaint)),
          const SizedBox(height: 8),
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            height: 3,
            width: active ? 28 : 0,
            color: Palette.yellow,
          ),
        ]),
      ),
    );
  }
}

/// One report in a list: real photo, what and where, current stage.
class ComplaintRow extends StatelessWidget {
  const ComplaintRow(this.c, {super.key});
  final Complaint c;
  @override
  Widget build(BuildContext context) {
    final cat = categoryOf(c.category);
    final colors = AppColors.of(context);
    final thumb = c.media.where((m) => !m.isVideo).map((m) => m.mediaUrl).firstOrNull;
    final place = c.address?.isNotEmpty == true ? c.address!.split(',').first : null;
    return Pressable(
      onTap: () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => DetailScreen(id: c.id, initial: c))),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: colors.line))),
        child: Row(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(
              width: 68,
              height: 68,
              child: thumb != null
                  ? Image.network(api.url(thumb),
                      fit: BoxFit.cover, errorBuilder: (_, _, _) => Image.asset(cat.thumb, fit: BoxFit.cover))
                  : (c.media.any((m) => m.isVideo)
                      ? Container(
                          color: Palette.asphalt,
                          child: const Icon(PhosphorIconsFill.videoCamera, color: Colors.white, size: 26))
                      : Image.asset(cat.thumb, fit: BoxFit.cover)),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(cat.label, style: T.h3(context)),
              const SizedBox(height: 2),
              Text(
                [?place, timeAgo(c.createdAt)].join(', '),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: T.small(context),
              ),
              const SizedBox(height: 6),
              StatusTag(c.status),
            ]),
          ),
          Icon(PhosphorIconsBold.caretRight, size: 18, color: colors.inkFaint),
        ]),
      ),
    );
  }
}
