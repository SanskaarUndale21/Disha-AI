/* Disha AI: tiny UI dictionary. window.T(key) returns the string in the saved language, English as fallback. */
(function () {
  var LANGS = [
    { code: "en", native: "English", short: "EN" },
    { code: "hi", native: "हिन्दी", short: "हिं" },
    { code: "kn", native: "ಕನ್ನಡ", short: "ಕ" },
    { code: "mr", native: "मराठी", short: "मरा" }
  ];
  var D = {
    en: {
      home: "Home", report: "Report", drive: "Video analysis", map: "Map", reports: "My reports", alerts: "Alerts", profile: "Profile", talk: "Talk to Disha", lang: "Language",
      hero1: "Fix the road,", hero2: "not the excuses.", lede: "Photograph a pothole, crack or flooded stretch. Disha AI checks it, pins it on the city map and sends it to the crew that repairs it.",
      report_btn: "Report an issue", plan: "Plan a safe trip", quick: "Quick actions", how: "How it works", how1: "Snap it", how2: "AI checks it", how3: "Crew fixes it",
      how1d: "Take a photo of the damage", how2d: "We confirm and rate the risk", how3d: "Track every update here",
      latest: "Your latest report", days_open: "days open", day_open: "day open", today: "Reported today", view: "View details", fixed_on: "Fixed",
      s_issue: "Issue", s_photo: "Photo", s_loc: "Location", s_send: "Send", step_of: "Step {n} of 4",
      q_issue: "What is the problem?", q_photo: "Show us the damage", q_loc: "Where is it?", q_send: "Check and send",
      next: "Next", back: "Back", cancel: "Cancel", submit: "Send report", skip_photo: "Skip photo, describe it instead",
      take_photo: "Take photo", rec_video: "Record video", library: "Choose from gallery", add_more: "Add another",
      remove: "Remove", undo: "Undo", removed: "Photo removed", ai_check: "AI is checking...", ai_ok: "Damage found", ai_fail: "No damage seen", ai_err: "Check failed, tap to retry",
      photo_tip: "Stand about a metre back so the damage and some road are in the picture.",
      use_loc: "Use my location", finding: "Finding you...", loc_found: "Location found", loc_edit: "Or type the street or landmark", loc_label: "Place",
      details: "Add details (optional)", details_req: "Describe the problem", details_ph: "e.g. Deep pothole near the bus stop", your_name: "Your name", your_phone: "Mobile number",
      sum_issue: "Issue", sum_photos: "Photos", sum_place: "Place", none: "None",
      c_pothole: "Pothole", c_crack: "Cracks", c_waterlogging: "Waterlogging", c_broken_road: "Broken road", c_other: "Other",
      h_pothole: "Holes or craters", h_crack: "Surface cracking", h_waterlogging: "Flooded stretch", h_broken_road: "Caved or washed out", h_other: "Open manhole, debris",
      st_submitted: "Reported", st_in_review: "Verified", st_in_progress: "Repairing", st_resolved: "Fixed", st_rejected: "Closed",
      ok_title: "Report sent", ok_sub: "Thank you for making your road safer.", ticket: "Ticket", copy: "Copy", copied: "Copied", share: "Share",
      track: "Track this report", another: "Report another", saved_title: "Saved on this phone", saved_sub: "You are offline. We will send it as soon as you are back online.",
      share_text: "I reported a road problem on Disha AI. Ticket {t}.",
      e_offline: "You are offline. Connect to the internet and try again. Your report is safe on this phone.",
      e_server: "Our server is not answering right now. Try again in a minute.",
      e_gps: "Location is blocked. Tap the lock icon in the address bar, allow Location, then tap Use my location. Or type the street below.",
      e_gps_time: "Could not find you in time. Move outdoors and try again, or type the street.",
      e_need: "Add a photo or describe the problem to continue.", e_wait: "Checking your photos...", e_fail: "Remove or retake the photo that did not pass.", e_place: "Tap Use my location or type the street.",
      a2hs: "Add Disha AI to your home screen", a2hs_ios: "Tap Share, then Add to Home Screen.", a2hs_btn: "Install", dismiss: "Not now",
      empty_reports: "No reports yet", empty_reports_d: "Your reports will show up here once you send one.",
      sending: "Sending...", sent_wait: "Almost there..."
    },
    hi: {
      home: "होम", report: "रिपोर्ट", drive: "वीडियो जांच", map: "नक्शा", reports: "मेरी रिपोर्ट", alerts: "अलर्ट", profile: "प्रोफ़ाइल", talk: "दिशा से बात करें", lang: "भाषा",
      hero1: "सड़क ठीक करें,", hero2: "बहाने नहीं।", lede: "गड्ढे, दरार या जलभराव की फ़ोटो लें। दिशा AI जांचता है, शहर के नक्शे पर दिखाता है और मरम्मत दल तक भेजता है।",
      report_btn: "समस्या बताएं", plan: "सुरक्षित यात्रा चुनें", quick: "तुरंत करें", how: "यह कैसे काम करता है", how1: "फ़ोटो लें", how2: "AI जांचता है", how3: "दल ठीक करता है",
      how1d: "नुकसान की फ़ोटो लें", how2d: "हम पुष्टि कर जोखिम आंकते हैं", how3d: "हर अपडेट यहां देखें",
      latest: "आपकी ताज़ा रिपोर्ट", days_open: "दिन से खुली", day_open: "दिन से खुली", today: "आज दर्ज हुई", view: "विवरण देखें", fixed_on: "ठीक हुई",
      s_issue: "समस्या", s_photo: "फ़ोटो", s_loc: "जगह", s_send: "भेजें", step_of: "चरण {n} / 4",
      q_issue: "समस्या क्या है?", q_photo: "नुकसान दिखाएं", q_loc: "यह कहां है?", q_send: "जांचें और भेजें",
      next: "आगे", back: "पीछे", cancel: "रद्द करें", submit: "रिपोर्ट भेजें", skip_photo: "फ़ोटो छोड़ें, लिखकर बताएं",
      take_photo: "फ़ोटो लें", rec_video: "वीडियो बनाएं", library: "गैलरी से चुनें", add_more: "और जोड़ें",
      remove: "हटाएं", undo: "वापस लाएं", removed: "फ़ोटो हटाई गई", ai_check: "AI जांच रहा है...", ai_ok: "नुकसान मिला", ai_fail: "नुकसान नहीं दिखा", ai_err: "जांच विफल, दोबारा दबाएं",
      photo_tip: "एक मीटर दूर खड़े हों ताकि नुकसान और थोड़ी सड़क फ़ोटो में आए।",
      use_loc: "मेरी लोकेशन लें", finding: "लोकेशन खोज रहे हैं...", loc_found: "लोकेशन मिली", loc_edit: "या सड़क या पहचान की जगह लिखें", loc_label: "जगह",
      details: "विवरण जोड़ें (वैकल्पिक)", details_req: "समस्या लिखें", details_ph: "जैसे बस स्टॉप के पास गहरा गड्ढा", your_name: "आपका नाम", your_phone: "मोबाइल नंबर",
      sum_issue: "समस्या", sum_photos: "फ़ोटो", sum_place: "जगह", none: "कोई नहीं",
      c_pothole: "गड्ढा", c_crack: "दरारें", c_waterlogging: "जलभराव", c_broken_road: "टूटी सड़क", c_other: "अन्य",
      h_pothole: "गड्ढे या गहरे छेद", h_crack: "सतह में दरार", h_waterlogging: "पानी भरी सड़क", h_broken_road: "धंसी या बहती सड़क", h_other: "खुला मैनहोल, मलबा",
      st_submitted: "दर्ज", st_in_review: "जांची गई", st_in_progress: "मरम्मत जारी", st_resolved: "ठीक हुई", st_rejected: "बंद",
      ok_title: "रिपोर्ट भेज दी गई", ok_sub: "सड़क को सुरक्षित बनाने के लिए धन्यवाद।", ticket: "टिकट", copy: "कॉपी", copied: "कॉपी हुआ", share: "शेयर",
      track: "रिपोर्ट ट्रैक करें", another: "एक और रिपोर्ट", saved_title: "फ़ोन में सहेजा गया", saved_sub: "आप ऑफ़लाइन हैं। नेट आते ही हम इसे भेज देंगे।",
      share_text: "मैंने Disha AI पर सड़क की समस्या दर्ज की। टिकट {t}।",
      e_offline: "आप ऑफ़लाइन हैं। इंटरनेट जोड़कर दोबारा कोशिश करें। रिपोर्ट फ़ोन में सुरक्षित है।",
      e_server: "सर्वर अभी जवाब नहीं दे रहा। एक मिनट बाद फिर कोशिश करें।",
      e_gps: "लोकेशन बंद है। एड्रेस बार में ताले के आइकन पर दबाकर Location की अनुमति दें, फिर मेरी लोकेशन लें दबाएं। या नीचे सड़क लिखें।",
      e_gps_time: "समय पर लोकेशन नहीं मिली। खुली जगह जाकर फिर कोशिश करें, या सड़क लिखें।",
      e_need: "आगे बढ़ने के लिए फ़ोटो जोड़ें या समस्या लिखें।", e_wait: "फ़ोटो जांची जा रही हैं...", e_fail: "जो फ़ोटो पास नहीं हुई उसे हटाएं या दोबारा लें।", e_place: "मेरी लोकेशन लें दबाएं या सड़क लिखें।",
      a2hs: "Disha AI को होम स्क्रीन पर जोड़ें", a2hs_ios: "शेयर दबाएं, फिर Add to Home Screen चुनें।", a2hs_btn: "इंस्टॉल", dismiss: "अभी नहीं",
      empty_reports: "अभी कोई रिपोर्ट नहीं", empty_reports_d: "रिपोर्ट भेजने के बाद वह यहां दिखेगी।",
      sending: "भेज रहे हैं...", sent_wait: "बस थोड़ा और..."
    },
    kn: {
      home: "ಮುಖಪುಟ", report: "ವರದಿ", drive: "ವೀಡಿಯೊ ವಿಶ್ಲೇಷಣೆ", map: "ನಕ್ಷೆ", reports: "ನನ್ನ ವರದಿಗಳು", alerts: "ಎಚ್ಚರಿಕೆಗಳು", profile: "ಪ್ರೊಫೈಲ್", talk: "ದಿಶಾ ಜೊತೆ ಮಾತನಾಡಿ", lang: "ಭಾಷೆ",
      hero1: "ರಸ್ತೆ ಸರಿಪಡಿಸಿ,", hero2: "ನೆಪಗಳಲ್ಲ.", lede: "ಗುಂಡಿ, ಬಿರುಕು ಅಥವಾ ನೀರು ನಿಂತ ಜಾಗದ ಫೋಟೋ ತೆಗೆಯಿರಿ. ದಿಶಾ AI ಪರಿಶೀಲಿಸಿ, ನಗರದ ನಕ್ಷೆಯಲ್ಲಿ ಗುರುತಿಸಿ, ದುರಸ್ತಿ ತಂಡಕ್ಕೆ ಕಳುಹಿಸುತ್ತದೆ.",
      report_btn: "ಸಮಸ್ಯೆ ತಿಳಿಸಿ", plan: "ಸುರಕ್ಷಿತ ಪ್ರಯಾಣ", quick: "ತ್ವರಿತ ಕ್ರಿಯೆಗಳು", how: "ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ", how1: "ಫೋಟೋ ತೆಗೆಯಿರಿ", how2: "AI ಪರಿಶೀಲನೆ", how3: "ತಂಡ ಸರಿಪಡಿಸುತ್ತದೆ",
      how1d: "ಹಾನಿಯ ಫೋಟೋ ತೆಗೆಯಿರಿ", how2d: "ನಾವು ದೃಢೀಕರಿಸಿ ಅಪಾಯ ಅಳೆಯುತ್ತೇವೆ", how3d: "ಪ್ರತಿ ಅಪ್ಡೇಟ್ ಇಲ್ಲಿ ನೋಡಿ",
      latest: "ನಿಮ್ಮ ಇತ್ತೀಚಿನ ವರದಿ", days_open: "ದಿನಗಳಿಂದ ಬಾಕಿ", day_open: "ದಿನದಿಂದ ಬಾಕಿ", today: "ಇಂದು ದಾಖಲಾಗಿದೆ", view: "ವಿವರ ನೋಡಿ", fixed_on: "ಸರಿಪಡಿಸಲಾಗಿದೆ",
      s_issue: "ಸಮಸ್ಯೆ", s_photo: "ಫೋಟೋ", s_loc: "ಸ್ಥಳ", s_send: "ಕಳುಹಿಸಿ", step_of: "ಹಂತ {n} / 4",
      q_issue: "ಸಮಸ್ಯೆ ಏನು?", q_photo: "ಹಾನಿಯನ್ನು ತೋರಿಸಿ", q_loc: "ಇದು ಎಲ್ಲಿದೆ?", q_send: "ಪರಿಶೀಲಿಸಿ ಕಳುಹಿಸಿ",
      next: "ಮುಂದೆ", back: "ಹಿಂದೆ", cancel: "ರದ್ದು", submit: "ವರದಿ ಕಳುಹಿಸಿ", skip_photo: "ಫೋಟೋ ಬಿಟ್ಟು ವಿವರಿಸಿ",
      take_photo: "ಫೋಟೋ ತೆಗೆಯಿರಿ", rec_video: "ವೀಡಿಯೊ ರೆಕಾರ್ಡ್", library: "ಗ್ಯಾಲರಿಯಿಂದ ಆರಿಸಿ", add_more: "ಇನ್ನೊಂದು ಸೇರಿಸಿ",
      remove: "ತೆಗೆಯಿರಿ", undo: "ರದ್ದುಗೊಳಿಸಿ", removed: "ಫೋಟೋ ತೆಗೆಯಲಾಗಿದೆ", ai_check: "AI ಪರಿಶೀಲಿಸುತ್ತಿದೆ...", ai_ok: "ಹಾನಿ ಕಂಡಿದೆ", ai_fail: "ಹಾನಿ ಕಾಣಲಿಲ್ಲ", ai_err: "ಪರಿಶೀಲನೆ ವಿಫಲ, ಮತ್ತೆ ಒತ್ತಿ",
      photo_tip: "ಒಂದು ಮೀಟರ್ ದೂರ ನಿಂತು ಹಾನಿ ಮತ್ತು ಸ್ವಲ್ಪ ರಸ್ತೆ ಫೋಟೋದಲ್ಲಿ ಬರುವಂತೆ ತೆಗೆಯಿರಿ.",
      use_loc: "ನನ್ನ ಸ್ಥಳ ಬಳಸಿ", finding: "ಸ್ಥಳ ಹುಡುಕುತ್ತಿದೆ...", loc_found: "ಸ್ಥಳ ಸಿಕ್ಕಿದೆ", loc_edit: "ಅಥವಾ ರಸ್ತೆ ಹೆಸರು ಬರೆಯಿರಿ", loc_label: "ಸ್ಥಳ",
      details: "ವಿವರ ಸೇರಿಸಿ (ಐಚ್ಛಿಕ)", details_req: "ಸಮಸ್ಯೆ ವಿವರಿಸಿ", details_ph: "ಉದಾ. ಬಸ್ ನಿಲ್ದಾಣದ ಬಳಿ ಆಳವಾದ ಗುಂಡಿ", your_name: "ನಿಮ್ಮ ಹೆಸರು", your_phone: "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ",
      sum_issue: "ಸಮಸ್ಯೆ", sum_photos: "ಫೋಟೋಗಳು", sum_place: "ಸ್ಥಳ", none: "ಇಲ್ಲ",
      c_pothole: "ಗುಂಡಿ", c_crack: "ಬಿರುಕುಗಳು", c_waterlogging: "ನೀರು ನಿಂತಿದೆ", c_broken_road: "ಮುರಿದ ರಸ್ತೆ", c_other: "ಇತರೆ",
      h_pothole: "ಗುಂಡಿಗಳು", h_crack: "ಮೇಲ್ಮೈ ಬಿರುಕು", h_waterlogging: "ನೀರು ತುಂಬಿದ ಭಾಗ", h_broken_road: "ಕುಸಿದ ರಸ್ತೆ", h_other: "ತೆರೆದ ಮ್ಯಾನ್ಹೋಲ್, ಕಸ",
      st_submitted: "ದಾಖಲಾಗಿದೆ", st_in_review: "ಪರಿಶೀಲಿತ", st_in_progress: "ದುರಸ್ತಿ ನಡೆಯುತ್ತಿದೆ", st_resolved: "ಸರಿಪಡಿಸಲಾಗಿದೆ", st_rejected: "ಮುಚ್ಚಲಾಗಿದೆ",
      ok_title: "ವರದಿ ಕಳುಹಿಸಲಾಗಿದೆ", ok_sub: "ರಸ್ತೆಯನ್ನು ಸುರಕ್ಷಿತಗೊಳಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದ.", ticket: "ಟಿಕೆಟ್", copy: "ನಕಲಿಸಿ", copied: "ನಕಲಾಗಿದೆ", share: "ಹಂಚಿಕೊಳ್ಳಿ",
      track: "ವರದಿ ಟ್ರ್ಯಾಕ್ ಮಾಡಿ", another: "ಇನ್ನೊಂದು ವರದಿ", saved_title: "ಫೋನ್‌ನಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ", saved_sub: "ನೀವು ಆಫ್‌ಲೈನ್ ಇದ್ದೀರಿ. ನೆಟ್ ಬಂದ ಕೂಡಲೇ ಕಳುಹಿಸುತ್ತೇವೆ.",
      share_text: "ನಾನು Disha AI ನಲ್ಲಿ ರಸ್ತೆ ಸಮಸ್ಯೆ ವರದಿ ಮಾಡಿದ್ದೇನೆ. ಟಿಕೆಟ್ {t}.",
      e_offline: "ನೀವು ಆಫ್‌ಲೈನ್ ಇದ್ದೀರಿ. ಇಂಟರ್ನೆಟ್ ಸಂಪರ್ಕಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ. ವರದಿ ಫೋನ್‌ನಲ್ಲಿ ಸುರಕ್ಷಿತವಾಗಿದೆ.",
      e_server: "ಸರ್ವರ್ ಈಗ ಉತ್ತರಿಸುತ್ತಿಲ್ಲ. ಒಂದು ನಿಮಿಷದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
      e_gps: "ಸ್ಥಳ ನಿರ್ಬಂಧಿಸಲಾಗಿದೆ. ವಿಳಾಸ ಪಟ್ಟಿಯ ಲಾಕ್ ಐಕಾನ್ ಒತ್ತಿ Location ಅನುಮತಿಸಿ, ನಂತರ ನನ್ನ ಸ್ಥಳ ಬಳಸಿ ಒತ್ತಿ. ಅಥವಾ ರಸ್ತೆ ಹೆಸರು ಬರೆಯಿರಿ.",
      e_gps_time: "ಸಮಯಕ್ಕೆ ಸ್ಥಳ ಸಿಗಲಿಲ್ಲ. ಹೊರಗೆ ಹೋಗಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ, ಅಥವಾ ರಸ್ತೆ ಬರೆಯಿರಿ.",
      e_need: "ಮುಂದುವರಿಯಲು ಫೋಟೋ ಸೇರಿಸಿ ಅಥವಾ ಸಮಸ್ಯೆ ವಿವರಿಸಿ.", e_wait: "ಫೋಟೋ ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ...", e_fail: "ಪಾಸ್ ಆಗದ ಫೋಟೋ ತೆಗೆಯಿರಿ ಅಥವಾ ಮತ್ತೆ ತೆಗೆಯಿರಿ.", e_place: "ನನ್ನ ಸ್ಥಳ ಬಳಸಿ ಒತ್ತಿ ಅಥವಾ ರಸ್ತೆ ಬರೆಯಿರಿ.",
      a2hs: "Disha AI ಅನ್ನು ಹೋಮ್ ಸ್ಕ್ರೀನ್‌ಗೆ ಸೇರಿಸಿ", a2hs_ios: "ಶೇರ್ ಒತ್ತಿ, ನಂತರ Add to Home Screen ಆರಿಸಿ.", a2hs_btn: "ಇನ್‌ಸ್ಟಾಲ್", dismiss: "ಈಗ ಬೇಡ",
      empty_reports: "ಇನ್ನೂ ವರದಿಗಳಿಲ್ಲ", empty_reports_d: "ವರದಿ ಕಳುಹಿಸಿದ ನಂತರ ಇಲ್ಲಿ ಕಾಣುತ್ತದೆ.",
      sending: "ಕಳುಹಿಸಲಾಗುತ್ತಿದೆ...", sent_wait: "ಇನ್ನೇನು ಮುಗಿಯಿತು..."
    },
    mr: {
      home: "मुख्यपृष्ठ", report: "तक्रार", drive: "व्हिडिओ तपासणी", map: "नकाशा", reports: "माझ्या तक्रारी", alerts: "सूचना", profile: "प्रोफाइल", talk: "दिशाशी बोला", lang: "भाषा",
      hero1: "रस्ता दुरुस्त करा,", hero2: "सबबी नको.", lede: "खड्डा, भेग किंवा पाणी साचलेल्या जागेचा फोटो काढा. दिशा AI तपासते, शहराच्या नकाशावर दाखवते आणि दुरुस्ती पथकाकडे पाठवते.",
      report_btn: "समस्या नोंदवा", plan: "सुरक्षित प्रवास", quick: "जलद कृती", how: "हे कसे चालते", how1: "फोटो काढा", how2: "AI तपासते", how3: "पथक दुरुस्त करते",
      how1d: "नुकसानीचा फोटो काढा", how2d: "आम्ही खात्री करून धोका ठरवतो", how3d: "प्रत्येक अपडेट येथे पहा",
      latest: "तुमची ताजी तक्रार", days_open: "दिवस प्रलंबित", day_open: "दिवस प्रलंबित", today: "आज नोंदवली", view: "तपशील पहा", fixed_on: "दुरुस्त झाली",
      s_issue: "समस्या", s_photo: "फोटो", s_loc: "ठिकाण", s_send: "पाठवा", step_of: "पायरी {n} / 4",
      q_issue: "समस्या काय आहे?", q_photo: "नुकसान दाखवा", q_loc: "हे कुठे आहे?", q_send: "तपासा आणि पाठवा",
      next: "पुढे", back: "मागे", cancel: "रद्द करा", submit: "तक्रार पाठवा", skip_photo: "फोटो वगळा, लिहून सांगा",
      take_photo: "फोटो काढा", rec_video: "व्हिडिओ काढा", library: "गॅलरीतून निवडा", add_more: "आणखी जोडा",
      remove: "काढा", undo: "परत आणा", removed: "फोटो काढला", ai_check: "AI तपासत आहे...", ai_ok: "नुकसान आढळले", ai_fail: "नुकसान दिसले नाही", ai_err: "तपासणी अयशस्वी, पुन्हा दाबा",
      photo_tip: "एक मीटर मागे उभे राहा, म्हणजे नुकसान आणि थोडा रस्ता फोटोत येईल.",
      use_loc: "माझे ठिकाण वापरा", finding: "ठिकाण शोधत आहे...", loc_found: "ठिकाण मिळाले", loc_edit: "किंवा रस्ता किंवा खूण लिहा", loc_label: "ठिकाण",
      details: "तपशील जोडा (ऐच्छिक)", details_req: "समस्या लिहा", details_ph: "उदा. बस थांब्याजवळ खोल खड्डा", your_name: "तुमचे नाव", your_phone: "मोबाइल क्रमांक",
      sum_issue: "समस्या", sum_photos: "फोटो", sum_place: "ठिकाण", none: "काहीही नाही",
      c_pothole: "खड्डा", c_crack: "भेगा", c_waterlogging: "पाणी साचले", c_broken_road: "तुटलेला रस्ता", c_other: "इतर",
      h_pothole: "खड्डे किंवा खळगे", h_crack: "पृष्ठभागाला भेगा", h_waterlogging: "पाणी भरलेला भाग", h_broken_road: "खचलेला रस्ता", h_other: "उघडे मॅनहोल, कचरा",
      st_submitted: "नोंदवली", st_in_review: "तपासली", st_in_progress: "दुरुस्ती सुरू", st_resolved: "दुरुस्त", st_rejected: "बंद",
      ok_title: "तक्रार पाठवली", ok_sub: "रस्ता सुरक्षित केल्याबद्दल धन्यवाद.", ticket: "तिकीट", copy: "कॉपी", copied: "कॉपी केले", share: "शेअर",
      track: "तक्रार ट्रॅक करा", another: "आणखी एक तक्रार", saved_title: "फोनमध्ये जतन केले", saved_sub: "तुम्ही ऑफलाइन आहात. नेट येताच आम्ही पाठवू.",
      share_text: "मी Disha AI वर रस्त्याची समस्या नोंदवली. तिकीट {t}.",
      e_offline: "तुम्ही ऑफलाइन आहात. इंटरनेट जोडून पुन्हा प्रयत्न करा. तक्रार फोनमध्ये सुरक्षित आहे.",
      e_server: "सर्व्हर आत्ता उत्तर देत नाही. एका मिनिटाने पुन्हा प्रयत्न करा.",
      e_gps: "लोकेशन बंद आहे. अॅड्रेस बारमधील कुलूप चिन्ह दाबून Location परवानगी द्या, मग माझे ठिकाण वापरा दाबा. किंवा खाली रस्ता लिहा.",
      e_gps_time: "वेळेत ठिकाण मिळाले नाही. मोकळ्या जागी जाऊन पुन्हा प्रयत्न करा, किंवा रस्ता लिहा.",
      e_need: "पुढे जाण्यासाठी फोटो जोडा किंवा समस्या लिहा.", e_wait: "फोटो तपासले जात आहेत...", e_fail: "जो फोटो पास झाला नाही तो काढा किंवा पुन्हा घ्या.", e_place: "माझे ठिकाण वापरा दाबा किंवा रस्ता लिहा.",
      a2hs: "Disha AI होम स्क्रीनवर जोडा", a2hs_ios: "शेअर दाबा, मग Add to Home Screen निवडा.", a2hs_btn: "इन्स्टॉल", dismiss: "आत्ता नाही",
      empty_reports: "अजून तक्रारी नाहीत", empty_reports_d: "तक्रार पाठवल्यावर ती येथे दिसेल.",
      sending: "पाठवत आहे...", sent_wait: "जवळजवळ झाले..."
    }
  };
  var cur = "en";
  try { var s = localStorage.getItem("rw-lang"); if (s && D[s]) cur = s; } catch (e) {}
  function T(k, v) {
    var s = (D[cur] && D[cur][k]) || D.en[k] || k;
    if (v) for (var p in v) s = s.replace("{" + p + "}", v[p]);
    return s;
  }
  function apply() {
    document.documentElement.lang = cur;
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n]"), function (e) { e.textContent = T(e.getAttribute("data-i18n")); });
    Array.prototype.forEach.call(document.querySelectorAll("[data-i18n-label]"), function (e) { e.setAttribute("aria-label", T(e.getAttribute("data-i18n-label"))); });
    var b = document.getElementById("lang-btn"); if (b) { var l = LANGS.filter(function (x) { return x.code === cur; })[0]; b.querySelector("span").textContent = l ? l.short : "EN"; b.setAttribute("aria-label", T("lang") + ": " + (l ? l.native : "English")); }
  }
  function set(c) {
    if (!D[c]) return; cur = c;
    try { localStorage.setItem("rw-lang", c); localStorage.setItem("rw-call-lang", c); } catch (e) {}
    apply();
  }
  window.T = T;
  window.I18N = { langs: LANGS, get: function () { return cur; }, set: set, apply: apply };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply); else apply();
})();
