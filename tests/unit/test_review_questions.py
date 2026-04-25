"""
Unit tests: Review Question Generation (Feature A, §2.2)

Tests AC1: Review dialog generates exactly the questions defined in §2.2
"""
import pytest


class TestReviewQuestionsMinimal:
    """Q1 and Q4 are always asked — minimum required questions."""

    def test_q1_always_included(self):
        """Q1 is always in the question set (most important gap)."""
        rq = pytest.importorskip("review_questions")
        questions = rq.generate_review_questions(session_text="", session_files=[])
        assert any("most important" in q.lower() or "what happened" in q.lower() for q in questions)

    def test_q4_always_included(self):
        """Q4 (open threads / follow-ups / where this leads) is always in the set."""
        rq = pytest.importorskip("review_questions")
        questions = rq.generate_review_questions(session_text="", session_files=[])
        assert any(
            "open thread" in q.lower()
            or "follow-up" in q.lower()
            or "where this leads" in q.lower()
            or "what needs to happen" in q.lower()
            for q in questions
        )

    def test_minimum_two_questions(self):
        """At minimum, exactly two questions are returned (Q1 + Q4)."""
        rq = pytest.importorskip("review_questions")
        questions = rq.generate_review_questions(session_text="", session_files=[])
        assert len(questions) >= 2

    def test_questions_are_numbered(self):
        """Each question is numbered so answers can be tied back compactly."""
        rq = pytest.importorskip("review_questions")
        questions = rq.generate_review_questions(session_text="", session_files=[])
        for q in questions:
            assert any(q.strip().startswith(f"[{i}]") for i in range(1, 10)), \
                f"Question not numbered: {q}"

    def test_questions_are_short(self):
        """Each question fits in one focused sentence (under 200 chars)."""
        rq = pytest.importorskip("review_questions")
        questions = rq.generate_review_questions(session_text="", session_files=[])
        for q in questions:
            assert len(q) < 200, f"Question too long ({len(q)} chars): {q}"


class TestReviewQuestionsConditional:
    """Q2, Q3, Q5 are conditionally included based on session content signals."""

    def test_q2_triggered_when_unfinished_work_mentioned(self):
        """Q2 asked when session signals unfinished work (contains 'left', 'pending', etc.)."""
        rq = pytest.importorskip("review_questions")
        unfinished_text = "The vARRR bridge audit was still left pending when we ran out of time."
        questions = rq.generate_review_questions(session_text=unfinished_text, session_files=[])
        assert any("unfinished" in q.lower() or "left" in q.lower() for q in questions)

    def test_q3_triggered_when_surprise_mentioned(self):
        """Q3 asked when session signals unexpected events."""
        rq = pytest.importorskip("review_questions")
        surprise_text = "something unexpected happened with the bridge — debugging now"
        questions = rq.generate_review_questions(session_text=surprise_text, session_files=[])
        assert any("unexpected" in q.lower() or "surprise" in q.lower() for q in questions)

    def test_q5_triggered_when_clarity_needed(self):
        """Q5 asked for clarity/sanity check when session is very short or low-clarity."""
        rq = pytest.importorskip("review_questions")
        # Short session (< 100 words) should trigger Q5
        short = "a b c d e f g h i j k l m n o p q r s t u v w x y z " * 3  # ~78 words
        questions = rq.generate_review_questions(session_text=short, session_files=[])
        assert any("make sense" in q.lower() or "wasn't in the room" in q.lower() for q in questions)


class TestReviewDialogFormat:
    """Review dialog output format (AC1)."""

    def test_questions_returned_as_list(self):
        """Questions are returned as a list of strings, one per question."""
        rq = pytest.importorskip("review_questions")
        result = rq.generate_review_questions(session_text="", session_files=[])
        assert isinstance(result, list)
        assert all(isinstance(q, str) for q in result)

    def test_no_duplicate_questions(self):
        """The same question text should not appear twice."""
        rq = pytest.importorskip("review_questions")
        questions = rq.generate_review_questions(session_text="test", session_files=[])
        assert len(questions) == len(set(questions)), "Duplicate questions found"
