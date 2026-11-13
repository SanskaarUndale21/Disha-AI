import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Tiny translation layer. English is the fallback for any missing string.
const appLangs = [
  ('en', 'English', 'English'),
  ('hi', 'Hindi', 'हिन्दी'),
  ('kn', 'Kannada', 'ಕನ್ನಡ'),
  ('mr', 'Marathi', 'मराठी'),
];

final langNotifier = ValueNotifier<String>('en');
String get lang => langNotifier.value;

/// Map page only has English and Hindi strings.
String get mapLang => lang == 'hi' ? 'hi' : 'en';

Future<void> loadLang() async {
  try {
    final p = await SharedPreferences.getInstance();
    final l = p.getString('lang');
    if (l != null && _t.containsKey(l)) langNotifier.value = l;
  } catch (_) {}
}

Future<void> setLang(String l) async {
  langNotifier.value = l;
  try {
    final p = await SharedPreferences.getInstance();
    await p.setString('lang', l);
  } catch (_) {}
}

String tr(String key, [Map<String, String>? args]) {
  var s = _t[lang]?[key] ?? _t['en']![key] ?? key;
  args?.forEach((k, v) => s = s.replaceAll('{$k}', v));
  return s;
}

const _t = <String, Map<String, String>>{
  'en': {
    'nav_home': 'Home', 'nav_map': 'Map', 'nav_reports': 'My Reports', 'nav_profile': 'Profile',
    'good_morning': 'Good morning', 'good_afternoon': 'Good afternoon', 'good_evening': 'Good evening',
    'hero_title': 'Spotted a bad road?', 'hero_sub': 'Snap a photo. AI checks it and sends it to the repair crew.',
    'report_issue': 'Report an issue',
    'qa_report': 'Report', 'qa_trip': 'Safe trip', 'qa_talk': 'Talk to Disha', 'qa_alerts': 'Alerts',
    'latest_report': 'Your latest report', 'days_open': 'Open for {n} days', 'today_open': 'Reported today',
    'one_day_open': 'Open for 1 day', 'closed_fixed': 'Fixed. Thank you!',
    'st_reported': 'Reported', 'st_verified': 'Verified', 'st_repairing': 'Repairing', 'st_fixed': 'Fixed',
    'in_review': 'In review', 'repair_underway': 'Repair underway', 'resolved': 'Resolved', 'closed': 'Closed',
    'submitted': 'Submitted',
    'empty_title': 'Welcome to Disha AI', 'empty_text': 'See a pothole? Report it in under a minute. We will keep you updated until it is fixed.',
    'empty_cta': 'Make your first report',
    'recent_reports': 'Recent reports', 'see_all': 'See all', 'quick_report': 'Quick report', 'near_you': 'Near you',
    'step_issue': 'Issue', 'step_photo': 'Photo', 'step_location': 'Location', 'step_send': 'Send',
    'step_of': 'Step {n} of 4', 'new_report': 'New Report',
    'whats_issue': 'What is the issue?', 'photo_title': 'Take a photo', 'photo_sub': 'Step back about a metre so the whole damage is in frame.',
    'take_photo': 'Photo', 'record_video': 'Video', 'library': 'Library', 'add_more': 'Add another',
    'ai_checking': 'AI is checking...', 'ai_ok': 'Road damage found', 'ai_fail': 'No damage found', 'ai_retry': 'Check failed',
    'retake': 'Retake', 'retry': 'Retry', 'remove': 'Remove',
    'where': 'Where is it?', 'finding_loc': 'Finding your location...', 'tap_map': 'Tap the map to place the pin',
    'adjust_map': 'Tap the map to adjust.', 'use_my_loc': 'Use my location', 'pinned': 'Pinned on the map',
    'details': 'Details (optional)', 'details_hint': 'e.g. Deep pothole near the bus stop',
    'summary': 'Check and send', 'contact': 'Your contact', 'contact_hint': 'Used only to send you repair updates. Optional.',
    'name': 'Full name', 'mobile': 'Mobile number', 'photos': 'Photos', 'issue': 'Issue', 'place': 'Place', 'no_photos': 'None, described in words',
    'next': 'Next', 'back': 'Back', 'submit': 'Send report', 'cancel': 'Cancel', 'uploading': 'Uploading...', 'analysing': 'AI is analysing...',
    'hint_photo': 'Add a photo of the damage, or describe it in a few words.', 'hint_checking': 'Checking your photos...',
    'hint_fix': 'Remove or retake the photos that did not pass.',
    'success_title': 'Report sent', 'success_text': 'Thank you for making your streets safer. We will keep you updated.',
    'ticket': 'Ticket', 'copy': 'Copy', 'copied': 'Ticket copied', 'share': 'Share', 'track': 'Track this report', 'done': 'Done',
    'share_text': 'I reported a road issue on Disha AI. Ticket {t}.',
    'err_offline': 'You seem to be offline. Check your internet and try again.',
    'err_server': 'Our server is not responding right now. Please try again in a minute.',
    'err_gps': 'Location is off or blocked. Turn it on, or tap the map to place the pin.',
    'err_generic': 'Something went wrong. Please try again.',
    'language': 'Language', 'language_hint': 'Changes the app, map and Disha call language.',
    'profile': 'Profile', 'loading_map': 'Opening map', 'loading_map_sub': 'Getting roads and potholes ready',
    'talk_title': 'Talk to Disha in the app', 'talk_sub': 'Voice and camera, 4 languages',
    'trip_sub': 'Routes that avoid potholes', 'alerts_sub': 'Notifications',
  },
  'hi': {
    'nav_home': 'होम', 'nav_map': 'नक्शा', 'nav_reports': 'मेरी शिकायतें', 'nav_profile': 'प्रोफ़ाइल',
    'good_morning': 'सुप्रभात', 'good_afternoon': 'नमस्कार', 'good_evening': 'शुभ संध्या',
    'hero_title': 'खराब सड़क दिखी?', 'hero_sub': 'फोटो खींचें। AI जाँचकर मरम्मत टीम को भेज देगा।',
    'report_issue': 'शिकायत दर्ज करें',
    'qa_report': 'शिकायत', 'qa_trip': 'सुरक्षित सफर', 'qa_talk': 'दिशा से बात', 'qa_alerts': 'अलर्ट',
    'latest_report': 'आपकी ताज़ा शिकायत', 'days_open': '{n} दिन से खुली', 'today_open': 'आज दर्ज हुई',
    'one_day_open': '1 दिन से खुली', 'closed_fixed': 'ठीक हो गई। धन्यवाद!',
    'st_reported': 'दर्ज', 'st_verified': 'जाँची गई', 'st_repairing': 'मरम्मत जारी', 'st_fixed': 'ठीक हुई',
    'in_review': 'समीक्षा में', 'repair_underway': 'मरम्मत जारी', 'resolved': 'हल हुई', 'closed': 'बंद',
    'submitted': 'दर्ज',
    'empty_title': 'दिशा AI में स्वागत है', 'empty_text': 'गड्ढा दिखा? एक मिनट में शिकायत करें। ठीक होने तक हम आपको बताते रहेंगे।',
    'empty_cta': 'पहली शिकायत करें',
    'recent_reports': 'हाल की शिकायतें', 'see_all': 'सभी देखें', 'quick_report': 'तुरंत शिकायत', 'near_you': 'आपके पास',
    'step_issue': 'समस्या', 'step_photo': 'फोटो', 'step_location': 'जगह', 'step_send': 'भेजें',
    'step_of': 'चरण {n} / 4', 'new_report': 'नई शिकायत',
    'whats_issue': 'समस्या क्या है?', 'photo_title': 'फोटो लें', 'photo_sub': 'करीब एक मीटर पीछे हटें ताकि पूरा नुकसान फ्रेम में आए।',
    'take_photo': 'फोटो', 'record_video': 'वीडियो', 'library': 'गैलरी', 'add_more': 'और जोड़ें',
    'ai_checking': 'AI जाँच रहा है...', 'ai_ok': 'सड़क खराब मिली', 'ai_fail': 'कोई नुकसान नहीं दिखा', 'ai_retry': 'जाँच विफल',
    'retake': 'दोबारा लें', 'retry': 'फिर कोशिश', 'remove': 'हटाएँ',
    'where': 'यह कहाँ है?', 'finding_loc': 'आपकी लोकेशन खोज रहे हैं...', 'tap_map': 'पिन लगाने के लिए नक्शे पर टैप करें',
    'adjust_map': 'बदलने के लिए नक्शे पर टैप करें।', 'use_my_loc': 'मेरी लोकेशन', 'pinned': 'नक्शे पर पिन किया',
    'details': 'विवरण (वैकल्पिक)', 'details_hint': 'जैसे बस स्टॉप के पास गहरा गड्ढा',
    'summary': 'जाँचें और भेजें', 'contact': 'आपका संपर्क', 'contact_hint': 'सिर्फ मरम्मत की जानकारी भेजने के लिए। वैकल्पिक।',
    'name': 'पूरा नाम', 'mobile': 'मोबाइल नंबर', 'photos': 'फोटो', 'issue': 'समस्या', 'place': 'जगह', 'no_photos': 'कोई नहीं, शब्दों में बताया',
    'next': 'आगे', 'back': 'पीछे', 'submit': 'शिकायत भेजें', 'cancel': 'रद्द करें', 'uploading': 'अपलोड हो रहा है...', 'analysing': 'AI विश्लेषण कर रहा है...',
    'hint_photo': 'नुकसान की फोटो जोड़ें, या कुछ शब्दों में बताएँ।', 'hint_checking': 'आपकी फोटो जाँची जा रही हैं...',
    'hint_fix': 'जो फोटो पास नहीं हुईं उन्हें हटाएँ या दोबारा लें।',
    'success_title': 'शिकायत भेज दी गई', 'success_text': 'सड़कें सुरक्षित बनाने के लिए धन्यवाद। हम आपको अपडेट देते रहेंगे।',
    'ticket': 'टिकट', 'copy': 'कॉपी', 'copied': 'टिकट कॉपी हुआ', 'share': 'शेयर', 'track': 'शिकायत ट्रैक करें', 'done': 'पूरा',
    'share_text': 'मैंने दिशा AI पर सड़क की समस्या दर्ज की। टिकट {t}।',
    'err_offline': 'आप ऑफ़लाइन लग रहे हैं। इंटरनेट जाँचकर फिर कोशिश करें।',
    'err_server': 'सर्वर अभी जवाब नहीं दे रहा। एक मिनट बाद फिर कोशिश करें।',
    'err_gps': 'लोकेशन बंद या रोकी हुई है। उसे चालू करें, या नक्शे पर पिन लगाएँ।',
    'err_generic': 'कुछ गड़बड़ हो गई। फिर कोशिश करें।',
    'language': 'भाषा', 'language_hint': 'ऐप, नक्शे और दिशा कॉल की भाषा बदलती है।',
    'profile': 'प्रोफ़ाइल', 'loading_map': 'नक्शा खुल रहा है', 'loading_map_sub': 'सड़कें और गड्ढे तैयार हो रहे हैं',
    'talk_title': 'ऐप में दिशा से बात करें', 'talk_sub': 'आवाज़ और कैमरा, 4 भाषाएँ',
    'trip_sub': 'गड्ढों से बचाने वाले रास्ते', 'alerts_sub': 'सूचनाएँ',
  },
  'kn': {
    'nav_home': 'ಮುಖಪುಟ', 'nav_map': 'ನಕ್ಷೆ', 'nav_reports': 'ನನ್ನ ದೂರುಗಳು', 'nav_profile': 'ಪ್ರೊಫೈಲ್',
    'good_morning': 'ಶುಭೋದಯ', 'good_afternoon': 'ನಮಸ್ಕಾರ', 'good_evening': 'ಶುಭ ಸಂಜೆ',
    'hero_title': 'ಕೆಟ್ಟ ರಸ್ತೆ ಕಂಡಿತೇ?', 'hero_sub': 'ಫೋಟೋ ತೆಗೆಯಿರಿ. AI ಪರಿಶೀಲಿಸಿ ದುರಸ್ತಿ ತಂಡಕ್ಕೆ ಕಳಿಸುತ್ತದೆ.',
    'report_issue': 'ದೂರು ನೀಡಿ',
    'qa_report': 'ದೂರು', 'qa_trip': 'ಸುರಕ್ಷಿತ ಪ್ರಯಾಣ', 'qa_talk': 'ದಿಶಾ ಜೊತೆ ಮಾತು', 'qa_alerts': 'ಎಚ್ಚರಿಕೆ',
    'latest_report': 'ನಿಮ್ಮ ಇತ್ತೀಚಿನ ದೂರು', 'days_open': '{n} ದಿನಗಳಿಂದ ಬಾಕಿ', 'today_open': 'ಇಂದು ದಾಖಲಾಗಿದೆ',
    'one_day_open': '1 ದಿನದಿಂದ ಬಾಕಿ', 'closed_fixed': 'ಸರಿಪಡಿಸಲಾಗಿದೆ. ಧನ್ಯವಾದ!',
    'st_reported': 'ದಾಖಲು', 'st_verified': 'ಪರಿಶೀಲನೆ', 'st_repairing': 'ದುರಸ್ತಿ', 'st_fixed': 'ಸರಿಯಾಯಿತು',
    'in_review': 'ಪರಿಶೀಲನೆಯಲ್ಲಿ', 'repair_underway': 'ದುರಸ್ತಿ ನಡೆಯುತ್ತಿದೆ', 'resolved': 'ಪರಿಹಾರ', 'closed': 'ಮುಚ್ಚಲಾಗಿದೆ',
    'submitted': 'ಸಲ್ಲಿಸಲಾಗಿದೆ',
    'empty_title': 'ದಿಶಾ AI ಗೆ ಸ್ವಾಗತ', 'empty_text': 'ಗುಂಡಿ ಕಂಡರೆ ಒಂದು ನಿಮಿಷದಲ್ಲಿ ದೂರು ನೀಡಿ. ಸರಿಪಡಿಸುವವರೆಗೆ ನಿಮಗೆ ತಿಳಿಸುತ್ತೇವೆ.',
    'empty_cta': 'ಮೊದಲ ದೂರು ನೀಡಿ',
    'recent_reports': 'ಇತ್ತೀಚಿನ ದೂರುಗಳು', 'see_all': 'ಎಲ್ಲಾ ನೋಡಿ', 'quick_report': 'ತ್ವರಿತ ದೂರು', 'near_you': 'ನಿಮ್ಮ ಹತ್ತಿರ',
    'step_issue': 'ಸಮಸ್ಯೆ', 'step_photo': 'ಫೋಟೋ', 'step_location': 'ಸ್ಥಳ', 'step_send': 'ಕಳಿಸಿ',
    'step_of': 'ಹಂತ {n} / 4', 'new_report': 'ಹೊಸ ದೂರು',
    'whats_issue': 'ಸಮಸ್ಯೆ ಏನು?', 'photo_title': 'ಫೋಟೋ ತೆಗೆಯಿರಿ', 'photo_sub': 'ಒಂದು ಮೀಟರ್ ಹಿಂದೆ ನಿಂತು ಪೂರ್ತಿ ಹಾನಿ ಕಾಣುವಂತೆ ತೆಗೆಯಿರಿ.',
    'take_photo': 'ಫೋಟೋ', 'record_video': 'ವಿಡಿಯೋ', 'library': 'ಗ್ಯಾಲರಿ', 'add_more': 'ಇನ್ನೊಂದು ಸೇರಿಸಿ',
    'ai_checking': 'AI ಪರಿಶೀಲಿಸುತ್ತಿದೆ...', 'ai_ok': 'ರಸ್ತೆ ಹಾನಿ ಕಂಡಿದೆ', 'ai_fail': 'ಹಾನಿ ಕಂಡಿಲ್ಲ', 'ai_retry': 'ಪರಿಶೀಲನೆ ವಿಫಲ',
    'retake': 'ಮತ್ತೆ ತೆಗೆಯಿರಿ', 'retry': 'ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ', 'remove': 'ತೆಗೆಯಿರಿ',
    'where': 'ಇದು ಎಲ್ಲಿದೆ?', 'finding_loc': 'ನಿಮ್ಮ ಸ್ಥಳ ಹುಡುಕುತ್ತಿದೆ...', 'tap_map': 'ಪಿನ್ ಹಾಕಲು ನಕ್ಷೆ ಮೇಲೆ ಟ್ಯಾಪ್ ಮಾಡಿ',
    'adjust_map': 'ಬದಲಿಸಲು ನಕ್ಷೆ ಮೇಲೆ ಟ್ಯಾಪ್ ಮಾಡಿ.', 'use_my_loc': 'ನನ್ನ ಸ್ಥಳ', 'pinned': 'ನಕ್ಷೆಯಲ್ಲಿ ಪಿನ್ ಮಾಡಲಾಗಿದೆ',
    'details': 'ವಿವರ (ಐಚ್ಛಿಕ)', 'details_hint': 'ಉದಾ. ಬಸ್ ನಿಲ್ದಾಣದ ಬಳಿ ದೊಡ್ಡ ಗುಂಡಿ',
    'summary': 'ಪರಿಶೀಲಿಸಿ ಕಳಿಸಿ', 'contact': 'ನಿಮ್ಮ ಸಂಪರ್ಕ', 'contact_hint': 'ದುರಸ್ತಿ ಮಾಹಿತಿ ಕಳಿಸಲು ಮಾತ್ರ. ಐಚ್ಛಿಕ.',
    'name': 'ಪೂರ್ಣ ಹೆಸರು', 'mobile': 'ಮೊಬೈಲ್ ಸಂಖ್ಯೆ', 'photos': 'ಫೋಟೋಗಳು', 'issue': 'ಸಮಸ್ಯೆ', 'place': 'ಸ್ಥಳ', 'no_photos': 'ಇಲ್ಲ, ಮಾತಿನಲ್ಲಿ ವಿವರಿಸಲಾಗಿದೆ',
    'next': 'ಮುಂದೆ', 'back': 'ಹಿಂದೆ', 'submit': 'ದೂರು ಕಳಿಸಿ', 'cancel': 'ರದ್ದು', 'uploading': 'ಅಪ್‌ಲೋಡ್ ಆಗುತ್ತಿದೆ...', 'analysing': 'AI ವಿಶ್ಲೇಷಿಸುತ್ತಿದೆ...',
    'hint_photo': 'ಹಾನಿಯ ಫೋಟೋ ಸೇರಿಸಿ, ಅಥವಾ ಕೆಲವು ಮಾತುಗಳಲ್ಲಿ ಬರೆಯಿರಿ.', 'hint_checking': 'ನಿಮ್ಮ ಫೋಟೋಗಳನ್ನು ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ...',
    'hint_fix': 'ಪಾಸಾಗದ ಫೋಟೋಗಳನ್ನು ತೆಗೆಯಿರಿ ಅಥವಾ ಮತ್ತೆ ತೆಗೆಯಿರಿ.',
    'success_title': 'ದೂರು ಕಳಿಸಲಾಗಿದೆ', 'success_text': 'ರಸ್ತೆಗಳನ್ನು ಸುರಕ್ಷಿತಗೊಳಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದ. ನಿಮಗೆ ಮಾಹಿತಿ ನೀಡುತ್ತೇವೆ.',
    'ticket': 'ಟಿಕೆಟ್', 'copy': 'ನಕಲಿಸಿ', 'copied': 'ಟಿಕೆಟ್ ನಕಲಾಗಿದೆ', 'share': 'ಹಂಚಿ', 'track': 'ದೂರು ಹಿಂಬಾಲಿಸಿ', 'done': 'ಮುಗಿಯಿತು',
    'share_text': 'ನಾನು ದಿಶಾ AI ನಲ್ಲಿ ರಸ್ತೆ ಸಮಸ್ಯೆ ದಾಖಲಿಸಿದೆ. ಟಿಕೆಟ್ {t}.',
    'err_offline': 'ನೀವು ಆಫ್‌ಲೈನ್ ಆಗಿರುವಂತಿದೆ. ಇಂಟರ್ನೆಟ್ ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
    'err_server': 'ಸರ್ವರ್ ಈಗ ಉತ್ತರಿಸುತ್ತಿಲ್ಲ. ಒಂದು ನಿಮಿಷ ಬಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
    'err_gps': 'ಸ್ಥಳ ಆಫ್ ಅಥವಾ ನಿರ್ಬಂಧಿತವಾಗಿದೆ. ಆನ್ ಮಾಡಿ, ಅಥವಾ ನಕ್ಷೆಯಲ್ಲಿ ಪಿನ್ ಹಾಕಿ.',
    'err_generic': 'ಏನೋ ತಪ್ಪಾಯಿತು. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
    'language': 'ಭಾಷೆ', 'language_hint': 'ಆ್ಯಪ್, ನಕ್ಷೆ ಮತ್ತು ದಿಶಾ ಕರೆಯ ಭಾಷೆ ಬದಲಾಗುತ್ತದೆ.',
    'profile': 'ಪ್ರೊಫೈಲ್', 'loading_map': 'ನಕ್ಷೆ ತೆರೆಯುತ್ತಿದೆ', 'loading_map_sub': 'ರಸ್ತೆ ಮತ್ತು ಗುಂಡಿಗಳನ್ನು ಸಿದ್ಧಪಡಿಸಲಾಗುತ್ತಿದೆ',
    'talk_title': 'ಆ್ಯಪ್‌ನಲ್ಲಿ ದಿಶಾ ಜೊತೆ ಮಾತನಾಡಿ', 'talk_sub': 'ಧ್ವನಿ ಮತ್ತು ಕ್ಯಾಮೆರಾ, 4 ಭಾಷೆಗಳು',
    'trip_sub': 'ಗುಂಡಿ ತಪ್ಪಿಸುವ ದಾರಿಗಳು', 'alerts_sub': 'ಸೂಚನೆಗಳು',
  },
  'mr': {
    'nav_home': 'मुख्यपृष्ठ', 'nav_map': 'नकाशा', 'nav_reports': 'माझ्या तक्रारी', 'nav_profile': 'प्रोफाइल',
    'good_morning': 'शुभ प्रभात', 'good_afternoon': 'नमस्कार', 'good_evening': 'शुभ संध्या',
    'hero_title': 'खराब रस्ता दिसला?', 'hero_sub': 'फोटो काढा. AI तपासून दुरुस्ती पथकाकडे पाठवेल.',
    'report_issue': 'तक्रार नोंदवा',
    'qa_report': 'तक्रार', 'qa_trip': 'सुरक्षित प्रवास', 'qa_talk': 'दिशाशी बोला', 'qa_alerts': 'सूचना',
    'latest_report': 'तुमची ताजी तक्रार', 'days_open': '{n} दिवसांपासून खुली', 'today_open': 'आज नोंदवली',
    'one_day_open': '1 दिवसापासून खुली', 'closed_fixed': 'दुरुस्त झाले. धन्यवाद!',
    'st_reported': 'नोंदवली', 'st_verified': 'तपासली', 'st_repairing': 'दुरुस्ती सुरू', 'st_fixed': 'दुरुस्त',
    'in_review': 'तपासणीत', 'repair_underway': 'दुरुस्ती सुरू', 'resolved': 'निकाली', 'closed': 'बंद',
    'submitted': 'नोंदवली',
    'empty_title': 'दिशा AI मध्ये स्वागत', 'empty_text': 'खड्डा दिसला? एका मिनिटात तक्रार करा. दुरुस्त होईपर्यंत आम्ही कळवत राहू.',
    'empty_cta': 'पहिली तक्रार करा',
    'recent_reports': 'अलीकडील तक्रारी', 'see_all': 'सर्व पहा', 'quick_report': 'झटपट तक्रार', 'near_you': 'तुमच्या जवळ',
    'step_issue': 'समस्या', 'step_photo': 'फोटो', 'step_location': 'ठिकाण', 'step_send': 'पाठवा',
    'step_of': 'पायरी {n} / 4', 'new_report': 'नवी तक्रार',
    'whats_issue': 'समस्या काय आहे?', 'photo_title': 'फोटो काढा', 'photo_sub': 'एक मीटर मागे उभे राहा म्हणजे पूर्ण नुकसान दिसेल.',
    'take_photo': 'फोटो', 'record_video': 'व्हिडिओ', 'library': 'गॅलरी', 'add_more': 'आणखी जोडा',
    'ai_checking': 'AI तपासत आहे...', 'ai_ok': 'रस्त्याचे नुकसान आढळले', 'ai_fail': 'नुकसान आढळले नाही', 'ai_retry': 'तपासणी अयशस्वी',
    'retake': 'पुन्हा काढा', 'retry': 'पुन्हा प्रयत्न', 'remove': 'काढा',
    'where': 'हे कुठे आहे?', 'finding_loc': 'तुमचे ठिकाण शोधत आहे...', 'tap_map': 'पिन लावण्यासाठी नकाशावर टॅप करा',
    'adjust_map': 'बदलण्यासाठी नकाशावर टॅप करा.', 'use_my_loc': 'माझे ठिकाण', 'pinned': 'नकाशावर पिन केले',
    'details': 'तपशील (ऐच्छिक)', 'details_hint': 'उदा. बस थांब्याजवळ खोल खड्डा',
    'summary': 'तपासा आणि पाठवा', 'contact': 'तुमचा संपर्क', 'contact_hint': 'फक्त दुरुस्तीची माहिती पाठवण्यासाठी. ऐच्छिक.',
    'name': 'पूर्ण नाव', 'mobile': 'मोबाइल नंबर', 'photos': 'फोटो', 'issue': 'समस्या', 'place': 'ठिकाण', 'no_photos': 'नाही, शब्दांत सांगितले',
    'next': 'पुढे', 'back': 'मागे', 'submit': 'तक्रार पाठवा', 'cancel': 'रद्द करा', 'uploading': 'अपलोड होत आहे...', 'analysing': 'AI विश्लेषण करत आहे...',
    'hint_photo': 'नुकसानीचा फोटो जोडा, किंवा थोडक्यात लिहा.', 'hint_checking': 'तुमचे फोटो तपासले जात आहेत...',
    'hint_fix': 'तपासणीत नापास झालेले फोटो काढा किंवा पुन्हा काढा.',
    'success_title': 'तक्रार पाठवली', 'success_text': 'रस्ते सुरक्षित केल्याबद्दल धन्यवाद. आम्ही तुम्हाला कळवत राहू.',
    'ticket': 'तिकीट', 'copy': 'कॉपी', 'copied': 'तिकीट कॉपी झाले', 'share': 'शेअर', 'track': 'तक्रार ट्रॅक करा', 'done': 'झाले',
    'share_text': 'मी दिशा AI वर रस्त्याची समस्या नोंदवली. तिकीट {t}.',
    'err_offline': 'तुम्ही ऑफलाइन दिसता. इंटरनेट तपासून पुन्हा प्रयत्न करा.',
    'err_server': 'सर्व्हर सध्या उत्तर देत नाही. एका मिनिटाने पुन्हा प्रयत्न करा.',
    'err_gps': 'लोकेशन बंद किंवा अडवलेले आहे. ते चालू करा, किंवा नकाशावर पिन लावा.',
    'err_generic': 'काहीतरी चुकले. पुन्हा प्रयत्न करा.',
    'language': 'भाषा', 'language_hint': 'ॲप, नकाशा आणि दिशा कॉलची भाषा बदलते.',
    'profile': 'प्रोफाइल', 'loading_map': 'नकाशा उघडत आहे', 'loading_map_sub': 'रस्ते आणि खड्डे तयार होत आहेत',
    'talk_title': 'ॲपमध्ये दिशाशी बोला', 'talk_sub': 'आवाज आणि कॅमेरा, 4 भाषा',
    'trip_sub': 'खड्डे टाळणारे मार्ग', 'alerts_sub': 'सूचना',
  },
};
