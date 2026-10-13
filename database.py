import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("HackCollegeLife.DB")

DB_FILE = os.getenv("DB_PATH", "college_life.db")

def get_connection():
    """Returns a SQLite connection with row_factory configured"""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable Write-Ahead Logging for high performance
    return conn

def init_db():
    """Initializes tables for all 5 agents and student academic history"""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Study Buddy Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            notes TEXT,
            flashcards_json TEXT,
            mcqs_json TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Quiz Score Results (Live Quiz Record)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percentage REAL NOT NULL,
            answers_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. YouTube Summaries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS youtube_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            title TEXT,
            summary TEXT,
            takeaways_json TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 4. Research Briefs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            summary TEXT,
            markdown TEXT,
            word_count INTEGER,
            wikipedia_url TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 5. Assignments
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            questions_json TEXT,
            answers_json TEXT,
            markdown TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 6. Dean Orchestrations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dean_orchestrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            plan_json TEXT,
            step_logs_json TEXT,
            dean_note TEXT,
            dean_verdict TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized successfully at {DB_FILE}")

# ---------------------------------------------------------------------------
# Insertion Helpers
# ---------------------------------------------------------------------------
def save_study_session(topic: str, notes: str, flashcards: list, mcqs: list, source: str) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO study_sessions (topic, notes, flashcards_json, mcqs_json, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic, notes, json.dumps(flashcards), json.dumps(mcqs), source, datetime.now().isoformat())
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        logger.error(f"Error saving study session: {e}")
        return -1

def save_quiz_result(topic: str, score: int, total: int, percentage: float, answers: dict = None) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO quiz_results (topic, score, total, percentage, answers_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic, score, total, percentage, json.dumps(answers or {}), datetime.now().isoformat())
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        logger.error(f"Error saving quiz result: {e}")
        return -1

def save_youtube_summary(url: str, title: str, summary: str, takeaways: list, source: str) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO youtube_summaries (url, title, summary, takeaways_json, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (url, title, summary, json.dumps(takeaways), source, datetime.now().isoformat())
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        logger.error(f"Error saving youtube summary: {e}")
        return -1

def save_research_brief(topic: str, summary: str, markdown: str, word_count: int, wiki_url: str, source: str) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO research_briefs (topic, summary, markdown, word_count, wikipedia_url, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (topic, summary, markdown, word_count, wiki_url, source, datetime.now().isoformat())
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        logger.error(f"Error saving research brief: {e}")
        return -1

def save_assignment(topic: str, questions: list, answers: list, markdown: str, source: str) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO assignments (topic, questions_json, answers_json, markdown, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic, json.dumps(questions), json.dumps(answers), markdown, source, datetime.now().isoformat())
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        logger.error(f"Error saving assignment: {e}")
        return -1

def save_dean_orchestration(task: str, plan: list, step_logs: list, dean_note: str, verdict: str, source: str) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO dean_orchestrations (task, plan_json, step_logs_json, dean_note, dean_verdict, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task, json.dumps(plan), json.dumps(step_logs), dean_note, verdict, source, datetime.now().isoformat())
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        logger.error(f"Error saving dean orchestration: {e}")
        return -1

# ---------------------------------------------------------------------------
# Retrieval & Analytics Helpers
# ---------------------------------------------------------------------------
def get_academic_stats() -> Dict[str, Any]:
    """Computes overall student metrics across all agents"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        study_count = cursor.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
        quiz_count = cursor.execute("SELECT COUNT(*) FROM quiz_results").fetchone()[0]
        yt_count = cursor.execute("SELECT COUNT(*) FROM youtube_summaries").fetchone()[0]
        research_count = cursor.execute("SELECT COUNT(*) FROM research_briefs").fetchone()[0]
        assignment_count = cursor.execute("SELECT COUNT(*) FROM assignments").fetchone()[0]
        dean_count = cursor.execute("SELECT COUNT(*) FROM dean_orchestrations").fetchone()[0]

        # Quiz stats
        avg_score_row = cursor.execute("SELECT AVG(percentage), MAX(percentage) FROM quiz_results").fetchone()
        avg_quiz_pct = round(avg_score_row[0], 1) if avg_score_row and avg_score_row[0] is not None else 0.0
        max_quiz_pct = round(avg_score_row[1], 1) if avg_score_row and avg_score_row[1] is not None else 0.0

        # Estimated Freshman GPA (4.0 scale based on quiz average)
        if quiz_count > 0:
            if avg_quiz_pct >= 90:
                freshman_gpa = 4.0
            elif avg_quiz_pct >= 80:
                freshman_gpa = 3.5
            elif avg_quiz_pct >= 70:
                freshman_gpa = 3.0
            elif avg_quiz_pct >= 60:
                freshman_gpa = 2.5
            else:
                freshman_gpa = 2.0
        else:
            freshman_gpa = 4.0  # Freshman start

        conn.close()

        return {
            "total_study_sessions": study_count,
            "total_quizzes_taken": quiz_count,
            "average_quiz_score_pct": avg_quiz_pct,
            "highest_quiz_score_pct": max_quiz_pct,
            "freshman_gpa": freshman_gpa,
            "total_youtube_digests": yt_count,
            "total_research_briefs": research_count,
            "total_assignments_solved": assignment_count,
            "total_dean_plans": dean_count,
            "total_records": study_count + quiz_count + yt_count + research_count + assignment_count + dean_count
        }
    except Exception as e:
        logger.error(f"Error computing academic stats: {e}")
        return {
            "total_study_sessions": 0,
            "total_quizzes_taken": 0,
            "average_quiz_score_pct": 0.0,
            "freshman_gpa": 4.0,
            "total_records": 0
        }

def get_recent_history(limit: int = 25) -> List[Dict[str, Any]]:
    """Retrieves unified timeline of past academic work"""
    items = []
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Study sessions
        for row in cursor.execute("SELECT id, topic, source, created_at FROM study_sessions ORDER BY id DESC LIMIT ?", (limit,)):
            items.append({
                "type": "Study Buddy",
                "icon": "📚",
                "title": f"Study Kit: {row['topic']}",
                "detail": f"Source: {row['source']}",
                "timestamp": row['created_at'],
                "category": "study"
            })

        # Quiz results
        for row in cursor.execute("SELECT id, topic, score, total, percentage, created_at FROM quiz_results ORDER BY id DESC LIMIT ?", (limit,)):
            items.append({
                "type": "Quiz Attempt",
                "icon": "🎯",
                "title": f"Quiz: {row['topic']}",
                "detail": f"Score: {row['score']}/{row['total']} ({row['percentage']}%)",
                "timestamp": row['created_at'],
                "category": "quiz"
            })

        # YouTube summaries
        for row in cursor.execute("SELECT id, title, source, created_at FROM youtube_summaries ORDER BY id DESC LIMIT ?", (limit,)):
            items.append({
                "type": "YouTube Digest",
                "icon": "🎥",
                "title": row['title'] or "Lecture Summary",
                "detail": f"Source: {row['source']}",
                "timestamp": row['created_at'],
                "category": "youtube"
            })

        # Research briefs
        for row in cursor.execute("SELECT id, topic, word_count, created_at FROM research_briefs ORDER BY id DESC LIMIT ?", (limit,)):
            items.append({
                "type": "Research Brief",
                "icon": "🔬",
                "title": f"Research: {row['topic']}",
                "detail": f"Word count: ~{row['word_count']}",
                "timestamp": row['created_at'],
                "category": "research"
            })

        # Assignments
        for row in cursor.execute("SELECT id, topic, created_at FROM assignments ORDER BY id DESC LIMIT ?", (limit,)):
            items.append({
                "type": "Assignment Submission",
                "icon": "📝",
                "title": f"Assignment: {row['topic']}",
                "detail": "Step-by-step collegiate solutions",
                "timestamp": row['created_at'],
                "category": "assignment"
            })

        # Dean orchestrations
        for row in cursor.execute("SELECT id, task, dean_verdict, created_at FROM dean_orchestrations ORDER BY id DESC LIMIT ?", (limit,)):
            items.append({
                "type": "Dean Orchestration",
                "icon": "🎓",
                "title": f"Dean's Order: {row['task'][:50]}...",
                "detail": row['dean_verdict'] or "Academic plan executed",
                "timestamp": row['created_at'],
                "category": "dean"
            })

        conn.close()

        # Sort combined timeline descending by timestamp
        items.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
        return items[:limit]
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return []

def clear_all_records() -> bool:
    """Wipes all database records (reset)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for table in ["study_sessions", "quiz_results", "youtube_summaries", "research_briefs", "assignments", "dean_orchestrations"]:
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error clearing records: {e}")
        return False
