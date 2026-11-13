"""In-app voice call with the Disha AI assistant (web and phone app).

The browser or the app does speech to text and text to speech on the device (free, works offline from our servers);
this module is the assistant's brain: a small dialogue manager that walks the caller through a road complaint,
in English, Hindi, Kannada or Marathi, and asks for the camera when it is time to show the damage.

Endpoints
  POST /api/call/start  {lang, lat, lon, device_id}        -> {session_id, say, stage, expect, fields, suggest}
  POST /api/call/turn   {session_id, text}                 -> same shape, plus done=true at the end
        text "__media__:<n>:<pass|fail>" tells the assistant the caller captured n photos or clips
  GET  /api/call/session/{id}                              -> the collected fields (for the client to file the complaint)
The client files the complaint itself with POST /api/complaints (files + screening tokens) using `fields`.
Sessions live in memory for 30 minutes.
"""
import re
import threading
import time
import uuid
from typing import Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

LANGS = ("en", "hi", "kn", "mr")
SESSIONS: dict = {}
_lock = threading.Lock()
TTL_S = 1800

# ---------------------------------------------------------------- phrases
T = {
    "greet": {
        "en": "Hello, I am Disha, your road assistant. Tell me what is wrong with the road, a pothole, cracks, water on the road, or an open manhole.",
        "hi": "नमस्ते, मैं दिशा हूँ, आपकी सड़क सहायक। बताइए सड़क में क्या दिक्कत है, गड्ढा, दरार, पानी भरा हुआ या खुला मैनहोल?",
        "kn": "ನಮಸ್ಕಾರ, ನಾನು ದಿಶಾ, ನಿಮ್ಮ ರಸ್ತೆ ಸಹಾಯಕಿ. ರಸ್ತೆಯಲ್ಲಿ ಏನು ಸಮಸ್ಯೆ ಇದೆ ಹೇಳಿ, ಗುಂಡಿ, ಬಿರುಕು, ನೀರು ನಿಂತಿದೆಯಾ ಅಥವಾ ತೆರೆದ ಮ್ಯಾನ್‌ಹೋಲ್?",
        "mr": "नमस्कार, मी दिशा, तुमची रस्ता सहाय्यक. रस्त्यात काय अडचण आहे सांगा, खड्डा, तडे, पाणी साचले आहे की उघडे मॅनहोल?",
    },
    "didnt_get_issue": {
        "en": "Sorry, I did not catch the problem. Is it a pothole, cracks, water on the road, or a manhole?",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाई। क्या यह गड्ढा है, दरार है, पानी भरा है या मैनहोल?",
        "kn": "ಕ್ಷಮಿಸಿ, ಅರ್ಥವಾಗಲಿಲ್ಲ. ಇದು ಗುಂಡಿಯೇ, ಬಿರುಕೇ, ನೀರು ನಿಂತಿದೆಯೇ ಅಥವಾ ಮ್ಯಾನ್‌ಹೋಲ್ ಆಗಿದೆಯೇ?",
        "mr": "माफ करा, मला समजले नाही. हा खड्डा आहे, तडे आहेत, पाणी साचले आहे की मॅनहोल?",
    },
    "loc_found": {
        "en": "I can see you are near {place}. Is the problem at this spot?",
        "hi": "मुझे दिख रहा है कि आप {place} के पास हैं। क्या समस्या इसी जगह पर है?",
        "kn": "ನೀವು {place} ಹತ್ತಿರ ಇದ್ದೀರಿ ಎಂದು ತೋರುತ್ತಿದೆ. ಸಮಸ್ಯೆ ಇದೇ ಜಾಗದಲ್ಲಿದೆಯೇ?",
        "mr": "तुम्ही {place} जवळ आहात असे दिसते. समस्या याच ठिकाणी आहे का?",
    },
    "loc_found_nogeo": {
        "en": "I have your GPS location. Is the problem at this spot?",
        "hi": "मेरे पास आपकी GPS लोकेशन है। क्या समस्या इसी जगह पर है?",
        "kn": "ನನಗೆ ನಿಮ್ಮ GPS ಸ್ಥಳ ಸಿಕ್ಕಿದೆ. ಸಮಸ್ಯೆ ಇದೇ ಜಾಗದಲ್ಲಿದೆಯೇ?",
        "mr": "माझ्याकडे तुमचे GPS लोकेशन आहे. समस्या याच ठिकाणी आहे का?",
    },
    "loc_none": {
        "en": "I could not get your location. Please tell me the road name and the area.",
        "hi": "मुझे आपकी लोकेशन नहीं मिली। कृपया सड़क का नाम और इलाका बताइए।",
        "kn": "ನಿಮ್ಮ ಸ್ಥಳ ಸಿಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ರಸ್ತೆಯ ಹೆಸರು ಮತ್ತು ಪ್ರದೇಶ ಹೇಳಿ.",
        "mr": "तुमचे लोकेशन मिळाले नाही. कृपया रस्त्याचे नाव आणि परिसर सांगा.",
    },
    "ask_place": {
        "en": "Okay. Please tell me the road name and the area.",
        "hi": "ठीक है। कृपया सड़क का नाम और इलाका बताइए।",
        "kn": "ಸರಿ. ದಯವಿಟ್ಟು ರಸ್ತೆಯ ಹೆಸರು ಮತ್ತು ಪ್ರದೇಶ ಹೇಳಿ.",
        "mr": "ठीक आहे. कृपया रस्त्याचे नाव आणि परिसर सांगा.",
    },
    "ask_landmark": {
        "en": "Is there a landmark nearby, like a shop, school, temple or bus stop? You can say skip.",
        "hi": "क्या पास में कोई निशानी है, जैसे दुकान, स्कूल, मंदिर या बस स्टॉप? आप स्किप भी कह सकते हैं।",
        "kn": "ಹತ್ತಿರದಲ್ಲಿ ಅಂಗಡಿ, ಶಾಲೆ, ದೇವಸ್ಥಾನ ಅಥವಾ ಬಸ್ ನಿಲ್ದಾಣದಂತಹ ಗುರುತು ಇದೆಯೇ? ಬೇಕಿದ್ದರೆ ಸ್ಕಿಪ್ ಎನ್ನಿ.",
        "mr": "जवळ दुकान, शाळा, मंदिर किंवा बस स्टॉप अशी खूण आहे का? तुम्ही स्किप म्हणू शकता.",
    },
    "ask_severity": {
        "en": "How bad is it? Small, big, deep, full of water, or has anyone fallen or been hurt?",
        "hi": "यह कितना खराब है? छोटा, बड़ा, गहरा, पानी भरा हुआ, या कोई गिरा या घायल हुआ है?",
        "kn": "ಎಷ್ಟು ಕೆಟ್ಟದಾಗಿದೆ? ಸಣ್ಣದೋ, ದೊಡ್ಡದೋ, ಆಳವೋ, ನೀರು ತುಂಬಿದೆಯೋ, ಅಥವಾ ಯಾರಾದರೂ ಬಿದ್ದಿದ್ದಾರೆಯೇ?",
        "mr": "किती खराब आहे? लहान, मोठा, खोल, पाणी भरलेला, की कोणी पडले किंवा जखमी झाले?",
    },
    "ask_media": {
        "en": "Thank you. Now please point your camera at the damage so I can see it. Take a photo or a short video, and I will check it.",
        "hi": "धन्यवाद। अब कृपया कैमरा नुकसान की तरफ कीजिए ताकि मैं देख सकूँ। फोटो या छोटा वीडियो लीजिए, मैं जाँच लूँगी।",
        "kn": "ಧನ್ಯವಾದ. ಈಗ ದಯವಿಟ್ಟು ಹಾನಿಯ ಕಡೆ ಕ್ಯಾಮೆರಾ ತೋರಿಸಿ. ಫೋಟೋ ಅಥವಾ ಚಿಕ್ಕ ವೀಡಿಯೊ ತೆಗೆಯಿರಿ, ನಾನು ಪರಿಶೀಲಿಸುತ್ತೇನೆ.",
        "mr": "धन्यवाद. आता कृपया कॅमेरा नुकसानीकडे धरा म्हणजे मला दिसेल. फोटो किंवा छोटा व्हिडिओ घ्या, मी तपासते.",
    },
    "media_pass": {
        "en": "I can see the road damage clearly. That helps the repair team a lot. May I have your name for the complaint? You can say skip.",
        "hi": "मुझे सड़क का नुकसान साफ़ दिख रहा है। इससे मरम्मत टीम को बहुत मदद मिलेगी। शिकायत के लिए आपका नाम क्या है? आप स्किप भी कह सकते हैं।",
        "kn": "ರಸ್ತೆಯ ಹಾನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕಾಣುತ್ತಿದೆ. ಇದು ದುರಸ್ತಿ ತಂಡಕ್ಕೆ ತುಂಬಾ ಸಹಾಯ ಮಾಡುತ್ತದೆ. ದೂರಿಗಾಗಿ ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ. ಬೇಕಿದ್ದರೆ ಸ್ಕಿಪ್ ಎನ್ನಿ.",
        "mr": "मला रस्त्याचे नुकसान स्पष्ट दिसत आहे. यामुळे दुरुस्ती पथकाला खूप मदत होईल. तक्रारीसाठी तुमचे नाव सांगा. तुम्ही स्किप म्हणू शकता.",
    },
    "media_fail": {
        "en": "I could not see road damage in that shot. Please move closer to the damage and try again, or say skip to continue without a photo.",
        "hi": "उस तस्वीर में मुझे सड़क का नुकसान नहीं दिखा। कृपया नुकसान के पास जाकर फिर से लीजिए, या बिना फोटो के आगे बढ़ने के लिए स्किप कहिए।",
        "kn": "ಆ ಚಿತ್ರದಲ್ಲಿ ರಸ್ತೆಯ ಹಾನಿ ಕಾಣಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಹಾನಿಯ ಹತ್ತಿರ ಹೋಗಿ ಮತ್ತೆ ತೆಗೆಯಿರಿ, ಅಥವಾ ಫೋಟೋ ಇಲ್ಲದೆ ಮುಂದುವರಿಯಲು ಸ್ಕಿಪ್ ಎನ್ನಿ.",
        "mr": "त्या फोटोत मला रस्त्याचे नुकसान दिसले नाही. कृपया नुकसानीच्या जवळ जाऊन पुन्हा घ्या, किंवा फोटोशिवाय पुढे जाण्यासाठी स्किप म्हणा.",
    },
    "ask_name": {
        "en": "May I have your name for the complaint? You can say skip.",
        "hi": "शिकायत के लिए आपका नाम क्या है? आप स्किप भी कह सकते हैं।",
        "kn": "ದೂರಿಗಾಗಿ ನಿಮ್ಮ ಹೆಸರು ಹೇಳಿ. ಬೇಕಿದ್ದರೆ ಸ್ಕಿಪ್ ಎನ್ನಿ.",
        "mr": "तक्रारीसाठी तुमचे नाव सांगा. तुम्ही स्किप म्हणू शकता.",
    },
    "confirm": {
        "en": "Let me confirm. A {issue} at {place}. {sev} Shall I register this complaint?",
        "hi": "मैं पुष्टि कर लूँ। {place} पर {issue}। {sev} क्या मैं यह शिकायत दर्ज कर दूँ?",
        "kn": "ದೃಢಪಡಿಸುತ್ತೇನೆ. {place} ನಲ್ಲಿ {issue}. {sev} ಈ ದೂರನ್ನು ದಾಖಲಿಸಲೇ?",
        "mr": "मी खात्री करते. {place} येथे {issue}. {sev} ही तक्रार नोंदवू का?",
    },
    "done": {
        "en": "Done. Your complaint is registered. Thank you for helping fix the road. Stay safe.",
        "hi": "हो गया। आपकी शिकायत दर्ज हो गई है। सड़क ठीक कराने में मदद के लिए धन्यवाद। सुरक्षित रहिए।",
        "kn": "ಆಯಿತು. ನಿಮ್ಮ ದೂರು ದಾಖಲಾಗಿದೆ. ರಸ್ತೆ ಸರಿಪಡಿಸಲು ಸಹಾಯ ಮಾಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದ. ಸುರಕ್ಷಿತವಾಗಿರಿ.",
        "mr": "झाले. तुमची तक्रार नोंदवली आहे. रस्ता दुरुस्त करण्यात मदत केल्याबद्दल धन्यवाद. सुरक्षित रहा.",
    },
    "cancelled": {
        "en": "Okay, I have not registered anything. You can call me again any time. Goodbye.",
        "hi": "ठीक है, मैंने कुछ दर्ज नहीं किया। आप कभी भी फिर बुला सकते हैं। नमस्ते।",
        "kn": "ಸರಿ, ನಾನು ಏನನ್ನೂ ದಾಖಲಿಸಿಲ್ಲ. ಯಾವಾಗ ಬೇಕಾದರೂ ಮತ್ತೆ ಕರೆ ಮಾಡಿ. ನಮಸ್ಕಾರ.",
        "mr": "ठीक आहे, मी काहीही नोंदवले नाही. तुम्ही केव्हाही पुन्हा बोलावू शकता. नमस्कार.",
    },
    "emergency": {
        "en": "That sounds dangerous. If anyone is hurt, please call 112 now. I will mark this complaint as urgent.",
        "hi": "यह खतरनाक लगता है। अगर कोई घायल है तो अभी 112 पर कॉल कीजिए। मैं इस शिकायत को अत्यावश्यक चिह्नित कर दूँगी।",
        "kn": "ಇದು ಅಪಾಯಕಾರಿ ಎನಿಸುತ್ತದೆ. ಯಾರಾದರೂ ಗಾಯಗೊಂಡಿದ್ದರೆ ಈಗಲೇ 112 ಗೆ ಕರೆ ಮಾಡಿ. ಈ ದೂರನ್ನು ತುರ್ತು ಎಂದು ಗುರುತಿಸುತ್ತೇನೆ.",
        "mr": "हे धोकादायक वाटते. कोणी जखमी असेल तर आत्ताच 112 वर कॉल करा. मी ही तक्रार तातडीची म्हणून नोंदवते.",
    },
    "yesno": {
        "en": "Please say yes or no.", "hi": "कृपया हाँ या ना कहिए।", "kn": "ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎನ್ನಿ.", "mr": "कृपया होय किंवा नाही म्हणा.",
    },
}
ISSUE_NAME = {
    "pothole": {"en": "pothole", "hi": "गड्ढा", "kn": "ಗುಂಡಿ", "mr": "खड्डा"},
    "crack": {"en": "road crack", "hi": "सड़क में दरार", "kn": "ರಸ್ತೆ ಬಿರುಕು", "mr": "रस्त्यात तडे"},
    "waterlogging": {"en": "waterlogging", "hi": "जलभराव", "kn": "ನೀರು ನಿಂತಿರುವುದು", "mr": "पाणी साचणे"},
    "manhole": {"en": "open manhole", "hi": "खुला मैनहोल", "kn": "ತೆರೆದ ಮ್ಯಾನ್‌ಹೋಲ್", "mr": "उघडे मॅनहोल"},
    "broken_road": {"en": "broken road", "hi": "टूटी सड़क", "kn": "ಹಾಳಾದ ರಸ್ತೆ", "mr": "खराब रस्ता"},
    "other": {"en": "road problem", "hi": "सड़क की समस्या", "kn": "ರಸ್ತೆ ಸಮಸ್ಯೆ", "mr": "रस्त्याची समस्या"},
}
SEV_TEXT = {
    "small": {"en": "It is small.", "hi": "यह छोटा है।", "kn": "ಇದು ಸಣ್ಣದು.", "mr": "हे लहान आहे."},
    "large": {"en": "It is big or deep.", "hi": "यह बड़ा या गहरा है।", "kn": "ಇದು ದೊಡ್ಡದು ಅಥವಾ ಆಳವಾದದ್ದು.", "mr": "हे मोठे किंवा खोल आहे."},
    "water": {"en": "It is full of water.", "hi": "इसमें पानी भरा है।", "kn": "ಇದರಲ್ಲಿ ನೀರು ತುಂಬಿದೆ.", "mr": "यात पाणी भरले आहे."},
    "dangerous": {"en": "Someone fell or it is dangerous.", "hi": "कोई गिरा है या यह खतरनाक है।", "kn": "ಯಾರೋ ಬಿದ್ದಿದ್ದಾರೆ ಅಥವಾ ಇದು ಅಪಾಯಕಾರಿ.", "mr": "कोणी पडले आहे किंवा हे धोकादायक आहे."},
    "unknown": {"en": "", "hi": "", "kn": "", "mr": ""},
}
SEV_URGENCY = {"small": "low", "large": "normal", "water": "normal", "dangerous": "high", "unknown": "normal"}

# ---------------------------------------------------------------- understanding
ISSUES = {
    "manhole": ["manhole", "man hole", "gutter", "drain cover", "मैनहोल", "ढक्कन", "गटर", "ಮ್ಯಾನ್", "ಮ್ಯಾನ್‌ಹೋಲ್", "मॅनहोल", "झाकण"],
    "waterlogging": ["water", "waterlog", "flood", "puddle", "paani", "pani", "पानी", "जलभराव", "भराव", "पाणी", "साचले", "ನೀರು", "ನಿಂತ"],
    "crack": ["crack", "cracks", "split", "daraar", "darar", "दरार", "तडे", "तड", "ಬಿರುಕು", "ಬಿರುಕ"],
    "pothole": ["pothole", "pot hole", "hole", "pit", "gaddha", "gadda", "khadda", "गड्ढा", "गड्ढे", "खड्डा", "खड्डे", "ಗುಂಡಿ", "ಗುಂಡಿಗಳು"],
    "broken_road": ["broken", "damaged", "destroyed", "tuti", "टूटी", "खराब रस्ता", "ಹಾಳಾದ", "ಹಾಳು"],
}
YES = ["yes", "yeah", "yep", "correct", "right", "ok", "okay", "sure", "haan", "han", "ha", "हाँ", "हां", "जी", "ठीक", "सही", "होय", "हो", "ಹೌದು", "ಸರಿ", "ಹೌದ"]
NO = ["no", "nope", "not", "wrong", "nahi", "nahin", "नहीं", "ना", "नही", "नाही", "नको", "ಇಲ್ಲ", "ಅಲ್ಲ"]
SKIP = ["skip", "pass", "dont know", "don't know", "no idea", "pata nahi", "नहीं पता", "पता नहीं", "स्किप", "माहित नाही", "माहीत नाही", "ಗೊತ್ತಿಲ್ಲ", "ಸ್ಕಿಪ್", "nothing"]
CANCEL = ["cancel", "stop", "exit", "bye", "goodbye", "रद्द", "बंद", "अलविदा", "ರದ್ದು", "ಬೇಡ", "रद्द करा"]
SEV_KW = {
    "dangerous": ["fell", "fallen", "accident", "hurt", "injur", "died", "dangerous", "bike skid", "गिर", "घायल", "दुर्घटना", "खतरनाक", "पडल", "जखमी", "अपघात", "ಬಿದ್ದ", "ಗಾಯ", "ಅಪಘಾತ", "ಅಪಾಯ"],
    "water": ["water filled", "full of water", "waterlog", "puddle", "पानी भरा", "पाणी भर", "ನೀರು ತುಂಬ"],
    "large": ["big", "large", "huge", "deep", "wide", "bada", "बड़ा", "बड़े", "गहरा", "गहरे", "मोठा", "खोल", "ದೊಡ್ಡ", "ಆಳ"],
    "small": ["small", "tiny", "little", "minor", "chhota", "छोटा", "छोटे", "लहान", "ಸಣ್ಣ", "ಚಿಕ್ಕ"],
}


def _has(text, words):
    t = text.lower()
    return any(w in t for w in words)


def _issue(text):
    for k, words in ISSUES.items():
        if _has(text, words):
            return k
    return None


def _severity(text):
    for k in ("dangerous", "water", "large", "small"):
        if _has(text, SEV_KW[k]):
            return k
    return None


def _yn(text):
    t = " " + text.lower().strip() + " "
    if _has(t, SKIP) and not _has(t, YES):
        return None
    y = any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in YES)
    n = any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in NO)
    if y and not n:
        return True
    if n and not y:
        return False
    return None


def _say(key, lang, **kw):
    return T[key].get(lang, T[key]["en"]).format(**kw)


def _geocode(lat, lon):
    try:
        r = httpx.get("https://nominatim.openstreetmap.org/reverse", timeout=8, headers={"User-Agent": "Disha AI/1.0 (municipal road monitoring)"},
                      params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1})
        a = (r.json() or {}).get("address", {})
        road = a.get("road") or a.get("pedestrian") or a.get("residential")
        area = a.get("suburb") or a.get("neighbourhood") or a.get("village") or a.get("town")
        city = a.get("city") or a.get("town") or a.get("county") or a.get("state_district")
        parts = [p for p in (road, area, city) if p]
        return ", ".join(dict.fromkeys(parts))[:160] or None
    except Exception:
        return None


# ---------------------------------------------------------------- dialogue
def _reply(sess, say, expect="speech", suggest=None, done=False):
    sess["last"] = time.time()
    f = sess["fields"]
    return {"session_id": sess["id"], "say": say, "lang": sess["lang"], "stage": sess["stage"], "expect": expect,
            "suggest": suggest or [], "done": done,
            "fields": {k: f.get(k) for k in ("category", "issue_label", "place", "address", "lat", "lon", "landmark", "severity", "urgency",
                                           "name", "description", "media_count", "media_ok")}}


def _compose(sess):
    f, lang = sess["fields"], sess["lang"]
    bits = [f"{ISSUE_NAME[f['category']]['en']} reported by voice call"]
    if f.get("landmark"):
        lm = f["landmark"]
        bits.append(lm if re.match(r"(?i)(near|opposite|behind|next to|beside|in front of)", lm) else f"near {lm}")
    if f.get("severity") and f["severity"] != "unknown":
        bits.append(SEV_TEXT[f["severity"]]["en"].strip(" ."))
    if f.get("urgency") == "high":
        bits.append("URGENT: someone may have been hurt")
    return ". ".join(bits)[:480]


def _after_issue(sess):
    f, lang = sess["fields"], sess["lang"]
    if f.get("lat") is not None:
        sess["stage"] = "confirm_location"
        if f.get("place"):
            return _reply(sess, _say("loc_found", lang, place=f["place"]), suggest=["Yes", "No"])
        return _reply(sess, _say("loc_found_nogeo", lang), suggest=["Yes", "No"])
    sess["stage"] = "ask_place"
    return _reply(sess, _say("loc_none", lang))


def _handle(sess, text):
    f, lang, st = sess["fields"], sess["lang"], sess["stage"]
    text = (text or "").strip()
    if _has(text, CANCEL) and st not in ("ask_place", "ask_landmark", "ask_name"):
        sess["stage"] = "cancelled"
        return _reply(sess, _say("cancelled", lang), expect="none", done=True)
    if st == "ask_issue":
        issue = _issue(text)
        if not issue:
            return _reply(sess, _say("didnt_get_issue", lang), suggest=["Pothole", "Cracks", "Water on road", "Manhole"])
        f["category"] = issue
        f["issue_label"] = ISSUE_NAME[issue][lang]
        sev = _severity(text)
        if sev:
            f["severity"], f["urgency"] = sev, SEV_URGENCY[sev]
        prefix = _say("emergency", lang) + " " if sev == "dangerous" else ""
        r = _after_issue(sess)
        r["say"] = prefix + r["say"]
        return r
    if st == "confirm_location":
        yn = _yn(text)
        if yn is None:
            return _reply(sess, _say("yesno", lang), suggest=["Yes", "No"])
        if yn:
            sess["stage"] = "ask_landmark"
            return _reply(sess, _say("ask_landmark", lang), suggest=["Skip"])
        sess["stage"] = "ask_place"
        return _reply(sess, _say("ask_place", lang))
    if st == "ask_place":
        if text and not _has(text, SKIP):
            f["place"] = text[:120]
            f["address"] = text[:200]
        sess["stage"] = "ask_landmark"
        return _reply(sess, _say("ask_landmark", lang), suggest=["Skip"])
    if st == "ask_landmark":
        if text and not _has(text, SKIP):
            f["landmark"] = text[:100]
        if f.get("severity"):
            sess["stage"] = "ask_media"
            return _reply(sess, _say("ask_media", lang), expect="camera", suggest=["Skip"])
        sess["stage"] = "ask_severity"
        return _reply(sess, _say("ask_severity", lang), suggest=["Small", "Big", "Deep", "Someone fell"])
    if st == "ask_severity":
        sev = _severity(text) or "unknown"
        f["severity"], f["urgency"] = sev, SEV_URGENCY[sev]
        prefix = _say("emergency", lang) + " " if sev == "dangerous" else ""
        sess["stage"] = "ask_media"
        return _reply(sess, prefix + _say("ask_media", lang), expect="camera", suggest=["Skip"])
    if st == "ask_media":
        m = re.match(r"__media__:(\d+):(pass|fail)", text)
        if m:
            f["media_count"], f["media_ok"] = int(m.group(1)), m.group(2) == "pass"
            if f["media_ok"]:
                sess["stage"] = "ask_name"
                return _reply(sess, _say("media_pass", lang), suggest=["Skip"])
            return _reply(sess, _say("media_fail", lang), expect="camera", suggest=["Skip"])
        if _has(text, SKIP):
            f["media_count"], f["media_ok"] = 0, False
            sess["stage"] = "ask_name"
            return _reply(sess, _say("ask_name", lang), suggest=["Skip"])
        return _reply(sess, _say("ask_media", lang), expect="camera", suggest=["Skip"])
    if st == "ask_name":
        if text and not _has(text, SKIP):
            f["name"] = re.sub(r"^(my name is|i am|i'm|mera naam|मेरा नाम|माझे नाव|ನನ್ನ ಹೆಸರು)\s*", "", text, flags=re.I)[:60]
        f["description"] = _compose(sess)
        sess["stage"] = "confirm"
        sev = SEV_TEXT.get(f.get("severity") or "unknown", SEV_TEXT["unknown"])[lang]
        return _reply(sess, _say("confirm", lang, issue=ISSUE_NAME[f["category"]][lang], place=f.get("place") or f.get("landmark") or "this location", sev=sev),
                      suggest=["Yes", "No"])
    if st == "confirm":
        yn = _yn(text)
        if yn is None:
            return _reply(sess, _say("yesno", lang), suggest=["Yes", "No"])
        if yn:
            sess["stage"] = "done"
            return _reply(sess, _say("done", lang), expect="none", done=True)
        sess["stage"] = "cancelled"
        return _reply(sess, _say("cancelled", lang), expect="none", done=True)
    return _reply(sess, _say("done", lang), expect="none", done=True)


class StartBody(BaseModel):
    lang: str = "en"
    lat: Optional[float] = None
    lon: Optional[float] = None
    device_id: Optional[str] = None


class TurnBody(BaseModel):
    session_id: str
    text: str = ""


def _purge():
    cut = time.time() - TTL_S
    for k in [k for k, v in SESSIONS.items() if v["last"] < cut]:
        SESSIONS.pop(k, None)


def register(app):
    @app.post("/api/call/start")
    def call_start(body: StartBody):
        lang = body.lang if body.lang in LANGS else "en"
        lat = body.lat if body.lat is not None and -90 <= body.lat <= 90 else None
        lon = body.lon if body.lon is not None and -180 <= body.lon <= 180 else None
        place = _geocode(lat, lon) if lat is not None and lon is not None else None
        sid = uuid.uuid4().hex
        sess = {"id": sid, "lang": lang, "stage": "ask_issue", "last": time.time(), "device_id": body.device_id,
                "fields": {"lat": lat, "lon": lon, "place": place, "address": place}}
        with _lock:
            _purge()
            SESSIONS[sid] = sess
        return _reply(sess, _say("greet", lang), suggest=["Pothole", "Cracks", "Water on road", "Manhole"])

    @app.post("/api/call/turn")
    def call_turn(body: TurnBody):
        sess = SESSIONS.get(body.session_id)
        if not sess:
            raise HTTPException(404, "This call has ended. Please start a new one.")
        with _lock:
            return _handle(sess, body.text[:500])

    @app.get("/api/call/session/{sid}")
    def call_session(sid: str):
        sess = SESSIONS.get(sid)
        if not sess:
            raise HTTPException(404, "Call not found")
        return _reply(sess, "", expect="none", done=sess["stage"] in ("done", "cancelled"))
