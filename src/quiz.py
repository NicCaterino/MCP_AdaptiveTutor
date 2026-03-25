import re
import json

from src.database import get_db, QuizSession, QuizQuestion, Answer, ContentChunk


def parse_llm_json(text: str):
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group(0))
        raise


def _get_mcp():
    """Lazy import to avoid circular dependency."""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.server import mcp
    return mcp


async def generate_summary_with_llm(context: str) -> dict:
    """Use LLM to extract key concepts, formulas and general idea from content."""
    from mcp.types import SamplingMessage, TextContent

    mcp_instance = _get_mcp()
    if not mcp_instance.sampling_handler:
        return {"key_concepts": [], "formulas": [], "general_idea": ""}

    try:
        result = await mcp_instance.sampling_handler.create_message(
            messages=[SamplingMessage(
                role="user",
                content=TextContent(type="text", text=f"""Analizza questo estratto di materiale didattico e restituisci un JSON con:
- key_concepts: lista dei termini tecnici e concetti principali (max 15)
- formulas: lista di formule/equazioni presenti (lista vuota se nessuna)
- general_idea: 2-3 frasi che descrivono di cosa tratta il materiale

CONTENUTO:
{context}

Rispondi SOLO con JSON valido:
{{"key_concepts": ["...", "..."], "formulas": ["..."], "general_idea": "..."}}""")
            )],
            max_tokens=1000
        )
        if result and result.content:
            data = parse_llm_json(result.content[0].text)
            return {
                "key_concepts": data.get("key_concepts", []),
                "formulas": data.get("formulas", []),
                "general_idea": data.get("general_idea", "")
            }
    except Exception as e:
        print(f"Summary generation failed: {e}")

    return {"key_concepts": [], "formulas": [], "general_idea": ""}


async def generate_summary(material_ids: list[int]) -> dict:
    """Generate a structured summary from indexed material chunks."""
    db = next(get_db())
    try:
        chunks = db.query(ContentChunk).filter(
            ContentChunk.material_id.in_(material_ids)
        ).all()

        if not chunks:
            return {"key_concepts": [], "formulas": [], "general_idea": "Nessun contenuto disponibile"}

        context_text = "\n\n".join([
            f"[Pagina {chunk.page}] {chunk.chunk_text[:400]}"
            for chunk in chunks[:20]
        ])
        return await generate_summary_with_llm(context_text)
    finally:
        db.close()


def get_weak_concepts(material_ids: list[int]) -> list[str]:
    """Return concepts with highest error rate across all past sessions on these materials."""
    db = next(get_db())
    try:
        relevant_sessions = [
            s for s in db.query(QuizSession).all()
            if any(str(mid) in s.material_ids.split(',') for mid in material_ids)
        ]
        if not relevant_sessions:
            return []

        session_ids = [s.id for s in relevant_sessions]
        questions = db.query(QuizQuestion).filter(
            QuizQuestion.session_id.in_(session_ids)
        ).all()

        wrong: dict[str, int] = {}
        total: dict[str, int] = {}

        for q in questions:
            concept = q.page_reference.removeprefix("Concetto: ")
            answer = db.query(Answer).filter(Answer.question_id == q.id).first()
            if answer:
                total[concept] = total.get(concept, 0) + 1
                if not answer.is_correct:
                    wrong[concept] = wrong.get(concept, 0) + 1

        return sorted(
            [c for c in wrong if total.get(c, 0) > 0],
            key=lambda c: wrong[c] / total[c],
            reverse=True
        )[:8]
    finally:
        db.close()


def get_session_summary(session_id: int) -> dict:
    """Get score and answer breakdown for a quiz session."""
    db = next(get_db())
    try:
        session = db.query(QuizSession).filter(QuizSession.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        questions = db.query(QuizQuestion).filter(
            QuizQuestion.session_id == session_id
        ).all()

        answers = []
        correct_count = 0
        for q in questions:
            answer = db.query(Answer).filter(Answer.question_id == q.id).first()
            if answer:
                answers.append({
                    "question_id": q.id,
                    "question": q.question,
                    "user_answer": answer.user_answer,
                    "correct_answer": q.correct_answer,
                    "is_correct": answer.is_correct,
                    "feedback": answer.feedback
                })
                if answer.is_correct:
                    correct_count += 1

        return {
            "session_id": session.id,
            "status": session.status,
            "total_questions": len(questions),
            "answered_questions": len(answers),
            "correct_answers": correct_count,
            "answers": answers
        }
    finally:
        db.close()
