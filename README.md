# 🎓 Hack Your College Life

**Freshman Academic AI Suite powered by NVIDIA NIM, FastAPI & Persistent SQLite Database**

Built for 1st-year college students to accelerate exam preparation, homework problem-solving, lecture digesting, and research briefs with full academic record tracking.

---

## 🌟 Key Features

### 1. 5 Specialized AI Agents (POST `/api/*`):
- 📚 **Study Buddy (`/api/study-buddy`):** Takes any subject/topic and returns structured notes, **8 flip-able flashcards**, and **5 interactive MCQs** as clean JSON. Persists study kits to the database.
- 🎥 **YouTube Summarizer (`/api/youtube-summarizer`):** Extracts lecture transcripts using `youtube-transcript-api` and summarizes them with key takeaways, plus a **pasted-transcript fallback**. Persists lecture digests to the database.
- 🔬 **Research Assistant (`/api/research-assistant`):** Queries the Wikipedia REST API (with OpenSearch canonical title resolution) and generates structured academic briefs with citations and a **downloadable `.md`**. Persists research briefs to the database.
- 📝 **Assignment Writer (`/api/assignment-writer`):** Takes a topic + question list and provides step-by-step collegiate solutions with a **downloadable `.md`**. Persists assignment solutions to the database.
- 🎓 **Orchestrator "Dean" (`/api/dean`):** Accepts a single free-text task, formulates an LLM JSON execution plan (with deterministic keyword fallback), executes agents in order, **retries a failed agent once**, and outputs timeline logs plus a realistic **Dean's Supervisor Note**. Persists orchestrations to the database.

### 2. 🗄️ Persistent Database Backend (`college_life.db`):
- **Built-in Zero-Config SQLite:** Requires no extra installations or external cloud servers.
- **Tables:** `study_sessions`, `quiz_results`, `youtube_summaries`, `research_briefs`, `assignments`, and `dean_orchestrations`.
- **Live GPA & Academic Analytics:** Dynamic Freshman Cumulative GPA calculation based on live quiz performance.
- **REST Endpoints:**
  - `GET /api/db/stats`: Cumulative metrics, GPA, and counts.
  - `GET /api/db/history`: Unified timeline of student activity.
  - `POST /api/db/quiz-result`: Persists live quiz submissions with immediate GPA recalculation.
  - `DELETE /api/db/history`: Resets academic database records.
- **One-Click JSON Export:** Download complete database backup directly from the UI.

### 3. College-Notebook UI Theme:
- **Ruled Paper Canvas:** Soft paper background with horizontal blue notebook rules and a vertical red margin line.
- **Varsity Header:** Navy blue, maroon, and gold collegiate styling with varsity crests and badges.
- **6 Navigation Tabs:** Dean's Office, Study Buddy, YouTube Summarizer, Research Assistant, Assignment Writer, and **Academic Records (DB)**.
- **Flip-able Flashcards:** Responsive 3D flip cards on click (question on front, solution on back).
- **Clickable Quiz with Live Score & Auto-Save:** Instant option grading (green/red), explanations, and live score counter that automatically saves to SQLite.
- **Sticky Note:** Realistic yellow post-it note for Dean Vance's memo with drop shadow, red pin, and collegiate signature.
- **Zero Node/npm:** 100% Vanilla JS and CSS in a single static `index.html`.

---

## 🚀 Windows Quick Start Commands

### 1. Install Dependencies
```powershell
python -m pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Copy `.env.example` to `.env` and set your NVIDIA API key:
```env
# Primary: NVIDIA NIM API (Get your key from https://build.nvidia.com/)
NVIDIA_API_KEY=nvapi-your_nvidia_api_key_here

# Optional: Groq fallback (if desired)
GROQ_API_KEY=

PORT=8000
HOST=127.0.0.1
```
> **Note:**
> - **Primary Model:** `meta/llama-3.3-70b-instruct`
> - **Fallback Model:** `meta/llama-3.1-8b-instruct`
> - **Hot Reloading:** Keys added to `.env` are detected dynamically without restarting the server!
> - *(If no key is configured, the application automatically runs in high-fidelity Demo Mode!)*

### 3. Run Automated Tests
```powershell
python test.py
```

### 4. Launch the Web Application
```powershell
python main.py
```
*Or using uvicorn directly:*
```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 5. Access the Notebook Interface
Open your browser and navigate to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**
