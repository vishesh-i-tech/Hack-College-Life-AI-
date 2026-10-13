import sys
import unittest
from starlette.testclient import TestClient
from main import app

class TestHackYourCollegeLife(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_status_endpoint(self):
        """Test GET /api/status returns online status and demo mode metadata"""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertEqual(data.get("app"), "Hack Your College Life")
        self.assertIn("primary_model", data)
        self.assertIn("fallback_model", data)
        print("PASS: /api/status verified successfully.")

    def test_02_study_buddy_endpoint(self):
        """Test POST /api/study-buddy generates notes, 8 flashcards, and 5 MCQs"""
        payload = {"topic": "Calculus & Limits"}
        response = self.client.post("/api/study-buddy", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertNotIn("error", data)
        self.assertIn("notes", data)
        self.assertTrue(len(data["notes"]) > 50)
        
        # Verify 8 Flashcards
        flashcards = data.get("flashcards", [])
        self.assertEqual(len(flashcards), 8, f"Expected 8 flashcards, got {len(flashcards)}")
        for fc in flashcards:
            self.assertIn("front", fc)
            self.assertIn("back", fc)
            self.assertTrue(len(fc["front"]) > 0)
            self.assertTrue(len(fc["back"]) > 0)

        # Verify 5 MCQs
        mcqs = data.get("mcqs", [])
        self.assertEqual(len(mcqs), 5, f"Expected 5 MCQs, got {len(mcqs)}")
        for mcq in mcqs:
            self.assertIn("question", mcq)
            self.assertIn("options", mcq)
            self.assertEqual(len(mcq["options"]), 4, "Expected 4 options per MCQ")
            self.assertIn("answer_index", mcq)
            self.assertIn("explanation", mcq)
            self.assertTrue(0 <= mcq["answer_index"] < 4)

        print(f"PASS: /api/study-buddy verified (8 flashcards, 5 MCQs on '{data['topic']}').")

    def test_03_youtube_summarizer_url_and_fallback(self):
        """Test POST /api/youtube-summarizer with URL and pasted transcript fallback"""
        # Test 1: URL input
        url_payload = {"url": "https://www.youtube.com/watch?v=8hly31xKli0"}
        res1 = self.client.post("/api/youtube-summarizer", json=url_payload)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertIn("summary", data1)
        self.assertIn("key_takeaways", data1)
        self.assertTrue(len(data1["key_takeaways"]) >= 3)

        # Test 2: Pasted transcript fallback
        pasted_payload = {
            "url": "https://www.youtube.com/watch?v=invalid_id_999",
            "pasted_transcript": "Welcome to Linear Algebra. Today we discuss eigenvalues and eigenvectors. An eigenvector satisfies Av = lambda v."
        }
        res2 = self.client.post("/api/youtube-summarizer", json=pasted_payload)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertIn("summary", data2)
        self.assertIn("key_takeaways", data2)
        print("PASS: /api/youtube-summarizer verified (both URL and pasted fallback).")

    def test_04_research_assistant_endpoint(self):
        """Test POST /api/research-assistant with Wikipedia integration and .md synthesis"""
        payload = {"topic": "Computer Science", "word_count": 300}
        response = self.client.post("/api/research-assistant", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("summary", data)
        self.assertIn("markdown", data)
        self.assertIn("wikipedia_url", data)
        self.assertTrue(len(data["markdown"]) > 100)
        self.assertTrue(data.get("word_count", 0) > 50)
        print("PASS: /api/research-assistant verified (Wikipedia summary and Markdown).")

    def test_05_assignment_writer_endpoint(self):
        """Test POST /api/assignment-writer generates answers and .md output"""
        payload = {
            "topic": "Data Structures",
            "question_list": [
                "What is the average time complexity of QuickSort?",
                "Explain the difference between a Stack and a Queue."
            ]
        }
        response = self.client.post("/api/assignment-writer", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answers", data)
        self.assertEqual(len(data["answers"]), 2)
        self.assertIn("markdown", data)
        self.assertIn("QuickSort", data["markdown"])
        print("PASS: /api/assignment-writer verified (Answers and Markdown formatted).")

    def test_06_dean_orchestrator_endpoint(self):
        """Test POST /api/dean plans, executes sub-agents, retries if needed, and returns sticky note"""
        payload = {
            "task": "I need help preparing for my physics quiz on Newtonian mechanics: need flashcards, research, and questions."
        }
        response = self.client.post("/api/dean", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify plan
        self.assertIn("plan", data)
        self.assertTrue(len(data["plan"]) >= 1)

        # Verify step logs
        self.assertIn("step_logs", data)
        self.assertTrue(len(data["step_logs"]) >= 2)
        log_agents = [log["agent"] for log in data["step_logs"]]
        print(f"Dean pipeline log agents: {log_agents}")

        # Verify results
        self.assertIn("results", data)
        self.assertTrue(len(data["results"]) >= 1)

        # Verify Dean's Note (Sticky Note text)
        self.assertIn("dean_note", data)
        self.assertIn("Dean", data["dean_note"])
        self.assertIn("dean_verdict", data)
        print("PASS: /api/dean verified (Plan + Execution Logs + Results + Dean's Note).")

    def test_07_never_crash_resilience(self):
        """Test that malformed/empty requests never throw 500s and return friendly responses"""
        # Completely empty body to study-buddy
        r1 = self.client.post("/api/study-buddy", json={})
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertTrue("notes" in d1 or "error" in d1)

        # Missing fields to assignment writer
        r2 = self.client.post("/api/assignment-writer", json={"topic": ""})
        self.assertEqual(r2.status_code, 200)

        # Dean with empty task
        r3 = self.client.post("/api/dean", json={"task": ""})
        self.assertEqual(r3.status_code, 200)
        d3 = r3.json()
        self.assertIn("dean_note", d3)

        print("PASS: Never-Crash resilience verified across edge cases.")

    def test_08_static_index_html_served(self):
        """Test that GET / serves the static notebook HTML file"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("Hack Your College Life", html)
        self.assertIn("VARSITY HEADER", html)
        self.assertIn("flashcard", html)
        self.assertIn("sticky-note", html)
        print("PASS: GET / serves college-notebook UI HTML successfully.")

    def test_09_database_stats_and_persistence(self):
        """Test GET /api/db/stats returns persistent academic metrics and counts"""
        response = self.client.get("/api/db/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("freshman_gpa", data)
        self.assertIn("total_study_sessions", data)
        self.assertIn("total_records", data)
        self.assertTrue(data["total_records"] >= 0)
        print(f"PASS: /api/db/stats verified (GPA: {data['freshman_gpa']}, Total Records: {data['total_records']}).")

    def test_10_database_quiz_result_and_history(self):
        """Test POST /api/db/quiz-result saves quiz score and GET /api/db/history retrieves it"""
        # Save a sample quiz result
        payload = {
            "topic": "Newtonian Kinematics",
            "score": 4,
            "total": 5,
            "percentage": 80.0,
            "answers": {"0": 1, "1": 0, "2": 1, "3": 1, "4": 2}
        }
        res_post = self.client.post("/api/db/quiz-result", json=payload)
        self.assertEqual(res_post.status_code, 200)
        post_data = res_post.json()
        self.assertEqual(post_data.get("status"), "saved")
        self.assertEqual(post_data.get("score"), "4/5")

        # Verify history contains recent record
        res_hist = self.client.get("/api/db/history")
        self.assertEqual(res_hist.status_code, 200)
        hist_data = res_hist.json()
        self.assertIn("history", hist_data)
        self.assertTrue(len(hist_data["history"]) > 0)
        print("PASS: /api/db/quiz-result and /api/db/history persistence verified successfully.")

if __name__ == "__main__":
    unittest.main(verbosity=2)

