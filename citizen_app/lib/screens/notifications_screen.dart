import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../notifications.dart';
import '../theme.dart';
import '../widgets.dart';

(IconData, Color) _look(NotifKind k) => switch (k) {
      NotifKind.emergency => (CupertinoIcons.exclamationmark_triangle_fill, AppColors.red),
      NotifKind.complaint => (CupertinoIcons.doc_text_fill, AppColors.blue),
      NotifKind.repair => (CupertinoIcons.hammer_fill, AppColors.green),
      NotifKind.severe => (CupertinoIcons.bolt_fill, AppColors.orange),
      NotifKind.route => (CupertinoIcons.arrow_branch, AppColors.indigo),
    };

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  @override
  void initState() {
    super.initState();
    notifs.dismissBanner();
  }

  Future<void> _confirmClear() async {
    final ok = await showCupertinoDialog<bool>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text('Clear all notifications?'),
        content: const Text('This removes every item from this list.'),
        actions: [
          CupertinoDialogAction(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          CupertinoDialogAction(isDestructiveAction: true, onPressed: () => Navigator.pop(ctx, true), child: const Text('Clear')),
        ],
      ),
    );
    if (ok == true) notifs.clear();
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return Scaffold(
      backgroundColor: c.bg,
      appBar: AppBar(
        backgroundColor: c.bg,
        elevation: 0,
        scrolledUnderElevation: 0,
        title: Text('Notifications', style: T.title(context)),
        actions: [
          ListenableBuilder(
            listenable: notifs,
            builder: (_, _) => notifs.items.isEmpty
                ? const SizedBox.shrink()
                : PopupMenuButton<String>(
                    tooltip: 'More',
                    onSelected: (v) => v == 'read' ? notifs.markAllRead() : _confirmClear(),
                    itemBuilder: (_) => [
                      if (notifs.unread > 0) const PopupMenuItem(value: 'read', child: Text('Mark all as read')),
                      const PopupMenuItem(value: 'clear', child: Text('Clear all')),
                    ],
                  ),
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: notifs,
        builder: (context, _) {
          final list = notifs.items;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 40),
            children: [
              ValueListenableBuilder<bool>(
                valueListenable: notifs.permissionGranted,
                builder: (_, ok, __) => ok
                    ? const SizedBox.shrink()
                    : Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Material(
                          color: AppColors.orange.withValues(alpha: 0.18),
                          borderRadius: BorderRadius.circular(14),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(14),
                            onTap: notifs.requestPermission,
                            child: const Padding(
                              padding: EdgeInsets.all(14),
                              child: Row(children: [
                                Icon(CupertinoIcons.bell_slash_fill, color: AppColors.orange),
                                SizedBox(width: 12),
                                Expanded(
                                    child: Text('Phone notifications are blocked, so alerts show only inside the app. Tap to allow them.',
                                        style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600))),
                              ]),
                            ),
                          ),
                        ),
                      ),
              ),
              if (list.isEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 80),
                  child: Column(children: [
                    Icon(CupertinoIcons.bell, size: 44, color: c.textTertiary),
                    const SizedBox(height: 12),
                    Text('No notifications yet', style: T.title(context)),
                    const SizedBox(height: 6),
                    Text('Report updates, emergencies and road damage near you will appear here.',
                        textAlign: TextAlign.center, style: T.sub(context)),
                  ]),
                ),
              for (final n in list) _tile(context, n),
            ],
          );
        },
      ),
    );
  }

  Widget _tile(BuildContext context, AppNotification n) {
    final c = AppColors.of(context);
    final (icon, color) = _look(n.kind);
    return Dismissible(
      key: ValueKey(n.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(color: AppColors.red, borderRadius: BorderRadius.circular(16)),
        child: const Icon(CupertinoIcons.delete, color: Colors.white),
      ),
      onDismissed: (_) {
        notifs.remove(n.id);
      },
      child: Semantics(
        button: true,
        label: '${n.read ? '' : 'Unread. '}${n.title}. ${n.body}',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => notifs.markRead(n.id),
          child: Container(
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: n.read ? c.card : color.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: n.read ? Colors.transparent : color.withValues(alpha: 0.5)),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              IconBadge(icon, color, size: 38),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(
                        child: Text(n.title,
                            style: TextStyle(fontSize: 15, fontWeight: n.read ? FontWeight.w600 : FontWeight.w800))),
                    if (!n.read) Container(width: 9, height: 9, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                  ]),
                  const SizedBox(height: 3),
                  Text(n.body, style: T.sub(context).copyWith(fontSize: 13.5)),
                  const SizedBox(height: 4),
                  Text(timeAgo(n.at), style: TextStyle(fontSize: 12, color: c.textTertiary)),
                ]),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Bell with an unread badge for headers.
class NotificationBell extends StatelessWidget {
  const NotificationBell({super.key});
  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: notifs,
      builder: (context, _) {
        final n = notifs.unread;
        return Semantics(
          button: true,
          label: n == 0 ? 'Notifications' : 'Notifications, $n unread',
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => const NotificationsScreen())),
            child: SizedBox(
              width: 44,
              height: 44,
              child: Stack(alignment: Alignment.center, children: [
                const IconBadge(CupertinoIcons.bell_fill, AppColors.orange, size: 38),
                if (n > 0)
                  Positioned(
                    right: 0,
                    top: 0,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                      decoration: BoxDecoration(color: AppColors.red, borderRadius: BorderRadius.circular(99)),
                      child: Text(n > 9 ? '9+' : '$n',
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800)),
                    ),
                  ),
              ]),
            ),
          ),
        );
      },
    );
  }
}

/// Red full-width banner shown over every tab while an emergency alert is active.
class EmergencyBanner extends StatelessWidget {
  const EmergencyBanner({super.key});
  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<AppNotification?>(
      valueListenable: notifs.emergencyBanner,
      builder: (context, n, _) {
        if (n == null) return const SizedBox.shrink();
        return Positioned(
          left: 10,
          right: 10,
          top: MediaQuery.paddingOf(context).top + 6,
          child: Semantics(
            liveRegion: true,
            label: 'Emergency. ${n.body}',
            child: Material(
              color: const Color(0xFFC62828),
              elevation: 8,
              borderRadius: BorderRadius.circular(16),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Icon(CupertinoIcons.exclamationmark_triangle_fill, color: Colors.white, size: 26),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('EMERGENCY: FALL DETECTED',
                          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 15)),
                      const SizedBox(height: 3),
                      Text(n.body, style: const TextStyle(color: Colors.white, fontSize: 14)),
                    ]),
                  ),
                  IconButton(
                      tooltip: 'Dismiss alert',
                      onPressed: notifs.dismissBanner,
                      icon: const Icon(Icons.close, color: Colors.white)),
                ]),
              ),
            ),
          ),
        );
      },
    );
  }
}
