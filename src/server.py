import os
import sys
import json
from typing import Optional, List

from fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_db, Material, ContentChunk, QuizSession, QuizQuestion, Answer, init_db
from src.pdf_loader import extract_text_from_pdf, chunk_text
from src.search import search as search_content_func
from src.quiz import get_session_summary as _quiz_get_session_summary, get_weak_concepts as get_weak_concepts_func

mcp = FastMCP("Insegnante Interattivo")


@mcp.tool()
def list_materials() -> List[dict]:
    """List all indexed materials in the library."""
    db = next(get_db())
    try:
        materials = db.query(Material).order_by(Material.created_at.desc()).all()
        return [
            {
                "id": m.id,
                "filename": m.filename,
                "filepath": m.filepath,
                "num_pages": m.num_pages,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in materials
        ]
    finally:
        db.close()


@mcp.tool()
def remove_material(material_id: int) -> dict:
    """Remove a material and all its content from the library.

    Args:
        material_id: ID of the material to remove
    """
    db = next(get_db())
    try:
        material = db.query(Material).filter(Material.id == material_id).first()
        if not material:
            return {"error": f"Material {material_id} not found"}
        filename = material.filename
        db.query(ContentChunk).filter(ContentChunk.material_id == material_id).delete()
        db.delete(material)
        db.commit()
        return {"removed": filename, "material_id": material_id}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


@mcp.tool()
def scan_and_add_materials(folder_path: str = "materials") -> dict:
    """Scan a folder for PDF files, add new ones, and remove records for deleted files.

    Args:
        folder_path: Path to the folder containing PDF files (default: "materials")
    """
    if not os.path.isdir(folder_path):
        return {"error": f"Folder not found: {folder_path}"}

    db = next(get_db())
    try:
        pdf_files = {
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".pdf")
        }

        existing_materials = db.query(Material).all()
        existing_by_path = {m.filepath: m for m in existing_materials}

        # Remove records for files no longer on disk
        removed = []
        for filepath, material in existing_by_path.items():
            if filepath not in pdf_files:
                db.query(ContentChunk).filter(ContentChunk.material_id == material.id).delete()
                db.delete(material)
                removed.append(material.filename)
        db.commit()

        added = []
        skipped = 0

        for filepath in pdf_files:
            if filepath in existing_by_path:
                skipped += 1
                continue
            try:
                pages = extract_text_from_pdf(filepath)
            except Exception:
                continue

            filename = os.path.basename(filepath)
            material = Material(filename=filename, filepath=filepath, num_pages=len(pages))
            db.add(material)
            db.commit()
            db.refresh(material)

            chunks_created = 0
            for page_data in pages:
                for chunk_text_content in chunk_text(page_data["text"], chunk_size=500):
                    if chunk_text_content.strip():
                        db.add(ContentChunk(
                            material_id=material.id,
                            page=page_data["page"],
                            chunk_text=chunk_text_content
                        ))
                        chunks_created += 1
            db.commit()
            added.append({"id": material.id, "filename": filename, "num_pages": len(pages), "chunks_created": chunks_created})

        return {"added_count": len(added), "removed_count": len(removed), "skipped_count": skipped, "added_materials": added, "removed_materials": removed}
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to scan folder: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
def add_material(filepath: str) -> dict:
    """Add a new PDF material to the library.

    Args:
        filepath: Path to the PDF file to add
    """
    if not os.path.exists(filepath):
        return {"error": f"File not found: {filepath}"}

    try:
        pages = extract_text_from_pdf(filepath)
    except Exception as e:
        return {"error": f"Failed to extract text: {str(e)}"}

    db = next(get_db())
    try:
        filename = os.path.basename(filepath)
        material = Material(filename=filename, filepath=filepath, num_pages=len(pages))
        db.add(material)
        db.commit()
        db.refresh(material)

        chunks_created = 0
        for page_data in pages:
            for chunk_text_content in chunk_text(page_data["text"], chunk_size=500):
                if chunk_text_content.strip():
                    db.add(ContentChunk(
                        material_id=material.id,
                        page=page_data["page"],
                        chunk_text=chunk_text_content
                    ))
                    chunks_created += 1
        db.commit()
        return {"material_id": material.id, "num_pages": len(pages), "chunks_created": chunks_created}
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to add material: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
def search_content(query: str, material_id: Optional[int] = None, limit: int = 10) -> List[dict]:
    """Search across all indexed content.

    Args:
        query: Search query string
        material_id: Optional material ID to limit search to
        limit: Maximum number of results (default 10)
    """
    try:
        results = search_content_func(query, material_id=material_id)
        return [
            {
                "chunk_text": r.chunk_text[:500] + "..." if len(r.chunk_text) > 500 else r.chunk_text,
                "page": r.page,
                "material_id": r.material_id,
                "material_name": r.material_name
            }
            for r in results[:limit]
        ]
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool()
def get_quiz_context(material_ids: List[int], adaptive: bool = False) -> dict:
    """Fetch material content so the AI can generate quiz questions directly.

    Returns raw text chunks from the indexed PDFs. The AI uses this content
    to write questions and plausible answer options grounded in the material.

    If adaptive=True, also returns weak concepts from past sessions so the AI
    can prioritize those topics.

    Args:
        material_ids: List of material IDs to load
        adaptive: If True, include weak concepts from past quiz history
    """
    db = next(get_db())
    try:
        materials = db.query(Material).filter(Material.id.in_(material_ids)).all()
        if not materials:
            return {"error": "No materials found for the given IDs"}

        chunks = db.query(ContentChunk).filter(
            ContentChunk.material_id.in_(material_ids)
        ).order_by(ContentChunk.material_id, ContentChunk.page).all()

        if not chunks:
            return {"error": "No content found — add the material first with add_material"}

        # Return up to 20 chunks spread across the document
        step = max(1, len(chunks) // 20)
        sampled = chunks[::step][:20]

        content = "\n\n".join([
            f"[Pagina {c.page}] {c.chunk_text}"
            for c in sampled
        ])

        result = {
            "material_info": [
                {"id": m.id, "filename": m.filename, "num_pages": m.num_pages}
                for m in materials
            ],
            "content": content,
            "total_chunks": len(chunks)
        }

        if adaptive:
            weak = get_weak_concepts_func(material_ids)
            result["weak_concepts"] = weak
            result["mode"] = "adaptive" if weak else "standard (no history yet)"

        return result
    finally:
        db.close()


@mcp.tool()
def create_quiz_session(material_ids: List[int], questions: List[dict]) -> dict:
    """Save AI-generated questions and open a new quiz session.

    Call this after generating questions from get_quiz_context.

    Args:
        material_ids: Material IDs this quiz covers
        questions: List of question objects, each with:
            - question (str): question text
            - options (list[str]): ["A) ...", "B) ...", "C) ...", "D) ..."]
            - correct_answer (str): "A", "B", "C", or "D"
            - concept (str): the concept being tested (used for adaptive tracking)
    """
    if not questions:
        return {"error": "No questions provided"}

    db = next(get_db())
    try:
        session = QuizSession(
            material_ids=",".join(str(mid) for mid in material_ids),
            status="active"
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        saved = []
        for q_data in questions:
            opts = q_data.get("options", [])
            q = QuizQuestion(
                session_id=session.id,
                question=q_data.get("question", ""),
                options=json.dumps(opts),
                correct_answer=q_data.get("correct_answer", "A").strip().upper(),
                page_reference=f"Concetto: {q_data.get('concept', '')}",
                material_id=material_ids[0]
            )
            db.add(q)
            db.commit()
            db.refresh(q)
            saved.append({"id": q.id, "question": q.question, "options": opts})

        return {
            "session_id": session.id,
            "status": "active",
            "total_questions": len(saved),
            "questions": saved
        }
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to create session: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
def get_question(session_id: int) -> Optional[dict]:
    """Get the next unanswered question from a quiz session.

    Returns None when all questions have been answered.

    Args:
        session_id: The quiz session ID
    """
    db = next(get_db())
    try:
        answered_ids = [
            q[0] for q in
            db.query(Answer.question_id)
            .join(QuizQuestion, Answer.question_id == QuizQuestion.id)
            .filter(QuizQuestion.session_id == session_id)
            .all()
        ]

        next_q = db.query(QuizQuestion).filter(
            QuizQuestion.session_id == session_id,
            ~QuizQuestion.id.in_(answered_ids)
        ).first()

        if not next_q:
            return None

        try:
            options = json.loads(next_q.options) if next_q.options else []
        except (json.JSONDecodeError, TypeError):
            options = []

        return {
            "question_id": next_q.id,
            "question": next_q.question,
            "options": options,
            "concept": next_q.page_reference.removeprefix("Concetto: "),
            "material_id": next_q.material_id
        }
    finally:
        db.close()


@mcp.tool()
def evaluate_answer(question_id: int, user_answer: str) -> dict:
    """Record the student's answer and return correctness with context for explanation.

    Args:
        question_id: The question ID being answered
        user_answer: The student's selected answer (A, B, C, or D)

    Returns:
        is_correct, correct_answer, question, options, concept, and a content
        snippet from the material so the AI can explain the correct answer.
    """
    db = next(get_db())
    try:
        question = db.query(QuizQuestion).filter(QuizQuestion.id == question_id).first()
        if not question:
            return {"error": f"Question {question_id} not found"}

        user_clean = user_answer.strip().upper().split(")")[0].strip()
        correct_clean = question.correct_answer.strip().upper().split(")")[0].strip()
        is_correct = user_clean == correct_clean

        # Fetch a content snippet so the AI can ground its explanation
        chunks = db.query(ContentChunk).filter(
            ContentChunk.material_id == question.material_id
        ).limit(4).all()
        content_snippet = "\n".join(c.chunk_text[:250] for c in chunks)

        feedback = "Corretto" if is_correct else f"Sbagliato — risposta corretta: {question.correct_answer}"

        db.add(Answer(
            question_id=question_id,
            user_answer=user_answer,
            is_correct=is_correct,
            feedback=feedback
        ))
        db.commit()

        try:
            options = json.loads(question.options) if question.options else []
        except (json.JSONDecodeError, TypeError):
            options = []

        return {
            "is_correct": is_correct,
            "correct_answer": question.correct_answer,
            "question": question.question,
            "options": options,
            "concept": question.page_reference.removeprefix("Concetto: "),
            "content_snippet": content_snippet
        }
    except Exception as e:
        db.rollback()
        return {"error": f"Failed to evaluate answer: {str(e)}"}
    finally:
        db.close()


@mcp.tool()
def get_session_summary(session_id: int) -> dict:
    """Get score and full answer breakdown for a completed quiz session.

    Args:
        session_id: The quiz session ID
    """
    try:
        summary = _quiz_get_session_summary(session_id)
        total = summary.get("total_questions", 0)
        correct = summary.get("correct_answers", 0)
        return {
            "session_id": summary.get("session_id"),
            "status": summary.get("status"),
            "total_questions": total,
            "answered_questions": summary.get("answered_questions", 0),
            "correct_answers": correct,
            "score_percentage": round((correct / total) * 100, 1) if total > 0 else 0,
            "answers": summary.get("answers", [])
        }
    except Exception as e:
        return {"error": f"Failed to get session summary: {str(e)}"}


@mcp.prompt()
def list_materials_prompt() -> str:
    """Prompt to list all materials, auto-syncing with the materials folder first."""
    return """First call `scan_and_add_materials` to sync the library with the materials folder (picks up new PDFs and removes deleted ones).
Then call `list_materials` and show the current library to the student.
For each material show: ID, name, number of pages.
If the library is empty, tell the student to drop PDF files into the materials/ folder and run this again."""


@mcp.prompt()
def add_material_prompt() -> str:
    """Prompt to add a new PDF material to the library."""
    return """Help the student add a PDF to the library.
Ask for the file path, then call `add_material` with it.
On success, confirm pages extracted and chunks created, and suggest starting a quiz or searching.
On error, help diagnose the issue (wrong path, unsupported file, etc.)."""


@mcp.prompt()
def start_quiz_prompt() -> str:
    """Prompt to start a quiz session and run it interactively."""
    return """Run an interactive quiz session with the student. Follow these steps:

1. Call `list_materials` — show available materials and ask which to use.
2. Ask: standard quiz (random coverage) or adaptive quiz (targets past weak spots)?
3. Call `get_quiz_context` with the chosen material IDs.
   - For adaptive: pass adaptive=true to also receive weak concepts from past sessions.
4. Read the returned content carefully, then generate N questions yourself (default 5).
   Rules for questions:
   - Each question tests understanding of a specific concept from the content
   - 4 options (A/B/C/D): one correct, three plausible distractors using real terms from the material
   - If adaptive: prioritize questions on the weak_concepts list
   - No references to page numbers
5. Call `create_quiz_session` with material_ids and your generated questions list.
   Each question object: {question, options, correct_answer, concept}
6. Loop until all questions are answered:
   a. Call `get_question` with the session_id — show the question and options.
   b. Wait for the student's answer.
   c. Call `evaluate_answer` with question_id and the answer.
   d. Use the returned content_snippet and concept to explain why the answer is correct or wrong.
   e. If `get_question` returns null, the quiz is over.
7. Call `get_session_summary` — show the final score with encouragement.
   If score < 60%: suggest calling get_quiz_context with adaptive=true for a targeted follow-up."""


@mcp.prompt()
def generate_summary_prompt() -> str:
    """Prompt to summarize PDF material for the student."""
    return """Help the student understand their material.

1. Call `list_materials` — show available materials and ask which to summarize.
2. Call `get_quiz_context` with the chosen material IDs.
3. Read the returned content and produce a structured summary:
   - 📚 Idea generale (2-3 frasi)
   - Concetti chiave (bullet list)
   - Formule presenti (se ci sono)
4. Ask if they want to start a quiz or search for a specific topic."""


@mcp.prompt()
def search_prompt() -> str:
    """Prompt to search content in the library."""
    return """Ask the student what to search for, then call `search_content` with their query.
For each result show: text excerpt, page number, material name.
If no results, suggest different keywords or adding more materials."""


@mcp.prompt()
def review_prompt() -> str:
    """Prompt to review quiz session results."""
    return """Ask the student for their session ID, then call `get_session_summary`.
Show: score percentage, answered vs total, which answers were correct/incorrect.
Give encouraging feedback. If score < 60%, suggest a follow-up with get_quiz_context adaptive=true."""


if __name__ == "__main__":
    init_db()
    mcp.run(transport="stdio")
