import 'package:flutter/cupertino.dart';

import '../api.dart';
import '../i18n.dart';
import 'home_screen.dart' show friendlyError;
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
  int _filter = 0; // 0 all, 1 open, 2 closed

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

  List<Complaint> get _visible {
    final all = _items ?? [];
    return switch (_filter) {
      1 => all.where((x) => x.status != 'resolved' && x.status != 'rejected').toList(),
      2 => all.where((x) => x.status == 'resolved' || x.status == 'rejected').toList(),
      _ => all,
    };
  }

  @override
  Widget build(BuildContext context) {
    final list = _visible;
    return CustomScrollView(
      physics: const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics()),
      slivers: [
        CupertinoSliverRefreshControl(onRefresh: _load),
        SliverSafeArea(
          bottom: false,
          sliver: SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
            sliver: SliverList.list(children: [
              Text(tr('nav_reports'), style: T.largeTitle(context)),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: CupertinoSlidingSegmentedControl<int>(
                  groupValue: _filter,
                  onValueChanged: (v) => setState(() => _filter = v ?? 0),
                  children: const {
                    0: Padding(padding: EdgeInsets.symmetric(vertical: 6), child: Text('All')),
                    1: Text('Open'),
                    2: Text('Closed'),
                  },
                ),
              ),
              const SizedBox(height: 18),
              if (_items == null && _error == null)
                const Column(children: [Skeleton(height: 92, radius: 20), SizedBox(height: 10), Skeleton(height: 92, radius: 20), SizedBox(height: 10), Skeleton(height: 92, radius: 20)])
              else if (_error != null && (_items ?? []).isEmpty)
                Padding(
                  padding: const EdgeInsets.all(30),
                  child: Text(friendlyError(_error!), textAlign: TextAlign.center, style: T.sub(context)),
                )
              else if (list.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 40),
                  child: Column(children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(20),
                      child: Image.asset('assets/photos/crack_sq.jpg', width: 110, height: 110, fit: BoxFit.cover),
                    ),
                    const SizedBox(height: 14),
                    Text(_filter == 2 ? 'Nothing closed yet' : 'Nothing here', style: T.headline(context)),
                    const SizedBox(height: 4),
                    Text('Report a road issue from Home and track it here.', style: T.sub(context)),
                  ]),
                )
              else
                for (final x in list) Padding(padding: const EdgeInsets.only(bottom: 10), child: ComplaintTile(x)),
            ]),
          ),
        ),
      ],
    );
  }
}

class ComplaintTile extends StatelessWidget {
  const ComplaintTile(this.c, {super.key});
  final Complaint c;
  @override
  Widget build(BuildContext context) {
    final cat = categoryOf(c.category);
    final colors = AppColors.of(context);
    final thumb = c.media.where((m) => !m.isVideo).map((m) => m.mediaUrl).firstOrNull;
    return Pressable(
      onTap: () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => DetailScreen(id: c.id, initial: c))),
      child: CardBox(
        padding: const EdgeInsets.all(12),
        radius: 20,
        child: Row(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: SizedBox(
              width: 64,
              height: 64,
              child: thumb != null
                  ? Image.network(api.url(thumb),
                      fit: BoxFit.cover, errorBuilder: (_, _, _) => Image.asset(cat.thumb, fit: BoxFit.cover))
                  : Image.asset(cat.thumb, fit: BoxFit.cover),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(cat.label, style: T.headline(context).copyWith(fontSize: 16))),
                Text(timeAgo(c.createdAt), style: T.sub(context).copyWith(fontSize: 12.5)),
              ]),
              const SizedBox(height: 2),
              Text(
                c.description.isNotEmpty ? c.description : (c.address ?? c.ticket),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: T.sub(context),
              ),
              const SizedBox(height: 8),
              Row(children: [
                StatusPill(c.status),
                const SizedBox(width: 8),
                Text(c.ticket, style: TextStyle(fontSize: 12, color: colors.textTertiary, fontWeight: FontWeight.w500)),
                const Spacer(),
                if (c.media.isNotEmpty) ...[
                  Icon(CupertinoIcons.photo_on_rectangle, size: 14, color: colors.textTertiary),
                  const SizedBox(width: 3),
                  Text('${c.media.length}', style: TextStyle(fontSize: 12, color: colors.textTertiary)),
                ],
              ]),
            ]),
          ),
        ]),
      ),
    );
  }
}
