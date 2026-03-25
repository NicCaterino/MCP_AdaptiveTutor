import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.quiz import (
    get_session,
    list_sessions,
    generate_questions,
    generate_questions_async,
    start_quiz,
    evaluate_answer,
    get_question,
    get_session_summary,
    QuizQuestionDisplay,
    AnswerResponse,
    generate_summary_with_llm,
    generate_quiz_questions_with_llm
)
from src.database import QuizSession, QuizQuestion, Answer, ContentChunk


class TestQuizModuleInterface:
    """Test Task 1: Quiz module interface and types."""
    
    def test_quiz_question_display_type(self):
        """QuizQuestionDisplay should have correct fields."""
        q = QuizQuestionDisplay(
            id=1,
            question="Test question?",
            options=["A", "B", "C", "D"],
            page_reference="Page 1"
        )
        assert q.id == 1
        assert q.question == "Test question?"
        assert len(q.options) == 4
        assert q.page_reference == "Page 1"
    
    def test_answer_response_type(self):
        """AnswerResponse should have correct fields."""
        r = AnswerResponse(
            is_correct=True,
            feedback="Correct!",
            correct_answer="A",
            page_reference="Page 1"
        )
        assert r.is_correct is True
        assert r.feedback == "Correct!"
        assert r.correct_answer == "A"
        assert r.page_reference == "Page 1"


class TestGetSession:
    """Test get_session function."""
    
    @patch('src.quiz.get_db')
    def test_get_session_returns_session(self, mock_get_db):
        """get_session should return a session by ID."""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_session.material_ids = "1,2,3"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session
        mock_get_db.return_value = iter([mock_db])
        
        result = get_session(1)
        
        assert result is not None
        assert result.material_ids == [1, 2, 3]
    
    @patch('src.quiz.get_db')
    def test_get_session_returns_none_when_not_found(self, mock_get_db):
        """get_session should return None when session not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])
        
        result = get_session(999)
        
        assert result is None


class TestListSessions:
    """Test list_sessions function."""
    
    @patch('src.quiz.get_db')
    def test_list_sessions_returns_all_sessions(self, mock_get_db):
        """list_sessions should return all sessions ordered by created_at desc."""
        mock_db = MagicMock()
        mock_sessions = [MagicMock(material_ids="1,2"), MagicMock(material_ids="3")]
        mock_db.query.return_value.order_by.return_value.all.return_value = mock_sessions
        mock_get_db.return_value = iter([mock_db])
        
        result = list_sessions()
        
        assert len(result) == 2
        assert result[0].material_ids == [1, 2]
        assert result[1].material_ids == [3]


class TestQuestionGeneration:
    """Test Task 2: Question generation with LLM."""
    
    @patch('src.quiz.get_db')
    @patch('src.quiz.generate_quiz_questions_with_llm', new_callable=AsyncMock)
    @patch('src.quiz.generate_summary_with_llm', new_callable=AsyncMock)
    def test_generate_questions_creates_session(self, mock_summary, mock_generate, mock_get_db):
        """generate_questions should create a new quiz session."""
        mock_summary.return_value = {
            "key_concepts": ["concetto1", "concetto2"],
            "formulas": [],
            "general_idea": "Idea generale"
        }
        mock_generate.return_value = [
            {
                "question": "Domanda 1?",
                "options": ["A) A", "B) B", "C) C", "D) D"],
                "correct_answer": "A",
                "page_reference": "Concetto: concetto1"
            },
            {
                "question": "Domanda 2?",
                "options": ["A) A", "B) B", "C) C", "D) D"],
                "correct_answer": "B",
                "page_reference": "Concetto: concetto2"
            }
        ]
        
        mock_db = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.page = 1
        mock_chunk.chunk_text = "Test content is about something important."
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_chunk]
        
        def add_side_effect(obj):
            obj.id = 1
        
        mock_db.add = add_side_effect
        mock_db.refresh = MagicMock(side_effect=lambda x: setattr(x, 'id', 1))
        
        mock_get_db.return_value = iter([mock_db])
        
        session, questions = generate_questions([1], num_questions=2)
        
        assert session is not None
        assert len(questions) == 2
        mock_summary.assert_called_once()
        mock_generate.assert_called_once()
    
    @patch('src.quiz.get_db')
    @patch('src.quiz.generate_summary_with_llm', new_callable=AsyncMock)
    def test_generate_questions_raises_on_no_content(self, mock_summary, mock_get_db):
        """generate_questions should raise ValueError when no content found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])
        mock_summary.return_value = {"key_concepts": [], "formulas": [], "general_idea": ""}
        
        with pytest.raises(ValueError, match="No content found"):
            generate_questions([1])


class TestStartQuiz:
    """Test start_quiz convenience function."""
    
    @patch('src.quiz.generate_questions')
    def test_start_quiz_returns_dict(self, mock_generate):
        """start_quiz should return dict with session_id and questions."""
        mock_session = MagicMock(id=1, status="active")
        mock_question = QuizQuestionDisplay(
            id=1,
            question="Test?",
            options=["A", "B", "C", "D"],
            page_reference="Page 1"
        )
        mock_generate.return_value = (mock_session, [mock_question])
        
        result = start_quiz([1])
        
        assert "session_id" in result
        assert "status" in result
        assert "questions" in result
        assert result["session_id"] == 1
        assert result["status"] == "active"


class TestEvaluateAnswer:
    """Test Task 3: Answer evaluation."""
    
    def test_answer_response_correct(self):
        """AnswerResponse should handle correct answer."""
        response = AnswerResponse(
            is_correct=True,
            feedback="Correct!",
            correct_answer="Option A",
            page_reference="Page 1"
        )
        assert response.is_correct is True
        assert response.feedback == "Correct!"
        assert response.correct_answer == "Option A"
    
    def test_answer_response_incorrect(self):
        """AnswerResponse should handle incorrect answer."""
        response = AnswerResponse(
            is_correct=False,
            feedback="Incorrect. The correct answer is: Option A",
            correct_answer="Option A",
            page_reference="Page 1"
        )
        assert response.is_correct is False
        assert "Incorrect" in response.feedback
        assert response.correct_answer == "Option A"


class TestGetQuestion:
    """Test get_question function."""
    
    @patch('src.quiz.get_db')
    def test_get_question_returns_display(self, mock_get_db):
        """get_question should return QuizQuestionDisplay."""
        mock_db = MagicMock()
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question.question = "Test?"
        mock_question.page_reference = "Page 1"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_question
        mock_get_db.return_value = iter([mock_db])
        
        result = get_question(1)
        
        assert result is not None
        assert result.id == 1
        assert result.question == "Test?"
        assert len(result.options) == 4
    
    @patch('src.quiz.get_db')
    def test_get_question_returns_none_when_not_found(self, mock_get_db):
        """get_question should return None when question not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])
        
        result = get_question(999)
        
        assert result is None


class TestGetSessionSummary:
    """Test get_session_summary function."""
    
    @patch('src.quiz.get_db')
    def test_get_session_summary_returns_stats(self, mock_get_db):
        """get_session_summary should return session statistics."""
        mock_db = MagicMock()
        
        mock_session = MagicMock()
        mock_session.id = 1
        mock_session.status = "active"
        
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question.question = "Test?"
        
        mock_answer = MagicMock()
        mock_answer.user_answer = "A"
        mock_answer.is_correct = True
        mock_answer.feedback = "Correct!"
        
        def query_side_effect(model):
            mock_query = MagicMock()
            if model == QuizSession:
                mock_query.filter.return_value.first.return_value = mock_session
            elif model == QuizQuestion:
                mock_query.filter.return_value.all.return_value = [mock_question]
            elif model == Answer:
                mock_query.filter.return_value.first.return_value = mock_answer
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        mock_get_db.return_value = iter([mock_db])
        
        result = get_session_summary(1)
        
        assert result["session_id"] == 1
        assert result["status"] == "active"
        assert result["total_questions"] == 1
        assert result["answered_questions"] == 1
        assert result["correct_answers"] == 1
    
    @patch('src.quiz.get_db')
    def test_get_session_summary_raises_when_not_found(self, mock_get_db):
        """get_session_summary should raise ValueError when session not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])
        
        with pytest.raises(ValueError, match="Session 999 not found"):
            get_session_summary(999)
