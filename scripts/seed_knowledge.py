"""
Attora -- Seed Knowledge Documents from PDF

Parses "Overcome7Objections.pdf" by Tom Perkins, chunks it by
section/heading, assigns keyword tags, and inserts rows into
the knowledge_documents table.

Usage:
    python scripts/seed_knowledge.py

Requires:
    - DATABASE_URL or DATABASE_URL_SYNC env var (or .env file)
    - pdfplumber installed
    - Overcome7Objections.pdf at the project root
"""

import os
import sys
import uuid
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PDF_PATH = PROJECT_ROOT / "Overcome7Objections.pdf"
SOURCE_FILE = "Overcome7Objections.pdf"

# Load .env from backend directory
load_dotenv(PROJECT_ROOT / "backend" / ".env")

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

def get_sync_database_url() -> str:
    """Return a synchronous (psycopg2/libpq) database URL."""
    url = os.getenv("DATABASE_URL_SYNC")
    if url:
        return url
    url = os.getenv("DATABASE_URL", "")
    # Convert async driver to sync if needed
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    if not url:
        print("ERROR: No DATABASE_URL_SYNC or DATABASE_URL found in environment.")
        print("       Set one in backend/.env or export it.")
        sys.exit(1)
    return url


# ---------------------------------------------------------------------------
# PDF text extraction helpers
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: Path) -> dict[int, str]:
    """Return {page_number: text} for every page (1-indexed)."""
    pages: dict[int, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            pages[i + 1] = page_text
    return pages


def pages_text(pages: dict[int, str], start: int, end: int) -> str:
    """Concatenate text from pages[start] through pages[end] inclusive."""
    parts = []
    for p in range(start, end + 1):
        t = pages.get(p, "")
        if t:
            parts.append(t)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Chunk definitions
# ---------------------------------------------------------------------------
# Each chunk is a dict with:
#   title, section_name, category, keywords, page_start, page_end
#
# The content will be extracted from the PDF at those page ranges.
# For page 7 (the 7 objections list), we split by objection type
# programmatically below.
# ---------------------------------------------------------------------------

STATIC_CHUNKS = [
    {
        "title": "Introduction",
        "section_name": "Introduction",
        "category": "objection_handling",
        "keywords": ["sales", "objection_handling", "overview", "comp_session"],
        "page_start": 3,
        "page_end": 3,
    },
    {
        "title": "Overview",
        "section_name": "Overview",
        "category": "objection_handling",
        "keywords": ["sales", "objection_handling", "overview", "comp_session"],
        "page_start": 4,
        "page_end": 4,
    },
    {
        "title": "The Preparation Phase",
        "section_name": "The Preparation Phase",
        "category": "objection_handling",
        "keywords": ["preparation", "strategy", "confidence", "comp_session"],
        "page_start": 5,
        "page_end": 5,
        "extract_before": "Anticipate and Strategize",
    },
    {
        "title": "Anticipate and Strategize",
        "section_name": "The Preparation Phase",
        "category": "objection_handling",
        "keywords": ["preparation", "strategy", "anticipation", "objection_handling"],
        "page_start": 5,
        "page_end": 5,
        "extract_section": "Anticipate and Strategize",
    },
    {
        "title": "Rehearse",
        "section_name": "The Preparation Phase",
        "category": "objection_handling",
        "keywords": ["preparation", "rehearsal", "confidence", "practice"],
        "page_start": 6,
        "page_end": 6,
        "extract_section": "Rehearse",
    },
    {
        "title": "Have Faith",
        "section_name": "The Preparation Phase",
        "category": "objection_handling",
        "keywords": ["preparation", "confidence", "mindset", "belief"],
        "page_start": 6,
        "page_end": 6,
        "extract_section": "Have Faith",
    },
    # -- Page 7: The 7 objection types are handled separately below --
    {
        "title": "Handling Objections - Step 1: Acceptance",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["technique", "acceptance", "empathy", "acknowledgment", "objection_handling"],
        "page_start": 8,
        "page_end": 8,
        "extract_section": "Step 1",
    },
    {
        "title": "Handling Objections - Step 2: Use This Simple Question",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["technique", "permission", "simple_question", "trust", "objection_handling"],
        "page_start": 8,
        "page_end": 8,
        "extract_section": "Step 2",
    },
    {
        "title": "Handling Objections - Step 3: Speak to the Objection",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["technique", "reframing", "speak_to_objection", "objection_handling"],
        "page_start": 9,
        "page_end": 9,
        "extract_before": "The \u201cNot Ready\u201d Objection",
    },
    {
        "title": "Example Script: The 'Not Ready' Objection",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["script", "example", "conversation", "objection", "not_ready"],
        "page_start": 9,
        "page_end": 10,
    },
    {
        "title": "The Money Objection - Strategy",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["technique", "objection", "no_money", "pricing", "value"],
        "page_start": 11,
        "page_end": 11,
        "extract_before": "Money Objection - Examples",
    },
    {
        "title": "Example Script: The Money Objection",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["script", "example", "conversation", "objection", "no_money"],
        "page_start": 11,
        "page_end": 13,
    },
    {
        "title": "The 'Need to Discuss with Someone Else' Objection - Strategy and Example",
        "section_name": "Handling Objections",
        "category": "objection_handling",
        "keywords": ["script", "example", "conversation", "objection", "need_discussion"],
        "page_start": 14,
        "page_end": 15,
    },
    # -- Critical Success Factors (p16-19) --
    {
        "title": "Critical Success Factor: Obtaining Permission",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "permission", "trust", "objection_handling"],
        "page_start": 16,
        "page_end": 16,
        "extract_section": "Obtaining Permission",
    },
    {
        "title": "Critical Success Factor: Hold to Higher Level of Expectation",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "challenge", "expectation", "accountability"],
        "page_start": 16,
        "page_end": 16,
        "extract_section": "Hold to Higher Level",
    },
    {
        "title": "Critical Success Factor: Tap Into Emotions",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "emotions", "motivation", "feelings"],
        "page_start": 17,
        "page_end": 17,
        "extract_section": "Tap Into Emotions",
    },
    {
        "title": "Critical Success Factor: Professional Posture",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "professional_posture", "experience", "credibility"],
        "page_start": 17,
        "page_end": 17,
        "extract_section": "From a Position of Experience",
    },
    {
        "title": "Critical Success Factor: Approach As If Coaching for Six Months",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "professional_posture", "rapport", "confidence"],
        "page_start": 17,
        "page_end": 17,
        "extract_section": "Approach As If",
    },
    {
        "title": "Critical Success Factor: Together - Come to a Decision",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "collaboration", "trust", "decision"],
        "page_start": 17,
        "page_end": 17,
        "extract_section": "Together",
    },
    {
        "title": "Critical Success Factor: Say What's On Your Mind",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "directness", "honesty", "objection_handling"],
        "page_start": 18,
        "page_end": 18,
        "extract_section": "Say What",
    },
    {
        "title": "Critical Success Factor: Schedule Next Appointment",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "follow_up", "urgency", "scheduling"],
        "page_start": 18,
        "page_end": 18,
        "extract_section": "Schedule the Next Appointment",
    },
    {
        "title": "Critical Success Factor: Reach an Agreement and Secure Payment",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "agreement", "payment", "conversion"],
        "page_start": 18,
        "page_end": 19,
        "extract_section": "Reach an Agreement",
    },
    {
        "title": "Critical Success Factor: Avoid Hard/Pressure Selling",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "trust", "anti_pressure", "ethics"],
        "page_start": 19,
        "page_end": 19,
        "extract_section": "Avoid Hard",
    },
    {
        "title": "Critical Success Factor: Offer Free Subscription",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "closing", "newsletter", "lead_nurture", "follow_up"],
        "page_start": 19,
        "page_end": 19,
        "extract_section": "Offer Free Subscription",
    },
    {
        "title": "Critical Success Factor: Practice Overcoming Objections",
        "section_name": "Critical Success Factors",
        "category": "sales_sop",
        "keywords": ["technique", "practice", "rehearsal", "role_play", "objection_handling"],
        "page_start": 19,
        "page_end": 19,
        "extract_section": "Practice Overcoming",
    },
    # -- Summary --
    {
        "title": "Summary",
        "section_name": "Summary",
        "category": "objection_handling",
        "keywords": ["summary", "recap", "conversion_rate", "objection_handling"],
        "page_start": 20,
        "page_end": 20,
    },
    # -- Appendix --
    {
        "title": "Appendix: Typical Objections Coaches Often Encounter",
        "section_name": "Appendix",
        "category": "objection_handling",
        "keywords": ["appendix", "objection", "common_objections", "coaching", "responses"],
        "page_start": 21,
        "page_end": 22,
    },
    {
        "title": "Exercise: Be Prepared! Overcoming Objections",
        "section_name": "Appendix",
        "category": "objection_handling",
        "keywords": ["exercise", "practice", "objection", "worksheet", "preparation"],
        "page_start": 23,
        "page_end": 23,
    },
    {
        "title": "Exercise: Overcoming Objections by Relating to Your Client",
        "section_name": "Appendix",
        "category": "objection_handling",
        "keywords": ["exercise", "practice", "objection", "feel_felt_found", "empathy"],
        "page_start": 24,
        "page_end": 24,
    },
]

# The 7 objection types from page 7 -- one chunk each
OBJECTION_TYPES = [
    {
        "title": "The 7 Objections: No Time",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "no_time", "busy", "scheduling"],
    },
    {
        "title": "The 7 Objections: Not Ready",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "not_ready", "hesitation", "delay"],
    },
    {
        "title": "The 7 Objections: No Money",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "no_money", "affordability", "price"],
    },
    {
        "title": "The 7 Objections: Uncertain of Value",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "uncertain_value", "doubt", "skepticism"],
    },
    {
        "title": "The 7 Objections: Need to Discuss with Someone Else",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "need_discussion", "spouse", "decision_maker"],
    },
    {
        "title": "The 7 Objections: Need to Think About It",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "need_think", "stalling", "indecision"],
    },
    {
        "title": "The 7 Objections: Check Out Other Facilities/Coaches",
        "section_name": "The 7 Main Objections",
        "category": "objection_handling",
        "keywords": ["objection", "comparison_shopping", "competition", "alternatives"],
    },
]


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def extract_section_text(full_text: str, marker: str, next_markers: list[str] | None = None) -> str:
    """
    Extract text from *full_text* starting at the first line containing
    *marker* and ending just before any line containing one of *next_markers*
    (or end of text).
    """
    lines = full_text.split("\n")
    start_idx = None
    for i, line in enumerate(lines):
        if marker.lower() in line.lower():
            start_idx = i
            break
    if start_idx is None:
        return full_text  # fallback: return everything

    end_idx = len(lines)
    if next_markers:
        for i in range(start_idx + 1, len(lines)):
            for nm in next_markers:
                if nm.lower() in lines[i].lower():
                    end_idx = i
                    break
            if end_idx != len(lines):
                break

    return "\n".join(lines[start_idx:end_idx]).strip()


def extract_before_text(full_text: str, marker: str) -> str:
    """Extract text from the start up to (but not including) *marker*."""
    lines = full_text.split("\n")
    for i, line in enumerate(lines):
        if marker.lower() in line.lower():
            return "\n".join(lines[:i]).strip()
    return full_text.strip()


def build_objection_chunks(page7_text: str) -> list[dict]:
    """Split page 7 into individual objection-type chunks."""
    # Markers for each objection on page 7
    markers = [
        ("No Time", "Not Ready"),
        ("Not Ready", "No Money"),
        ("No Money", "Uncertain of Value"),
        ("Uncertain of Value", "Need to Discuss with Someone Else"),
        ("Need to Discuss with Someone Else", "Need to Think About"),
        ("Need to Think About", "Check Out Other"),
        ("Check Out Other", None),
    ]

    chunks = []
    for i, obj_def in enumerate(OBJECTION_TYPES):
        start_marker, end_marker = markers[i]
        section = extract_section_text(
            page7_text,
            start_marker,
            [end_marker] if end_marker else None,
        )
        chunks.append({
            **obj_def,
            "content": section,
        })
    return chunks


def build_all_chunks(pages: dict[int, str]) -> list[dict]:
    """Build the complete list of chunks with content extracted from pages."""
    chunks: list[dict] = []

    # --- Static chunks ---
    for defn in STATIC_CHUNKS:
        raw = pages_text(pages, defn["page_start"], defn["page_end"])

        # Optionally slice to a sub-section
        if "extract_section" in defn:
            # Try to find the next section header on the same page range
            content = extract_section_text(raw, defn["extract_section"])
        elif "extract_before" in defn:
            content = extract_before_text(raw, defn["extract_before"])
        else:
            content = raw.strip()

        # Skip if we got nothing useful
        if not content or len(content) < 10:
            content = raw.strip()

        chunks.append({
            "title": defn["title"],
            "section_name": defn["section_name"],
            "category": defn["category"],
            "keywords": defn["keywords"],
            "content": content,
        })

    # --- Page 7: individual objection types ---
    page7_text = pages.get(7, "")
    # Intro paragraph for "The Top 7 Objections" section
    intro_text = extract_before_text(page7_text, "No Time")
    if intro_text and len(intro_text) > 20:
        chunks.append({
            "title": "The Top 7 Objections - Introduction",
            "section_name": "The 7 Main Objections",
            "category": "objection_handling",
            "keywords": ["sales", "objection_handling", "overview", "seven_objections"],
            "content": intro_text,
        })

    objection_chunks = build_objection_chunks(page7_text)
    chunks.extend(objection_chunks)

    return chunks


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------

INSERT_SQL = text("""
    INSERT INTO knowledge_documents
        (id, title, content, keywords, source_file, section_name, category, is_active)
    VALUES
        (:id, :title, :content, :keywords, :source_file, :section_name, :category, true)
""")

DELETE_SQL = text("""
    DELETE FROM knowledge_documents WHERE source_file = :source_file
""")


def seed(chunks: list[dict], db_url: str) -> None:
    """Insert all chunks into the database (idempotent)."""
    engine = create_engine(db_url, echo=False)

    with engine.begin() as conn:
        # Idempotent: remove previous rows from this source file
        result = conn.execute(DELETE_SQL, {"source_file": SOURCE_FILE})
        deleted = result.rowcount
        if deleted:
            print(f"  Cleared {deleted} existing row(s) for source_file='{SOURCE_FILE}'")

        for i, chunk in enumerate(chunks, 1):
            conn.execute(INSERT_SQL, {
                "id": str(uuid.uuid4()),
                "title": chunk["title"],
                "content": chunk["content"],
                "keywords": chunk["keywords"],
                "source_file": SOURCE_FILE,
                "section_name": chunk["section_name"],
                "category": chunk["category"],
            })
            # Truncate long content for display
            preview = chunk["content"][:80].replace("\n", " ")
            print(f"  [{i:2d}/{len(chunks)}] {chunk['title']}")
            print(f"         section={chunk['section_name']}  category={chunk['category']}")
            print(f"         keywords={chunk['keywords']}")
            print(f"         content preview: {preview}...")
            print()

    engine.dispose()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Attora -- Seed Knowledge Documents")
    print("=" * 60)
    print()

    # Validate PDF exists
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        sys.exit(1)
    print(f"  PDF:  {PDF_PATH}")

    # Get database URL
    db_url = get_sync_database_url()
    # Mask password in display
    display_url = db_url
    if "@" in display_url:
        pre_at = display_url.split("@")[0]
        post_at = display_url.split("@", 1)[1]
        if ":" in pre_at:
            user_part = pre_at.rsplit(":", 1)[0]
            display_url = f"{user_part}:****@{post_at}"
    print(f"  DB:   {display_url}")
    print()

    # Extract PDF text
    print(">>> Extracting PDF text...")
    pages = extract_pages(PDF_PATH)
    print(f"  Extracted {len(pages)} pages")
    print()

    # Build chunks
    print(">>> Building chunks...")
    chunks = build_all_chunks(pages)
    print(f"  Built {len(chunks)} chunks")
    print()

    # Insert into database
    print(">>> Inserting into knowledge_documents...")
    print()
    seed(chunks, db_url)

    print("=" * 60)
    print(f"Done! Inserted {len(chunks)} knowledge document chunks.")
    print("=" * 60)


if __name__ == "__main__":
    main()
