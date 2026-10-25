"""
database.py — SQLite database layer for Smart College Assistant.

Tables:
  faqs         — college FAQs with category, keywords, created_at, updated_at
  chat_history — per-session conversation log
  feedback     — student helpfulness ratings with optional comment

Provides full CRUD for FAQs, chat history saving, feedback recording,
and admin analytics helpers.
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "college.db")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db():
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS faqs (
                id         INTEGER  PRIMARY KEY AUTOINCREMENT,
                question   TEXT     NOT NULL,
                answer     TEXT     NOT NULL,
                category   TEXT     NOT NULL DEFAULT 'General',
                keywords   TEXT     NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT     NOT NULL,
                user_message TEXT     NOT NULL,
                bot_response TEXT     NOT NULL,
                faq_id       INTEGER,
                created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER  PRIMARY KEY AUTOINCREMENT,
                session_id TEXT     NOT NULL,
                faq_id     INTEGER,
                rating     INTEGER  NOT NULL CHECK (rating IN (1, 0)),
                comment    TEXT     NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (faq_id) REFERENCES faqs(id) ON DELETE SET NULL
            )
        """)

        conn.commit()

    _seed_faqs()


# ---------------------------------------------------------------------------
# Seed data (runs only when table is empty)
# ---------------------------------------------------------------------------

SAMPLE_FAQS = [
    # ── Admissions ────────────────────────────────────────────────────────
    (
        "What is the admission process?",
        "Admissions are conducted through an online application form available on the college website. "
        "Eligible candidates are shortlisted based on merit and called for document verification. "
        "Please visit the official Admissions page for the current year's schedule and requirements.",
        "Admissions",
        "admission, apply, application, join, enroll, enrollment, procedure, process, how to apply",
    ),
    (
        "What are the eligibility requirements for admission?",
        "Eligibility criteria vary by programme. Generally, students must have completed 10+2 from "
        "a recognised board with the required minimum percentage. "
        "Please check the official Admissions page for programme-specific requirements.",
        "Admissions",
        "eligibility, requirement, criteria, qualification, marks, percentage, 10+2, 12th, standard",
    ),
    (
        "Where can I find the application form?",
        "The application form is available on the college's official website under the Admissions "
        "section. You can also collect a physical form from the administrative office during office hours.",
        "Admissions",
        "application form, form, download, apply online, where to apply, get form",
    ),
    (
        "When does admission start?",
        "Admission dates are announced on the college website and notice boards at the start of each "
        "academic year. Please check the official Admissions page or contact the administrative "
        "office for the current schedule.",
        "Admissions",
        "admission date, admission start, when admission, opening date, last date, deadline",
    ),
    # ── Courses ───────────────────────────────────────────────────────────
    (
        "What courses are offered by the college?",
        "The college offers undergraduate (B.A., B.Sc., B.Com., B.Tech.), postgraduate (M.A., M.Sc., MBA), "
        "and diploma programmes across various disciplines. "
        "Visit the Academics section of the official website for the complete list.",
        "Courses",
        "courses, programmes, programs, degree, undergraduate, postgraduate, diploma, offered, stream",
    ),
    (
        "Which departments are available?",
        "The college has departments including Computer Science, Commerce, Arts, Science, Management, "
        "Engineering, and Humanities. Please visit the Departments section on the website for details.",
        "Courses",
        "department, departments, faculty, science, arts, commerce, engineering, management, humanities",
    ),
    (
        "Where can I find the course syllabus?",
        "The syllabus for each programme is available on the college website under the respective "
        "department's page. You may also collect printed copies from the department office.",
        "Courses",
        "syllabus, curriculum, subjects, course content, topics, study material, schedule",
    ),
    # ── Fees ──────────────────────────────────────────────────────────────
    (
        "Where can I find the fee structure?",
        "The detailed fee structure for all programmes is published on the college website under the "
        "Fees section. For the most current information, please contact the accounts office.",
        "Fees",
        "fee, fees, fee structure, tuition, cost, charges, how much, amount",
    ),
    (
        "How do I pay my college fees?",
        "Fees can be paid online through the student portal or in person at the college accounts "
        "office. Online payment accepts net banking, UPI, and debit/credit cards. "
        "Keep your payment receipt for future reference.",
        "Fees",
        "pay fees, fee payment, online payment, challan, accounts, receipt, upi, net banking",
    ),
    (
        "Whom should I contact about fee-related issues?",
        "For any fee-related queries or issues, please contact the Accounts Office located in the "
        "main administrative block. Office hours are Monday to Saturday, 9:00 AM to 4:00 PM.",
        "Fees",
        "fee problem, fee issue, refund, fee query, accounts office, contact fee",
    ),
    # ── Examinations ──────────────────────────────────────────────────────
    (
        "Where can I find the examination timetable?",
        "The examination timetable is published on the college notice board and the official website "
        "under the Examinations section approximately one month before exams. "
        "Check regularly for updates.",
        "Examinations",
        "exam timetable, examination schedule, date sheet, exam dates, when is exam, time table",
    ),
    (
        "How can I check my examination results?",
        "Results are published on the college website and the university's official results portal. "
        "You can check results using your roll number.",
        "Examinations",
        "result, results, marks, grade, score, exam result, check result, pass fail, marksheet",
    ),
    (
        "What should I do if I have an examination-related issue?",
        "For examination issues such as admit card problems, hall ticket corrections, or result "
        "discrepancies, contact the Examination Cell in the administrative block. "
        "Bring your student ID and relevant documents.",
        "Examinations",
        "exam problem, admit card, hall ticket, revaluation, exam issue, examination office, correction",
    ),
    # ── Facilities ────────────────────────────────────────────────────────
    (
        "What are the library timings?",
        "The college library is open Monday to Saturday from 8:00 AM to 8:00 PM. "
        "On Sundays and public holidays, the library is closed. "
        "Students must carry their identity card to borrow books.",
        "Facilities",
        "library, library timings, library hours, library open, library close, books, reading room",
    ),
    (
        "Is hostel accommodation available?",
        "Yes, the college provides separate hostel facilities for male and female students. "
        "Hostel admission is subject to availability. "
        "Please contact the Hostel Warden or the administrative office for allocation and fee details.",
        "Facilities",
        "hostel, accommodation, boarding, residence, stay, dormitory, hostel fee, warden, room",
    ),
    (
        "Is transportation available for students?",
        "The college operates a bus service covering major routes in the city and surrounding areas. "
        "Route details, timings, and transport fees are available from the Transport Office. "
        "Contact the administrative office for the current route list.",
        "Facilities",
        "transport, bus, transportation, college bus, route, commute, travel, pick up, drop, vehicle",
    ),
    (
        "What sports and extracurricular activities are available?",
        "The college provides facilities for cricket, football, basketball, volleyball, badminton, "
        "and indoor games. There are also cultural clubs, technical clubs, and the National Service "
        "Scheme. Contact the Student Activities Office for current details.",
        "Facilities",
        "sports, games, extracurricular, activities, club, cricket, football, cultural, nss, gym",
    ),
    # ── General ───────────────────────────────────────────────────────────
    (
        "Where is the college located?",
        "The college is located at [College Address]. "
        "The nearest landmark is [Landmark]. "
        "Please update this with the actual address of your institution.",
        "General",
        "location, address, where, college address, how to reach, directions, map, situated",
    ),
    (
        "How can I contact the college administration?",
        "You can reach the administrative office by phone at [Phone Number] or by email at "
        "[admin@college.edu]. Office hours are Monday to Saturday, 9:00 AM to 5:00 PM. "
        "Please replace these placeholders with your institution's actual contact details.",
        "General",
        "contact, phone, email, administration, office, call, reach, helpdesk, number",
    ),
    (
        "Where can I find scholarship information?",
        "Information about scholarships, including government and institutional scholarships, "
        "is available in the Scholarship section of the college website. "
        "You may also contact the Student Welfare Office for guidance.",
        "General",
        "scholarship, financial aid, merit scholarship, stipend, fee waiver, student welfare, grant",
    ),
    (
        "What are the college office timings?",
        "The administrative office is open Monday to Saturday from 9:00 AM to 5:00 PM. "
        "The office is closed on Sundays and public holidays.",
        "General",
        "office timings, office hours, office open, when is office open, working hours, timing",
    ),
    (
        "How can I find information about campus events?",
        "Campus events, fests, seminars, and workshops are announced on the college notice boards, "
        "the official website, and the college's official social media pages. "
        "Check the Events section regularly for updates.",
        "General",
        "events, campus events, fest, festival, seminar, workshop, cultural, sports, activities, notice",
    ),
    (
        "What is the college principal's name?",
        "Please visit the About Us or Administration section on the college website for the current "
        "principal's name and contact details. This information is updated whenever there are changes.",
        "General",
        "principal, director, head, management, chancellor, dean, professor, staff",
    ),
]


def _seed_faqs():
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO faqs (question, answer, category, keywords) VALUES (?, ?, ?, ?)",
                SAMPLE_FAQS,
            )
            conn.commit()


# ---------------------------------------------------------------------------
# FAQ CRUD
# ---------------------------------------------------------------------------

def get_all_faqs():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM faqs ORDER BY category, id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_faq_by_id(faq_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM faqs WHERE id = ?", (faq_id,)).fetchone()
    return dict(row) if row else None


def add_faq(question: str, answer: str, category: str, keywords: str) -> int:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO faqs (question, answer, category, keywords, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (question.strip(), answer.strip(), category.strip(), keywords.strip(), now, now),
        )
        conn.commit()
    return cur.lastrowid


def update_faq(faq_id: int, question: str, answer: str, category: str, keywords: str) -> bool:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE faqs SET question=?, answer=?, category=?, keywords=?, updated_at=? WHERE id=?",
            (question.strip(), answer.strip(), category.strip(), keywords.strip(), now, faq_id),
        )
        conn.commit()
    return cur.rowcount > 0


def delete_faq(faq_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM faqs WHERE id = ?", (faq_id,))
        conn.commit()
    return cur.rowcount > 0


def search_faqs(query: str):
    term = f"%{query}%"
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM faqs WHERE question LIKE ? OR answer LIKE ? OR keywords LIKE ? "
            "ORDER BY category, id",
            (term, term, term),
        ).fetchall()
    return [dict(r) for r in rows]


def get_faqs_by_category(category: str):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM faqs WHERE category = ? ORDER BY id", (category,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_categories():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM faqs ORDER BY category"
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

def save_chat(session_id: str, user_message: str, bot_response: str, faq_id=None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_history (session_id, user_message, bot_response, faq_id) "
            "VALUES (?, ?, ?, ?)",
            (session_id, user_message, bot_response, faq_id),
        )
        conn.commit()


def get_chat_history(session_id: str, limit: int = 100):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_message, bot_response, faq_id, created_at FROM chat_history "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def save_feedback(session_id: str, faq_id, rating: int, comment: str = "") -> bool:
    if faq_id is not None and get_faq_by_id(faq_id) is None:
        faq_id = None
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO feedback (session_id, faq_id, rating, comment) VALUES (?, ?, ?, ?)",
            (session_id, faq_id, int(rating), comment.strip()[:500]),
        )
        conn.commit()
    return True


def get_feedback_stats():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT f.id, f.question,
                   COALESCE(SUM(CASE WHEN fb.rating=1 THEN 1 ELSE 0 END),0) AS helpful,
                   COALESCE(SUM(CASE WHEN fb.rating=0 THEN 1 ELSE 0 END),0) AS not_helpful
            FROM faqs f
            LEFT JOIN feedback fb ON fb.faq_id = f.id
            GROUP BY f.id ORDER BY helpful DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Admin stats
# ---------------------------------------------------------------------------

def get_stats():
    with get_connection() as conn:
        total_faqs     = conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0]
        total_chats    = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0]
        total_feedback = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        helpful        = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating=1").fetchone()[0]
        categories     = conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM faqs GROUP BY category ORDER BY category"
        ).fetchall()
    return {
        "total_faqs":     total_faqs,
        "total_chats":    total_chats,
        "total_feedback": total_feedback,
        "helpful":        helpful,
        "categories":     [dict(r) for r in categories],
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Initialising …")
    init_db()
    faqs = get_all_faqs()
    print(f"FAQs: {len(faqs)}")
    nid = add_faq("Test?", "Answer.", "General", "test")
    print(f"Added id={nid}, updated={update_faq(nid,'Q2','A2','General','kw')}, deleted={delete_faq(nid)}")
    save_chat("s1", "hello", "hi", None)
    save_feedback("s1", 1, 1, "great")
    print(f"Stats: {get_stats()}")
    print("OK")
