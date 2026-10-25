"""
chatbot.py — Keyword-based FAQ matching engine for Smart College Assistant.

Pipeline:
  normalize → tokenize → remove stopwords → synonym expand → score all FAQs
  → return best match above threshold, or fallback
"""

import re
import string
import random
from database import get_all_faqs

THRESHOLD = 0.28
MAX_LEN   = 500

FALLBACK = [
    "I'm sorry, I couldn't find a reliable answer to that question. "
    "Please try rephrasing it, or contact the college administration for assistance.",
    "I don't have information on that topic yet. "
    "Please visit the college website or contact the administrative office directly.",
    "That question is outside my current knowledge. "
    "For accurate information, please speak to the relevant college department.",
    "I wasn't able to match your question to any of our FAQs. "
    "Try using different keywords, or contact the college helpdesk.",
]

STOPWORDS = {
    "a","an","the","is","are","was","were","be","been","being","have","has","had",
    "do","does","did","will","would","could","should","may","might","shall","can",
    "to","of","in","on","at","by","for","with","about","from","into","through",
    "during","before","after","above","below","up","down","out","off","over",
    "again","then","here","there","when","where","why","how","all","both","each",
    "more","most","other","some","such","no","nor","not","only","same","so","than",
    "too","very","just","as","until","while","i","me","my","we","our","you","your",
    "he","him","his","she","her","it","its","they","them","their","what","which",
    "who","this","that","these","those","and","but","or","if","because","though",
    "am","get","got","want","know","like","go","tell","say","make","see","also",
    "please","hi","hello","hey","s","t",
}

SYNONYMS = {
    # admissions
    "apply": "admission", "applying": "admission", "applied": "admission",
    "enroll": "admission", "enrolling": "admission", "enrollment": "admission",
    "join": "admission", "joining": "admission",
    "register": "admission", "registration": "admission",
    "intake": "admission", "admit": "admission",
    # courses
    "course": "courses", "program": "courses", "programme": "courses",
    "programmes": "courses", "degree": "courses",
    "subject": "courses", "subjects": "courses", "stream": "courses",
    # fees
    "fee": "fees", "tuition": "fees", "cost": "fees",
    "charges": "fees", "payment": "fees", "pay": "fees", "paying": "fees",
    "amount": "fees",
    # examinations
    "exam": "examination", "exams": "examination", "test": "examination",
    "tests": "examination",
    "timetable": "schedule", "datesheet": "schedule", "schedule": "schedule",
    # results
    "result": "results", "marks": "results", "grade": "results",
    "grades": "results", "score": "results", "marksheet": "results",
    # library
    "lib": "library", "books": "library", "reading": "library",
    # hostel
    "hostel": "accommodation", "boarding": "accommodation",
    "residence": "accommodation", "dormitory": "accommodation", "room": "accommodation",
    # transport
    "bus": "transport", "transportation": "transport",
    "commute": "transport", "travel": "transport", "vehicle": "transport",
    # timings
    "timing": "timings", "hours": "timings", "hour": "timings",
    "open": "timings", "close": "timings", "closing": "timings", "opening": "timings",
    # contact
    "phone": "contact", "email": "contact", "reach": "contact", "call": "contact",
    "helpdesk": "contact", "number": "contact",
    # scholarship
    "scholarships": "scholarship", "financial": "scholarship",
    "aid": "scholarship", "stipend": "scholarship", "grant": "scholarship",
    # location
    "address": "location", "located": "location",
    "directions": "location", "map": "location", "situated": "location",
    # sports/activities
    "sports": "activities", "games": "activities", "club": "activities",
    "extracurricular": "activities", "cricket": "activities", "football": "activities",
}

GREETINGS = {"hi", "hello", "hey", "greetings", "good morning",
             "good afternoon", "good evening", "howdy", "hii", "helo"}


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text)


def _tokenize(text: str) -> list:
    return [w for w in text.split() if w not in STOPWORDS and len(w) > 1]


def _expand(tokens: list) -> set:
    return {SYNONYMS.get(t, t) for t in tokens}


def preprocess(text: str) -> set:
    return _expand(_tokenize(_normalize(text)))


def _score(q_tokens: set, faq: dict) -> float:
    if not q_tokens:
        return 0.0
    faq_q  = preprocess(faq["question"])
    faq_kw = _expand(_tokenize(_normalize(faq.get("keywords", ""))))
    faq_all = faq_q | faq_kw
    n = len(q_tokens)
    kw_score  = len(q_tokens & faq_kw)  / n
    q_score   = len(q_tokens & faq_q)   / n
    all_score = len(q_tokens & faq_all) / n
    return min(0.5 * kw_score + 0.3 * q_score + 0.2 * all_score, 1.0)


def get_response(user_message: str) -> dict:
    msg = user_message.strip()[:MAX_LEN]
    if not msg:
        return _fallback(0.0)

    norm = _normalize(msg)
    if norm in GREETINGS or norm.rstrip("!") in GREETINGS:
        return {
            "answer": (
                "Hello! I'm the Smart College Assistant. 👋\n"
                "I can answer questions about admissions, courses, fees, examinations, "
                "library, hostel, transport, scholarships, and more.\n"
                "How can I help you today?"
            ),
            "faq_id": None, "category": None, "confidence": 1.0, "matched": True,
        }

    tokens = preprocess(msg)
    if not tokens:
        return _fallback(0.0)

    faqs = get_all_faqs()
    if not faqs:
        return _fallback(0.0)

    ranked = sorted([(f, _score(tokens, f)) for f in faqs], key=lambda x: x[1], reverse=True)
    best_faq, best_score = ranked[0]

    if best_score >= THRESHOLD:
        return {
            "answer":     best_faq["answer"],
            "faq_id":     best_faq["id"],
            "category":   best_faq["category"],
            "confidence": round(best_score, 3),
            "matched":    True,
        }
    return _fallback(best_score)


def _fallback(conf: float) -> dict:
    return {
        "answer":     random.choice(FALLBACK),
        "faq_id":     None,
        "category":   None,
        "confidence": round(conf, 3),
        "matched":    False,
    }


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from database import init_db
    init_db()
    tests = [
        ("What is the admission process?",       "Admissions"),
        ("How do I apply?",                      "Admissions"),
        ("Tell me about courses",                "Courses"),
        ("What are the library timings?",        "Facilities"),
        ("When does the library close?",         "Facilities"),
        ("How do I pay my fees?",                "Fees"),
        ("Where is the exam timetable?",         "Examinations"),
        ("How do I check my results?",           "Examinations"),
        ("Is hostel available?",                 "Facilities"),
        ("Is there a bus service?",              "Facilities"),
        ("Where is the college located?",        "General"),
        ("Tell me about scholarships",           "General"),
        ("Who won the IPL?",                     None),
        ("",                                     None),
        ("hi",                                   None),
    ]
    ok = 0
    faq_total = 0
    print(f"{'Question':<48} {'Score':>5}  {'Category':<15} Pass")
    print("-" * 80)
    for q, exp in tests:
        r = get_response(q)
        got = r["category"]
        if exp is not None:
            faq_total += 1
            passed = got == exp
            if passed: ok += 1
        else:
            passed = not r["matched"] or (q.lower().strip() in GREETINGS)
        print(f"{(q or '<empty>'):<48} {r['confidence']:>5.2f}  {str(got):<15} {'✓' if passed else '✗'}")
    print(f"\nFAQ accuracy: {ok}/{faq_total} = {ok/faq_total*100:.0f}%")
