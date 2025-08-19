"""Feedback collection API endpoints."""

import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import app_config, settings
from app.core.logging import get_logger, get_trace_id
from app.models.base import FeedbackRequest, FeedbackResponse

router = APIRouter()
logger = get_logger(__name__)

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class FeedbackService:
    """Service for handling user feedback collection."""

    def __init__(self):
        self.logger = get_logger("feedback_service")
        feedback_config = app_config.feedback

        self.valid_reasons = feedback_config.get(
            "reasons",
            [
                "галлюцинация",
                "не по теме",
                "неполный ответ",
                "устаревшая информация",
                "опасный/вредный контент",
            ],
        )

        # Rate limiting config
        rate_config = feedback_config.get("rate_limit", {})
        self.max_requests = rate_config.get("max_requests", 5)
        self.window_minutes = rate_config.get("window_minutes", 1)

        # In-memory rate limiting (in production use Redis)
        self.rate_limit_store = {}

    def check_rate_limit(self, client_ip: str) -> bool:
        """Check if client IP has exceeded rate limit."""
        current_time = time.time()
        window_seconds = self.window_minutes * 60

        if client_ip not in self.rate_limit_store:
            self.rate_limit_store[client_ip] = []

        # Clean old requests outside window
        requests = self.rate_limit_store[client_ip]
        self.rate_limit_store[client_ip] = [
            req_time for req_time in requests if current_time - req_time < window_seconds
        ]

        # Check if limit exceeded
        if len(self.rate_limit_store[client_ip]) >= self.max_requests:
            return False

        # Add current request
        self.rate_limit_store[client_ip].append(current_time)
        return True

    async def save_feedback(
        self, feedback_data: FeedbackRequest, client_ip: str, user_agent: str, db
    ) -> str:
        """Save feedback to database."""
        try:
            feedback_id = str(uuid.uuid4())
            trace_id = get_trace_id()

            # Convert citations to JSON
            citations_json = feedback_data.citations_used if feedback_data.citations_used else []

            db.execute(
                text(
                    """
                    INSERT INTO feedback
                    (id, question, llm_answer, citations_used, rating, reason, comment,
                     trace_id, user_id, session_id, request_id, ip_address, user_agent,
                     created_at)
                    VALUES
                    (:id, :question, :llm_answer, :citations_used, :rating, :reason, :comment,
                     :trace_id, :user_id, :session_id, :request_id, :ip_address, :user_agent,
                     NOW())
                """
                ),
                {
                    "id": feedback_id,
                    "question": feedback_data.question,
                    "llm_answer": feedback_data.llm_answer,
                    "citations_used": json.dumps(citations_json),
                    "rating": feedback_data.rating,
                    "reason": feedback_data.reason,
                    "comment": feedback_data.comment,
                    "trace_id": trace_id,
                    "user_id": feedback_data.user_id,
                    "session_id": feedback_data.session_id,
                    "request_id": feedback_data.request_id,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                },
            )
            db.commit()

            self.logger.info(
                "Feedback saved successfully",
                feedback_id=feedback_id,
                rating=feedback_data.rating,
                reason=feedback_data.reason,
                has_comment=bool(feedback_data.comment),
                trace_id=trace_id,
            )

            return feedback_id

        except Exception as e:
            db.rollback()
            self.logger.error("Failed to save feedback", error=str(e), trace_id=trace_id)
            raise

    async def get_feedback_stats(self, db) -> dict:
        """Get feedback statistics."""
        try:
            # Overall stats
            overall_stats = db.execute(
                text(
                    """
                    SELECT
                        COUNT(*) as total_feedback,
                        COUNT(CASE WHEN rating = 'up' THEN 1 END) as positive_count,
                        COUNT(CASE WHEN rating = 'down' THEN 1 END) as negative_count,
                        ROUND(
                            COUNT(CASE WHEN rating = 'up' THEN 1 END)::float /
                            NULLIF(COUNT(*), 0) * 100, 2
                        ) as positive_percentage
                    FROM feedback
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                """
                )
            ).fetchone()

            # Reason breakdown for negative feedback
            reason_stats = db.execute(
                text(
                    """
                    SELECT reason, COUNT(*) as count
                    FROM feedback
                    WHERE rating = 'down' AND reason IS NOT NULL
                      AND created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY reason
                    ORDER BY count DESC
                    LIMIT 10
                """
                )
            ).fetchall()

            # Recent feedback
            recent_feedback = db.execute(
                text(
                    """
                    SELECT rating, reason, comment, created_at
                    FROM feedback
                    ORDER BY created_at DESC
                    LIMIT 10
                """
                )
            ).fetchall()

            return {
                "statistics": {
                    "total_feedback": overall_stats[0] if overall_stats else 0,
                    "positive_count": overall_stats[1] if overall_stats else 0,
                    "negative_count": overall_stats[2] if overall_stats else 0,
                    "positive_percentage": overall_stats[3] if overall_stats else 0,
                },
                "negative_reasons": [{"reason": row[0], "count": row[1]} for row in reason_stats],
                "recent_feedback": [
                    {
                        "rating": row[0],
                        "reason": row[1],
                        "comment": row[2][:100] + "..." if row[2] and len(row[2]) > 100 else row[2],
                        "created_at": row[3].isoformat() if row[3] else None,
                    }
                    for row in recent_feedback
                ],
            }

        except Exception as e:
            self.logger.error("Failed to get feedback stats", error=str(e))
            raise


feedback_service = FeedbackService()


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, http_request: Request, db=Depends(get_db)):
    """
    Submit feedback on a generated answer.

    - **question**: Original question asked
    - **llm_answer**: The answer that was generated
    - **citations_used**: List of chunk IDs that were cited
    - **rating**: "up" or "down"
    - **reason**: Optional reason for negative feedback
    - **comment**: Optional additional comment
    - **session_id**: Optional session identifier
    - **request_id**: Optional request identifier from /ask call
    """
    start_time = time.time()

    try:
        # Get client information
        client_ip = http_request.client.host if http_request.client else "unknown"
        user_agent = http_request.headers.get("user-agent", "unknown")

        logger.info(
            "Processing feedback submission",
            rating=request.rating,
            reason=request.reason,
            has_comment=bool(request.comment),
            client_ip=client_ip,
        )

        # Validate rating
        if request.rating not in ["up", "down"]:
            raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'")

        # Validate reason for negative feedback
        if request.rating == "down" and request.reason:
            if request.reason not in feedback_service.valid_reasons:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid reason. Must be one of: {feedback_service.valid_reasons}",
                )

        # Check rate limiting
        if not feedback_service.check_rate_limit(client_ip):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {feedback_service.max_requests} requests per {feedback_service.window_minutes} minute(s)",
            )

        # Validate input lengths
        if len(request.question) > 1000:
            raise HTTPException(
                status_code=400, detail="Question is too long (maximum 1000 characters)"
            )

        if len(request.llm_answer) > 5000:
            raise HTTPException(
                status_code=400, detail="Answer is too long (maximum 5000 characters)"
            )

        if request.comment and len(request.comment) > 1000:
            raise HTTPException(
                status_code=400, detail="Comment is too long (maximum 1000 characters)"
            )

        # Save feedback
        feedback_id = await feedback_service.save_feedback(request, client_ip, user_agent, db)

        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Feedback submitted successfully", feedback_id=feedback_id, duration_ms=duration_ms
        )

        return FeedbackResponse(
            feedback_id=feedback_id,
            saved_at=datetime.utcnow(),
            message="Feedback submitted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Feedback submission failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.get("/feedback/stats")
async def get_feedback_statistics(db=Depends(get_db)):
    """Get feedback statistics and analytics."""
    try:
        stats = await feedback_service.get_feedback_stats(db)
        return stats

    except Exception as e:
        logger.error("Failed to get feedback statistics", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve feedback statistics")


@router.get("/feedback/reasons")
async def get_feedback_reasons():
    """Get list of valid feedback reasons."""
    return {
        "reasons": feedback_service.valid_reasons,
        "description": "Valid reasons for negative feedback",
    }


# Import json for citations serialization
import json
