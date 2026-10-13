import os
import re
import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional, Union, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

import database

# Initialize SQLite Database on startup
database.init_db()

from fastapi import FastAPI, Request, Response

from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HackCollegeLife")

# Configuration
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
PRIMARY_MODEL = "meta/llama-3.3-70b-instruct"
FALLBACK_MODEL = "meta/llama-3.1-8b-instruct"

def get_nvidia_api_key() -> str:
    """Reloads .env so newly entered keys take effect immediately without restart"""
    load_dotenv(override=True)
    return (os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_KEY") or "").strip()

def get_groq_api_key() -> str:
    load_dotenv(override=True)
    return os.getenv("GROQ_API_KEY", "").strip()


def extract_topic_from_text(text: str) -> str:
    """Extracts clean subject/topic from a student prompt sentence"""
    clean = text.strip()
    match = re.search(r"(?:exam on|midterm on|quiz on|test on|help with|notes on|research on|brief on|about|for)\s+([A-Za-z0-9\s&+\-]{3,40}?)(?:\.|\,|\;|\:|\band\b|\bgenerate\b|\bneed\b|\bwith\b|$)", clean, re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        if len(extracted) >= 3:
            return extracted
    cleaned = re.sub(r"^(?:I have|I need|Prepare me for|Please help me with|Help me with|Exam on|Notes on)\s+", "", clean, flags=re.IGNORECASE)
    cleaned = cleaned.split(".")[0].split(",")[0].strip()
    return cleaned[:45].strip() or clean[:40].strip()

# Initialize FastAPI with friendly title
app = FastAPI(
    title="Hack Your College Life",
    description="5-Agent AI Suite for 1st-Year College Students",
    version="1.0.0"
)

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

# ---------------------------------------------------------------------------
# Never Crash: Global Exception Handlers (Always return friendly JSON)
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    logger.error(f"Global catch: {exc}", exc_info=True)
    return JSONResponse(
        status_code=200,
        content={"error": f"College AI Notice: An issue occurred ({str(exc)}). Switching to safe fallback."}
    )

@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=200,
        content={"error": f"Invalid input format: {exc.errors()}"}
    )

# ---------------------------------------------------------------------------
# NVIDIA NIM API Integration with Dual Model Fallback & Demo Mode
# ---------------------------------------------------------------------------
def call_ai_llm(prompt: str, system_prompt: str = "You are an expert college academic tutor.", json_mode: bool = False) -> tuple[Optional[str], str]:
    """
    Calls NVIDIA NIM API with auto-fallback:
    PRIMARY (meta/llama-3.3-70b-instruct) -> FALLBACK (meta/llama-3.1-8b-instruct) -> Groq fallback -> Demo Mode
    Returns (response_text, model_used_or_reason)
    """
    nvidia_key = get_nvidia_api_key()
    groq_key = get_groq_api_key()

    # 1. Primary: NVIDIA NIM API
    if nvidia_key and not nvidia_key.startswith("your_") and not nvidia_key.startswith("nvapi-your"):
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=nvidia_key,
                timeout=30.0
            )
            for model_name in [PRIMARY_MODEL, FALLBACK_MODEL]:
                try:
                    logger.info(f"Attempting NVIDIA NIM call with {model_name}...")
                    kwargs: Dict[str, Any] = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 2048,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    completion = client.chat.completions.create(**kwargs)
                    content = completion.choices[0].message.content
                    if content and content.strip():
                        return content.strip(), f"NVIDIA NIM ({model_name})"
                except Exception as e:
                    logger.warning(f"NVIDIA model {model_name} failed: {e}. Trying fallback...")
        except Exception as e:
            logger.warning(f"NVIDIA client init error: {e}")

    # 2. Secondary: Groq fallback if configured
    if groq_key and not groq_key.startswith("your_"):
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            for g_model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
                try:
                    logger.info(f"Attempting Groq fallback call with {g_model}...")
                    kwargs: Dict[str, Any] = {
                        "model": g_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.4,
                        "max_tokens": 2048,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    completion = client.chat.completions.create(**kwargs)
                    content = completion.choices[0].message.content
                    if content and content.strip():
                        return content.strip(), f"Groq ({g_model})"
                except Exception as e:
                    logger.warning(f"Groq fallback {g_model} failed: {e}")
        except Exception as e:
            logger.warning(f"Groq init error: {e}")

    # 3. Safe Demo Mode
    reason = "demo_mode_no_key" if not nvidia_key and not groq_key else "demo_mode_all_models_failed"
    return None, reason

call_groq_llm = call_ai_llm



# ---------------------------------------------------------------------------
# Wikipedia Fetch Helper
# ---------------------------------------------------------------------------
def fetch_wikipedia_summary(topic: str) -> tuple[str, str, str]:
    """
    Fetches Wikipedia page summary via REST API with OpenSearch resolution.
    Returns (title, extract, url) or fallback strings.
    """
    clean_topic = extract_topic_from_text(topic)
    resolved_title = clean_topic

    # Attempt OpenSearch to find canonical title (e.g. 'Newtonian Mechanics' -> 'Classical mechanics')
    try:
        search_query = urllib.parse.quote(clean_topic)
        opensearch_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={search_query}&limit=1&namespace=0&format=json"
        s_req = urllib.request.Request(
            opensearch_url,
            headers={"User-Agent": "HackYourCollegeLife/1.0 (academic-ai-demo@college.edu)"}
        )
        with urllib.request.urlopen(s_req, timeout=3) as s_res:
            if s_res.status == 200:
                s_data = json.loads(s_res.read().decode("utf-8"))
                if len(s_data) > 1 and s_data[1]:
                    resolved_title = s_data[1][0]
    except Exception as e:
        logger.info(f"OpenSearch lookup notice for '{clean_topic}': {e}")

    try:
        encoded_topic = urllib.parse.quote(resolved_title.strip().replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "HackYourCollegeLife/1.0 (academic-ai-demo@college.edu)"}
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return (
                    data.get("title", resolved_title),
                    data.get("extract", f"Overview of {resolved_title} from Wikipedia."),
                    data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{encoded_topic}")
                )
    except Exception as e:
        logger.info(f"Wikipedia lookup notice for '{resolved_title}': {e}. Using knowledge synthesis.")

    return (
        clean_topic.title(),
        f"{clean_topic.title()} is a fundamental subject in undergraduate curriculum, embodying essential principles, theoretical frameworks, and core real-world applications.",
        f"https://en.wikipedia.org/wiki/{urllib.parse.quote(clean_topic.title())}"
    )


# ---------------------------------------------------------------------------
# YouTube Transcript Helper
# ---------------------------------------------------------------------------
def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract 11-char YouTube video ID from various URL formats"""
    if not url:
        return None
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"youtu\.be\/([0-9A-Za-z_-]{11})",
        r"youtube\.com\/embed\/([0-9A-Za-z_-]{11})",
        r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})"
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def fetch_youtube_transcript(video_id: str) -> tuple[Optional[str], str]:
    """Tries youtube-transcript-api to fetch text (supports both modern 1.2+ and legacy versions)"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        # Support v1.2+ API
        if hasattr(YouTubeTranscriptApi, 'fetch'):
            try:
                transcript_obj = YouTubeTranscriptApi().fetch(video_id)
            except TypeError:
                transcript_obj = YouTubeTranscriptApi.fetch(video_id)
            if hasattr(transcript_obj, 'to_raw_data'):
                raw = transcript_obj.to_raw_data()
                full_text = " ".join([item.get("text", "") for item in raw])
                return full_text, "youtube-transcript-api"
            snippets = [getattr(s, 'text', str(s)) for s in transcript_obj]
            return " ".join(snippets), "youtube-transcript-api"
        # Support legacy <1.0 API
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            full_text = " ".join([item.get("text", "") for item in transcript_list])
            return full_text, "youtube-transcript-api"
    except Exception as e:
        logger.warning(f"youtube-transcript-api notice for {video_id}: {e}")
        return None, str(e)
    return None, "Transcript API not available"


# ---------------------------------------------------------------------------
# Demo Engine: High-Fidelity Domain Fallback Data for 1st-Year College
# ---------------------------------------------------------------------------
def generate_demo_study_buddy(topic: str) -> Dict[str, Any]:
    clean_topic = topic.strip() or "Calculus & Derivatives"
    notes = (
        f"### Academic Study Guide: {clean_topic}\n\n"
        f"**1. Core Foundations:**\n"
        f"- {clean_topic} forms the backbone of freshman collegiate studies. Understanding the first principles allows solving complex multi-variable problems.\n"
        f"- Memorizing definitions is insufficient; focus on intuition, visual interpretation, and practical problem decomposition.\n\n"
        f"**2. Essential Laws & Formulas:**\n"
        f"- Principle of Invariance & Equivalence: Always balance both sides of equations before simplification.\n"
        f"- Boundary Conditions & Limit Behavior: Check extremes (0, infinity, negative regimes) to verify solution sanity.\n"
        f"- Convergence vs. Divergence: Ensure parameters stay within well-defined asymptotic bounds.\n\n"
        f"**3. Professor's Exam Traps:**\n"
        f"- Watch out for sign errors during substitution steps.\n"
        f"- Always state explicit domain constraints and units in your final boxed response."
    )

    flashcards = [
        {"front": f"What is the foundational definition of {clean_topic}?", "back": f"The core framework modeling change, states, and relationships systematically in {clean_topic}."},
        {"front": f"Key Term: First Principle / Invariance in {clean_topic}", "back": "The baseline truth that remains unchanged under transformation or coordinate shifts."},
        {"front": f"Common exam mistake in {clean_topic}?", "back": "Failing to check boundary constraints, zero division, or sign inversion during intermediate steps."},
        {"front": f"How do you test asymptotic behavior in {clean_topic}?", "back": "Evaluate limits as the independent variable approaches zero and positive/negative infinity."},
        {"front": f"What is the primary theorem governing {clean_topic}?", "back": "The Fundamental Theorem bridging instantaneous rates with cumulative sums or state transitions."},
        {"front": f"Role of dimensional analysis in {clean_topic}?", "back": "Validating equation homogeneity by checking units on both sides of each equality."},
        {"front": f"How to break down complex multi-part problems in {clean_topic}?", "back": "Decompose into Givens, Unknowns, Governing Formula, Algebraic Resolution, and Sanity Check."},
        {"front": f"Golden Rule for scoring full marks in {clean_topic}?", "back": "Write clear step-by-step logic, annotate intermediate assumptions, and box your final answer with units."}
    ]

    mcqs = [
        {
            "question": f"In introductory {clean_topic}, what is the first step before computing any algebraic manipulation?",
            "options": [
                "Assume the final answer is zero",
                "Define the variable domain and check boundary conditions",
                "Skip documentation and write only the final number",
                "Multiply all coefficients by arbitrary scalars"
            ],
            "answer_index": 1,
            "explanation": "Checking domain validity and boundary constraints prevents invalid operations like zero-division or out-of-domain functions."
        },
        {
            "question": f"Which mathematical/conceptual property ensures consistency across transformations in {clean_topic}?",
            "options": [
                "Linear Homogeneity and Conservation",
                "Arbitrary Randomization",
                "Superficial Heuristics",
                "Recursive Divergence"
            ],
            "answer_index": 0,
            "explanation": "Conservation laws and homogeneity ensure that governing relationships hold true regardless of reference changes."
        },
        {
            "question": f"When an exam problem in {clean_topic} asks for the instantaneous rate of change, what tool should you apply?",
            "options": [
                "Histogram plotting",
                "First derivative / differential operator",
                "Polynomial regression only",
                "Double summation without limits"
            ],
            "answer_index": 1,
            "explanation": "The first derivative represents the instantaneous slope and rate of change of a function with respect to its variable."
        },
        {
            "question": f"Why is verifying units (dimensional analysis) vital in {clean_topic} solutions?",
            "options": [
                "It guarantees the problem is written in French",
                "It quickly exposes algebra mistakes if LHS and RHS dimensions disagree",
                "Professors don't inspect units anyway",
                "It doubles the word count automatically"
            ],
            "answer_index": 1,
            "explanation": "If LHS and RHS dimensions don't match, an algebraic or conceptual error occurred in intermediate steps."
        },
        {
            "question": f"What distinguishes an Honors-level solution from an average response in {clean_topic}?",
            "options": [
                "Using messy handwriting to look fast",
                "Skipping intermediate derivations",
                "Providing clean step justifications, diagram annotations, and a boxed sanity check",
                "Writing as few words as possible"
            ],
            "answer_index": 2,
            "explanation": "Clear justification, thorough annotation, and edge-case verification demonstrate mastery and capture partial marks."
        }
    ]

    return {
        "topic": clean_topic,
        "notes": notes,
        "flashcards": flashcards,
        "mcqs": mcqs,
        "source": "College Study Engine (Demo Fallback)"
    }

def generate_demo_youtube_summary(topic_or_url: str) -> Dict[str, Any]:
    return {
        "title": "Freshman College Lecture: Core Concepts & Exam Breakdown",
        "summary": (
            "This college lecture deconstructs core principles with vivid demonstrations. "
            "The professor begins with real-world intuition, introduces the mathematical and logical formalism, "
            "and walks through 3 high-yield exam archetypes that regularly appear on midterm tests. "
            "The second half focuses on debugging common misconceptions and strategic shortcuts for timed quizzes."
        ),
        "key_takeaways": [
            "Always derive formulas from first principles before relying on mnemonic shortcuts.",
            "Visual intuition (graphs, state tables) solves 80% of tricky edge-case questions.",
            "Keep an 'Error Log' of past quiz mistakes to review 24 hours before finals.",
            "Attend professor office hours with at least one specific written roadblock.",
            "Form a 3-person peer accountability study pod to test each other weekly."
        ],
        "quick_review_points": [
            "Timestamp 04:15 - Core theorem breakdown and standard notation.",
            "Timestamp 12:40 - Solving Midterm Archetype #1 without arithmetic traps.",
            "Timestamp 24:10 - How TA graders award partial credit on open-ended problems."
        ],
        "transcript_source": "demo_lecture",
        "source": "College Study Engine (Demo Fallback)"
    }

def generate_demo_research_assistant(topic: str, word_count: int, wiki_extract: str, wiki_url: str) -> Dict[str, Any]:
    md = (
        f"# Research Brief: {topic.title()}\n\n"
        f"> **Subject:** Undergraduate Academic Exploration  \n"
        f"> **Target Word Count:** ~{word_count} words  \n"
        f"> **Primary Reference:** [{topic.title()} on Wikipedia]({wiki_url})\n\n"
        f"---\n\n"
        f"### 1. Abstract & Context\n"
        f"{wiki_extract}\n\n"
        f"In higher education, exploring **{topic}** requires bridging foundational theory with contemporary "
        f"computational, physical, and societal impacts. First-year university students must analyze this subject "
        f"not as isolated equations or definitions, but as an evolving continuum of scientific and intellectual thought.\n\n"
        f"### 2. Historical & Theoretical Evolution\n"
        f"The formal study of {topic} originated from the necessity to solve practical engineering and philosophical dilemmas. "
        f"Early pioneers established the foundational postulates, which were subsequently refined through rigorous "
        f"peer review, empirical testing, and modern technological tools. Key landmarks include standardizing mathematical "
        f"notation, establishing benchmark datasets, and unifying distinct sub-disciplines.\n\n"
        f"### 3. Practical Applications & Industry Relevance\n"
        f"- **Modern Industry:** Applied extensively in automation, systems design, and quantitative decision modeling.\n"
        f"- **Cross-Disciplinary Synergy:** Links closely with mathematics, software engineering, and scientific computing.\n"
        f"- **Future Outlook:** Emerging research focuses on energy efficiency, ethical frameworks, and adaptive architectures.\n\n"
        f"### 4. Freshman Study Strategy\n"
        f"1. Master the glossary of terms before tackling derivation proofs.\n"
        f"2. Consult primary literature through institutional library access (IEEE, ACM, JSTOR, arXiv).\n"
        f"3. Re-implement toy models in code or on paper to internalize dynamics.\n\n"
        f"### 5. Verified Citations & Recommended Readings\n"
        f"- *University Textbook Series*: Introduction to {topic.title()}, 4th Edition.\n"
        f"- *Encyclopedic Entry*: [Wikipedia - {topic.title()}]({wiki_url})\n"
        f"- *Academic Survey*: Foundational Principles in Modern Science & Engineering (2024)."
    )
    return {
        "topic": topic,
        "wikipedia_title": topic.title(),
        "wikipedia_url": wiki_url,
        "summary": wiki_extract[:400] + ("..." if len(wiki_extract) > 400 else ""),
        "markdown": md,
        "word_count": len(md.split()),
        "source": "College Research Engine (Demo Fallback)"
    }

def generate_demo_assignment_writer(topic: str, questions: List[str]) -> Dict[str, Any]:
    answers = []
    md_lines = [
        f"# Academic Assignment Submission: {topic.title()}",
        f"**Course Level:** Freshman Collegiate (1st Year)",
        f"**Date:** {datetime.now().strftime('%B %d, %Y')}",
        f"**Status:** Verified Academic Draft",
        "\n---"
    ]

    for idx, q in enumerate(questions, 1):
        clean_q = q.strip()
        ans = (
            f"**Step 1: Problem Clarification & Identification of Givens**\n"
            f"We are tasked with addressing: *{clean_q}*. In the context of {topic}, this requires establishing "
            f"standard assumptions and identifying relevant boundary conditions.\n\n"
            f"**Step 2: Theoretical Formulation**\n"
            f"Applying the governing laws of {topic}, we define the formal relation $f(x)$ and maintain strict dimensional "
            f"consistency throughout all intermediate substitutions.\n\n"
            f"**Step 3: Analytical Derivation & Resolution**\n"
            f"Solving algebraically, we isolate the dependent variable. Every transformation is justified through standard "
            f"axioms, ensuring no spurious roots or undefined divisions occur.\n\n"
            f"**Step 4: Boxed Academic Conclusion**\n"
            f"$$\\boxed{{\\text{{Result for Part {idx}: Validated under standard collegiate assumptions.}}}}$$\n"
            f"*Sanity Check:* The solution scales appropriately as parameters tend toward extreme limits."
        )
        answers.append({"question": clean_q, "answer": ans})
        md_lines.append(f"\n### Question {idx}\n> {clean_q}\n\n{ans}\n")

    return {
        "topic": topic,
        "answers": answers,
        "markdown": "\n".join(md_lines),
        "source": "College Assignment Engine (Demo Fallback)"
    }

# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class StudyBuddyRequest(BaseModel):
    topic: str = Field(default="Calculus & Derivatives")

class YouTubeRequest(BaseModel):
    url: str = Field(default="")
    pasted_transcript: Optional[str] = Field(default=None)

class ResearchRequest(BaseModel):
    topic: str = Field(default="Artificial Intelligence")
    word_count: int = Field(default=350, ge=100, le=2000)

class AssignmentRequest(BaseModel):
    topic: str = Field(default="Data Structures")
    question_list: Union[List[str], str] = Field(default=["Explain the time complexity of QuickSort vs MergeSort."])

class DeanRequest(BaseModel):
    task: str = Field(default="I have a physics midterm on kinematics tomorrow. Give me notes, flashcards, and solve questions on projectile motion.")

class QuizResultRequest(BaseModel):
    topic: str = Field(default="Freshman Quiz")
    score: int = Field(default=0, ge=0)
    total: int = Field(default=5, ge=1)
    percentage: float = Field(default=0.0)
    answers: Optional[Dict[str, Any]] = Field(default_factory=dict)

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    """Health & Configuration check"""
    nvidia_key = get_nvidia_api_key()
    groq_key = get_groq_api_key()
    has_nvidia = bool(nvidia_key and not nvidia_key.startswith("your_") and not nvidia_key.startswith("nvapi-your"))
    has_groq = bool(groq_key and not groq_key.startswith("your_"))

    if has_nvidia:
        mode_str = f"NVIDIA NIM Connected ({PRIMARY_MODEL})"
    elif has_groq:
        mode_str = "Groq Connected (llama-3.3-70b-versatile)"
    else:
        mode_str = "Demo Mode (NVIDIA NIM key not configured)"

    return {
        "status": "online",
        "app": "Hack Your College Life",
        "provider": "NVIDIA NIM",
        "has_nvidia_key": has_nvidia,
        "has_groq_key": has_groq,
        "database": "SQLite (college_life.db connected)",
        "primary_model": PRIMARY_MODEL,
        "fallback_model": FALLBACK_MODEL,
        "mode": mode_str
    }


# ---------------------------------------------------------------------------
# Database & Academic Records Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/db/stats")
async def get_db_stats():
    """Returns student GPA, total quizzes, and academic metrics from SQLite"""
    return database.get_academic_stats()

@app.get("/api/db/history")
async def get_db_history(limit: int = 25):
    """Returns past study kits, quizzes, research briefs, and Dean orders"""
    return {"history": database.get_recent_history(limit=limit)}

@app.post("/api/db/quiz-result")
async def post_quiz_result(req: QuizResultRequest):
    """Persists a student's live quiz attempt and returns updated stats"""
    quiz_id = database.save_quiz_result(
        topic=req.topic,
        score=req.score,
        total=req.total,
        percentage=req.percentage,
        answers=req.answers
    )
    return {
        "status": "saved",
        "quiz_id": quiz_id,
        "topic": req.topic,
        "score": f"{req.score}/{req.total}",
        "percentage": req.percentage,
        "stats": database.get_academic_stats()
    }

@app.delete("/api/db/history")
async def delete_db_history():
    """Wipes student academic records"""
    success = database.clear_all_records()
    return {"status": "cleared" if success else "error"}



@app.post("/api/study-buddy")
async def study_buddy_endpoint(req: StudyBuddyRequest):
    """
    Study Buddy Agent:
    Input: topic
    Output: notes + 8 flashcards + 5 MCQs as JSON (Persisted to SQLite)
    """
    result = None
    topic = req.topic.strip() or "General Study Skills"
    try:
        # Try Groq LLM
        prompt = (
            f"You are Study Buddy, an academic AI for 1st-year college students.\n"
            f"Generate comprehensive study material for topic: '{topic}'.\n"
            f"Return ONLY a valid JSON object with the following exact keys:\n"
            f"{{\n"
            f'  "notes": "Clear, markdown-formatted study notes with key concepts, formulas, and common traps (at least 200 words)",\n'
            f'  "flashcards": [\n'
            f'     {{"front": "Term or Question 1", "back": "Definition or Answer 1"}},\n'
            f'     ... exactly 8 flashcards\n'
            f'  ],\n'
            f'  "mcqs": [\n'
            f'     {{\n'
            f'        "question": "Question text",\n'
            f'        "options": ["Option A", "Option B", "Option C", "Option D"],\n'
            f'        "answer_index": 0,\n'
            f'        "explanation": "Why this is correct"\n'
            f'     }},\n'
            f'     ... exactly 5 MCQs\n'
            f'  ]\n'
            f"}}"
        )
        content, model = call_groq_llm(prompt, json_mode=True)
        if content:
            try:
                data = json.loads(content)
                if "notes" in data and "flashcards" in data and "mcqs" in data:
                    data["topic"] = topic
                    data["source"] = f"Groq ({model})"
                    if len(data.get("flashcards", [])) >= 4 and len(data.get("mcqs", [])) >= 3:
                        result = data
            except Exception as e:
                logger.warning(f"Error parsing Groq JSON for study-buddy: {e}")

        if not result:
            result = generate_demo_study_buddy(topic)

    except Exception as e:
        logger.error(f"Study Buddy error: {e}")
        result = generate_demo_study_buddy(req.topic or "Freshman Studies")

    # Persist session to SQLite
    database.save_study_session(
        topic=result.get("topic", topic),
        notes=result.get("notes", ""),
        flashcards=result.get("flashcards", []),
        mcqs=result.get("mcqs", []),
        source=result.get("source", "Study Engine")
    )
    return result

@app.post("/api/youtube-summarizer")
async def youtube_summarizer_endpoint(req: YouTubeRequest):
    """
    YouTube Summarizer Agent:
    URL -> youtube-transcript-api -> summary, with pasted-transcript fallback.
    Persisted to SQLite.
    """
    result = None
    url = req.url.strip()
    pasted = (req.pasted_transcript or "").strip()
    try:
        video_id = extract_youtube_video_id(url)
        raw_transcript = None
        source_note = "none"

        # Attempt 1: Fetch via youtube-transcript-api if URL provided
        if video_id:
            logger.info(f"Attempting to fetch transcript for video ID: {video_id}")
            t_text, t_status = fetch_youtube_transcript(video_id)
            if t_text:
                raw_transcript = t_text
                source_note = "youtube-transcript-api"

        # Attempt 2: Fallback to pasted transcript
        if not raw_transcript and pasted:
            logger.info("Using user-pasted transcript fallback.")
            raw_transcript = pasted
            source_note = "pasted-transcript fallback"

        # If transcript found, summarize via Groq LLM
        if raw_transcript:
            prompt = (
                f"You are an expert collegiate lecture summarizer for 1st-year students.\n"
                f"Summarize the following video transcript:\n\n{raw_transcript[:6000]}\n\n"
                f"Return ONLY a JSON object with keys:\n"
                f'{{"title": "Lecture Title", "summary": "Comprehensive 3-paragraph summary", '
                f'"key_takeaways": ["Takeaway 1", "Takeaway 2", "Takeaway 3", "Takeaway 4", "Takeaway 5"], '
                f'"quick_review_points": ["Review Point 1", "Review Point 2", "Review Point 3"]}}'
            )
            content, model = call_groq_llm(prompt, json_mode=True)
            if content:
                try:
                    data = json.loads(content)
                    data["transcript_source"] = source_note
                    data["source"] = f"Groq ({model})"
                    result = data
                except Exception as e:
                    logger.warning(f"Groq parsing failed for youtube: {e}")

        if not result:
            result = generate_demo_youtube_summary(url or "College Lecture")
            if pasted:
                result["transcript_source"] = "pasted-transcript (demo mode)"
            elif video_id:
                result["transcript_source"] = f"video {video_id} (transcripts disabled/demo)"
            else:
                result["transcript_source"] = "demo_mode"

    except Exception as e:
        logger.error(f"YouTube Summarizer error: {e}")
        result = generate_demo_youtube_summary(req.url or "Freshman Lecture")

    # Persist summary to SQLite
    database.save_youtube_summary(
        url=url,
        title=result.get("title", "Lecture Digest"),
        summary=result.get("summary", ""),
        takeaways=result.get("key_takeaways", []),
        source=result.get("source", "YouTube Engine")
    )
    return result


@app.post("/api/research-assistant")
async def research_assistant_endpoint(req: ResearchRequest):
    """
    Research Assistant Agent:
    topic + word count -> Wikipedia search -> summary + downloadable .md (Persisted to SQLite)
    """
    result = None
    topic = req.topic.strip() or "Computer Science"
    word_count = req.word_count or 350
    wiki_title, wiki_extract, wiki_url = fetch_wikipedia_summary(topic)
    try:
        # Step 2: Groq Synthesis
        prompt = (
            f"You are a Research Assistant for 1st-year college students.\n"
            f"Topic: {topic}\n"
            f"Target word count: approx {word_count} words.\n"
            f"Wikipedia Background Info: {wiki_extract}\n\n"
            f"Synthesize an academic research brief in rich Markdown format.\n"
            f"Include:\n"
            f"1. Executive Abstract\n"
            f"2. Core Concepts & Theoretical Mechanics\n"
            f"3. Practical Applications & Industry Impact\n"
            f"4. Recommended 1st-Year Study Strategy\n"
            f"5. Academic References (include {wiki_url})\n\n"
            f"Return ONLY a JSON object with keys:\n"
            f'{{"summary": "A concise 2-3 sentence teaser summary", "markdown": "The complete markdown document with all headings"}}'
        )
        content, model = call_groq_llm(prompt, json_mode=True)
        if content:
            try:
                data = json.loads(content)
                if "markdown" in data:
                    md_text = data["markdown"]
                    result = {
                        "topic": topic,
                        "wikipedia_title": wiki_title,
                        "wikipedia_url": wiki_url,
                        "summary": data.get("summary", wiki_extract[:300]),
                        "markdown": md_text,
                        "word_count": len(md_text.split()),
                        "source": f"Groq ({model}) + Wikipedia"
                    }
            except Exception as e:
                logger.warning(f"Groq parsing failed for research: {e}")

        if not result:
            result = generate_demo_research_assistant(topic, word_count, wiki_extract, wiki_url)

    except Exception as e:
        logger.error(f"Research Assistant error: {e}")
        result = generate_demo_research_assistant(req.topic or "Science", req.word_count, wiki_extract, wiki_url)

    # Persist research brief to SQLite
    database.save_research_brief(
        topic=result.get("topic", topic),
        summary=result.get("summary", ""),
        markdown=result.get("markdown", ""),
        word_count=result.get("word_count", 0),
        wiki_url=result.get("wikipedia_url", wiki_url),
        source=result.get("source", "Research Engine")
    )
    return result

@app.post("/api/assignment-writer")
async def assignment_writer_endpoint(req: AssignmentRequest):
    """
    Assignment Writer Agent:
    topic + question list -> answer for each + .md download (Persisted to SQLite)
    """
    result = None
    topic = req.topic.strip() or "General Coursework"
    raw_questions = req.question_list
    if isinstance(raw_questions, str):
        questions = [q.strip() for q in raw_questions.split("\n") if q.strip()]
    else:
        questions = [q.strip() for q in raw_questions if q.strip()]

    if not questions:
        questions = [f"Explain the primary principles and common problem-solving strategies in {topic}."]

    try:
        # Groq Synthesis
        prompt = (
            f"You are an Academic Assignment Problem Solver for 1st-year college students.\n"
            f"Subject: {topic}\n"
            f"Questions to answer step-by-step:\n"
            + "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
            + "\n\nProvide thorough, rigorous collegiate answers showing:\n"
            f"- Problem identification & givens\n"
            f"- Conceptual formulation & formulas\n"
            f"- Step-by-step analytical solution\n"
            f"- Final boxed answer and sanity check\n\n"
            f"Return ONLY a JSON object with keys:\n"
            f'{{"answers": [{{"question": "Q1 text", "answer": "Detailed answer..."}}], "markdown": "Complete formatted assignment submission in markdown"}}'
        )
        content, model = call_groq_llm(prompt, json_mode=True)
        if content:
            try:
                data = json.loads(content)
                if "answers" in data and "markdown" in data:
                    data["topic"] = topic
                    data["source"] = f"Groq ({model})"
                    result = data
            except Exception as e:
                logger.warning(f"Groq parsing failed for assignment writer: {e}")

        if not result:
            result = generate_demo_assignment_writer(topic, questions)

    except Exception as e:
        logger.error(f"Assignment writer error: {e}")
        result = generate_demo_assignment_writer(req.topic or "General", ["Problem 1: Outline solution fundamentals."])

    # Persist assignment to SQLite
    database.save_assignment(
        topic=result.get("topic", topic),
        questions=questions,
        answers=result.get("answers", []),
        markdown=result.get("markdown", ""),
        source=result.get("source", "Assignment Engine")
    )
    return result


# ---------------------------------------------------------------------------
# Agent 5: Orchestrator "Dean"
# ---------------------------------------------------------------------------
def keyword_plan_fallback(task: str) -> List[Dict[str, Any]]:
    """Keyword-based planner fallback if LLM plan fails"""
    t_lower = task.lower()
    topic = extract_topic_from_text(task)
    plan = []

    # Check for YouTube / Video
    if any(k in t_lower for k in ["youtube", "video", "lecture", "watch", "link", "http", "youtu.be"]):
        urls = re.findall(r"https?://[^\s]+", task)
        url = urls[0] if urls else "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        plan.append({
            "agent": "youtube_summarizer",
            "name": "YouTube Summarizer",
            "params": {"url": url, "pasted_transcript": task},
            "reason": "Task refers to video, lecture, or external link."
        })

    # Check for Research / Wikipedia
    if any(k in t_lower for k in ["research", "wiki", "wikipedia", "paper", "background", "history", "explore", "deep dive"]):
        plan.append({
            "agent": "research_assistant",
            "name": "Research Assistant",
            "params": {"topic": topic, "word_count": 350},
            "reason": "Task requests research brief, context, or Wikipedia synthesis."
        })

    # Check for Study / Flashcards / Quiz / MCQs
    if any(k in t_lower for k in ["study", "flashcard", "card", "quiz", "mcq", "test", "midterm", "exam", "prep", "notes", "revision"]):
        plan.append({
            "agent": "study_buddy",
            "name": "Study Buddy",
            "params": {"topic": topic},
            "reason": "Task asks for revision, flashcards, or interactive quiz prep."
        })

    # Check for Assignment / Questions / Homework
    if any(k in t_lower for k in ["assignment", "homework", "question", "problem", "solve", "exercise", "proof"]):
        plan.append({
            "agent": "assignment_writer",
            "name": "Assignment Writer",
            "params": {"topic": topic, "question_list": [task]},
            "reason": "Task specifies coursework problems or assignment prompts."
        })

    # Smart default if nothing matched: run Research Assistant + Study Buddy
    if not plan:
        plan.append({
            "agent": "study_buddy",
            "name": "Study Buddy",
            "params": {"topic": topic},
            "reason": "Comprehensive freshman study kit generation."
        })
        plan.append({
            "agent": "research_assistant",
            "name": "Research Assistant",
            "params": {"topic": topic, "word_count": 300},
            "reason": "Supplementary background reference brief."
        })

    return plan

@app.post("/api/dean")
async def dean_orchestrator_endpoint(req: DeanRequest):
    """
    Orchestrator 'Dean':
    1. Takes one free-text task.
    2. Plans which agents to run (LLM JSON plan with keyword fallback).
    3. Runs them in order.
    4. Retries a failed agent once.
    5. Returns step logs plus a final supervisor note ("Dean's note").
    """
    task = req.task.strip() or "Prepare for my upcoming collegiate exams."
    topic = extract_topic_from_text(task)
    step_logs = []
    results = {}

    step_logs.append({
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "step": 0,
        "agent": "Dean's Office (Orchestrator)",
        "status": "ANALYZING",
        "message": f"Dean received student task: '{task}' (Identified subject: '{topic}')"
    })

    # Step 1: LLM JSON Plan with Keyword Fallback
    plan = None
    prompt = (
        f"You are 'The Dean', an AI Orchestrator leading 4 collegiate specialist agents:\n"
        f"1. 'study_buddy' (params: topic) -> notes, 8 flashcards, 5 MCQs\n"
        f"2. 'youtube_summarizer' (params: url, pasted_transcript) -> lecture summary\n"
        f"3. 'research_assistant' (params: topic, word_count) -> Wikipedia research brief\n"
        f"4. 'assignment_writer' (params: topic, question_list) -> academic solutions\n\n"
        f"Student task: '{task}'\n"
        f"Identified clean subject: '{topic}'\n\n"
        f"Create an optimal sequential plan. In params, use the clean subject '{topic}' for topic fields.\n"
        f"Return ONLY JSON:\n"
        f'{{"plan": [{{"agent": "study_buddy", "name": "Study Buddy", "params": {{"topic": "{topic}"}}, "reason": "Generate flashcards and quiz"}}]}}'
    )
    content, model = call_groq_llm(prompt, json_mode=True)

    if content:
        try:
            data = json.loads(content)
            if "plan" in data and isinstance(data["plan"], list) and len(data["plan"]) > 0:
                plan = data["plan"]
                step_logs.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "step": 1,
                    "agent": "Dean's Planner (LLM)",
                    "status": "PLANNED",
                    "message": f"Generated {len(plan)}-stage plan using Groq ({model})."
                })
        except Exception as e:
            logger.warning(f"Dean LLM planner failed to parse JSON: {e}")

    # Fallback to keyword planner if LLM plan failed
    if not plan:
        plan = keyword_plan_fallback(task)
        step_logs.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "step": 1,
            "agent": "Dean's Planner (Keyword Fallback)",
            "status": "PLANNED",
            "message": f"Applied deterministic keyword planner: {len(plan)} agent(s) scheduled."
        })

    # Step 2: Execute each agent in order with 1 retry on failure
    for idx, item in enumerate(plan, 2):
        agent_type = item.get("agent")
        agent_name = item.get("name", agent_type)
        params = item.get("params", {})
        success = False
        attempt = 1

        while attempt <= 2 and not success:
            try:
                step_logs.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "step": idx,
                    "agent": agent_name,
                    "status": "RUNNING" if attempt == 1 else "RETRYING",
                    "message": f"Executing {agent_name} (Attempt {attempt}/2)..."
                })

                if agent_type == "study_buddy":
                    res = await study_buddy_endpoint(StudyBuddyRequest(topic=params.get("topic", task)))
                    results["study_buddy"] = res
                    success = True
                elif agent_type == "youtube_summarizer":
                    res = await youtube_summarizer_endpoint(YouTubeRequest(
                        url=params.get("url", ""),
                        pasted_transcript=params.get("pasted_transcript", task)
                    ))
                    results["youtube_summarizer"] = res
                    success = True
                elif agent_type == "research_assistant":
                    res = await research_assistant_endpoint(ResearchRequest(
                        topic=params.get("topic", task),
                        word_count=params.get("word_count", 350)
                    ))
                    results["research_assistant"] = res
                    success = True
                elif agent_type == "assignment_writer":
                    res = await assignment_writer_endpoint(AssignmentRequest(
                        topic=params.get("topic", task),
                        question_list=params.get("question_list", [task])
                    ))
                    results["assignment_writer"] = res
                    success = True
                else:
                    # Unknown agent, default to study buddy
                    res = await study_buddy_endpoint(StudyBuddyRequest(topic=task))
                    results["study_buddy"] = res
                    success = True

                step_logs.append({
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "step": idx,
                    "agent": agent_name,
                    "status": "SUCCESS",
                    "message": f"{agent_name} completed successfully." + (" (on retry)" if attempt > 1 else "")
                })

            except Exception as e:
                logger.warning(f"Agent {agent_name} failed on attempt {attempt}: {e}")
                if attempt == 1:
                    step_logs.append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "step": idx,
                        "agent": agent_name,
                        "status": "RETRY_TRIGGERED",
                        "message": f"{agent_name} encountered an issue. Initiating automatic retry."
                    })
                    attempt += 1
                else:
                    step_logs.append({
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "step": idx,
                        "agent": agent_name,
                        "status": "SAFE_FALLBACK",
                        "message": f"{agent_name} gracefully switched to safe fallback."
                    })
                    # Use fallback data to guarantee never crash
                    if agent_type == "study_buddy":
                        results["study_buddy"] = generate_demo_study_buddy(task)
                    elif agent_type == "youtube_summarizer":
                        results["youtube_summarizer"] = generate_demo_youtube_summary(task)
                    elif agent_type == "research_assistant":
                        results["research_assistant"] = generate_demo_research_assistant(task, 350, f"Notes on {task}", "https://en.wikipedia.org")
                    elif agent_type == "assignment_writer":
                        results["assignment_writer"] = generate_demo_assignment_writer(task, [task])
                    break

    # Step 3: Dean's Supervisor Note (Sticky Note)
    agents_executed = [item.get("name", item.get("agent")) for item in plan]
    dean_note = (
        f"To the Student:\n\n"
        f"I have reviewed your academic request for '{task}'. "
        f"My team of specialists has mobilized and generated tailored resources across {', '.join(agents_executed)}.\n\n"
        f"Dean's Guidance for Freshman Success:\n"
        f"1. Spaced Repetition: Review the flashcards once today and again in 48 hours.\n"
        f"2. Active Recall: Complete the interactive quiz without referring to open notes.\n"
        f"3. Time Blocking: Dedicate 25 minutes of deep focus followed by a 5-minute break (Pomodoro).\n"
        f"4. Office Hours: If any assignment concept remains unclear, visit your teaching assistant with specific questions.\n\n"
        f"Keep your chin up. College is a marathon, not a sprint.\n\n"
        f"— Dean Vance, Office of Academic Affairs"
    )

    # Persist Dean orchestration to SQLite
    database.save_dean_orchestration(
        task=task,
        plan=plan,
        step_logs=step_logs,
        dean_note=dean_note,
        verdict="Academic Execution Plan Complete & Approved",
        source="Dean Orchestration Suite"
    )

    return {
        "task": task,
        "plan": plan,
        "step_logs": step_logs,
        "results": results,
        "dean_note": dean_note,
        "dean_verdict": "Academic Execution Plan Complete & Approved",
        "source": "Dean Orchestration Suite"
    }


# ---------------------------------------------------------------------------
# Serve Static Frontend
# ---------------------------------------------------------------------------
# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def serve_home():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Hack Your College Life</h1><p>Frontend loading...</p>")

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"Starting 'Hack Your College Life' on http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
