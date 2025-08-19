"""Evaluation API endpoints for running RAGAS assessments."""

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger, get_trace_id
from app.models.base import EvalRunRequest, EvalRunResponse, EvaluationResult
from app.services.evaluation import RAGASEvaluationService

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


class EvaluationService:
    """Service for managing evaluation runs and results."""

    def __init__(self):
        self.ragas_service = RAGASEvaluationService()
        self.logger = get_logger("evaluation_service")

    async def save_evaluation_run(self, run_data: dict, results: dict, db) -> str:
        """Save evaluation run to database."""
        try:
            run_id = str(uuid.uuid4())

            # Save evaluation run
            db.execute(
                text(
                    """
                    INSERT INTO evaluation_runs
                    (id, run_name, eval_type, llm_model, reranker_model, total_cases,
                     completed_cases, avg_faithfulness, avg_answer_relevancy,
                     avg_context_precision, avg_context_recall, status, user_id,
                     started_at, completed_at, config)
                    VALUES
                    (:id, :run_name, :eval_type, :llm_model, :reranker_model, :total_cases,
                     :completed_cases, :avg_faithfulness, :avg_answer_relevancy,
                     :avg_context_precision, :avg_context_recall, :status, :user_id,
                     NOW(), NOW(), :config)
                """
                ),
                {
                    "id": run_id,
                    "run_name": run_data.get("run_name", f"Evaluation {run_id[:8]}"),
                    "eval_type": run_data.get("eval_type", "ragas"),
                    "llm_model": run_data.get("llm_model"),
                    "reranker_model": run_data.get("reranker_model"),
                    "total_cases": results.get("total_cases", 0),
                    "completed_cases": results.get("successful_cases", 0),
                    "avg_faithfulness": results.get("overall_scores", {}).get("faithfulness"),
                    "avg_answer_relevancy": results.get("overall_scores", {}).get(
                        "answer_relevancy"
                    ),
                    "avg_context_precision": results.get("overall_scores", {}).get(
                        "context_precision"
                    ),
                    "avg_context_recall": results.get("overall_scores", {}).get("context_recall"),
                    "status": "completed"
                    if results.get("failed_cases", 0) == 0
                    else "partially_failed",
                    "user_id": run_data.get("user_id"),
                    "config": json.dumps(run_data),
                },
            )

            # Save individual case results
            for case_result in results.get("case_results", []):
                case_id = str(uuid.uuid4())

                db.execute(
                    text(
                        """
                        INSERT INTO evaluation_results
                        (id, run_id, case_id, question, ground_truth_answer,
                         llm_answer, citations_used, faithfulness, answer_relevancy,
                         context_precision, context_recall, flags, errors)
                        VALUES
                        (:id, :run_id, :case_id, :question, :ground_truth_answer,
                         :llm_answer, :citations_used, :faithfulness, :answer_relevancy,
                         :context_precision, :context_recall, :flags, :errors)
                    """
                    ),
                    {
                        "id": case_id,
                        "run_id": run_id,
                        "case_id": case_result.get("case_id", 0),
                        "question": case_result.get("question"),
                        "ground_truth_answer": case_result.get("ground_truth_answer"),
                        "llm_answer": case_result.get("generated_answer"),
                        "citations_used": json.dumps(case_result.get("contexts_used", [])),
                        "faithfulness": None,  # Individual metrics not available from RAGAS
                        "answer_relevancy": None,
                        "context_precision": None,
                        "context_recall": None,
                        "flags": json.dumps([]),
                        "errors": json.dumps(
                            {"error": case_result.get("error")} if case_result.get("error") else {}
                        ),
                    },
                )

            db.commit()

            self.logger.info(
                "Evaluation run saved",
                run_id=run_id,
                total_cases=results.get("total_cases", 0),
                successful_cases=results.get("successful_cases", 0),
            )

            return run_id

        except Exception as e:
            db.rollback()
            self.logger.error("Failed to save evaluation run", error=str(e))
            raise

    async def get_evaluation_history(self, db, limit: int = 10) -> list[dict]:
        """Get recent evaluation runs."""
        try:
            runs = db.execute(
                text(
                    """
                    SELECT id, run_name, eval_type, total_cases, completed_cases,
                           avg_faithfulness, avg_answer_relevancy, status, started_at
                    FROM evaluation_runs
                    ORDER BY started_at DESC
                    LIMIT :limit
                """
                ),
                {"limit": limit},
            ).fetchall()

            return [
                {
                    "run_id": row[0],
                    "run_name": row[1],
                    "eval_type": row[2],
                    "total_cases": row[3],
                    "completed_cases": row[4],
                    "avg_faithfulness": row[5],
                    "avg_answer_relevancy": row[6],
                    "status": row[7],
                    "started_at": row[8].isoformat() if row[8] else None,
                }
                for row in runs
            ]

        except Exception as e:
            self.logger.error("Failed to get evaluation history", error=str(e))
            raise


evaluation_service = EvaluationService()


@router.post("/eval/run", response_model=EvalRunResponse)
async def run_evaluation(request: EvalRunRequest, db=Depends(get_db)):
    """
    Run evaluation on the RAG system using RAGAS metrics.

    - **cases**: List of test cases (for small batches)
    - **file_path**: Path to JSONL file with test cases
    - **llm_model**: LLM model to use (optional, uses default)
    - **reranker**: Reranker model to use (optional, uses default)
    - **eval_type**: Type of evaluation (default: "ragas")
    """
    start_time = time.time()
    trace_id = get_trace_id()

    try:
        logger.info("Starting evaluation run", eval_type=request.eval_type, trace_id=trace_id)

        # Validate input
        if not request.cases and not request.file_path:
            raise HTTPException(
                status_code=400, detail="Either 'cases' or 'file_path' must be provided"
            )

        if request.cases and request.file_path:
            raise HTTPException(
                status_code=400, detail="Provide either 'cases' or 'file_path', not both"
            )

        # Load test cases
        if request.file_path:
            try:
                test_cases = evaluation_service.ragas_service.load_test_cases_from_jsonl(
                    request.file_path
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Failed to load test cases from file: {str(e)}"
                )
        else:
            test_cases = [case.dict() for case in request.cases]

        # Validate test cases
        if not test_cases:
            raise HTTPException(status_code=400, detail="No valid test cases found")

        if len(test_cases) > 1000:
            raise HTTPException(status_code=400, detail="Too many test cases (maximum 1000)")

        # Run evaluation
        try:
            results = await evaluation_service.ragas_service.evaluate_test_cases(test_cases)
        except Exception as e:
            logger.error("Evaluation failed", error=str(e), trace_id=trace_id)
            raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

        # Save results to database
        run_data = {
            "eval_type": request.eval_type,
            "llm_model": request.llm_model,
            "reranker_model": request.reranker,
            "user_id": None,  # Could be extracted from auth if implemented
            "run_name": f"Evaluation {results['evaluation_id'][:8]}",
        }

        try:
            run_id = await evaluation_service.save_evaluation_run(run_data, results, db)
        except Exception as e:
            logger.warning("Failed to save evaluation to database", error=str(e))
            run_id = results["evaluation_id"]

        # Format response
        evaluation_results = []
        for case_result in results.get("case_results", []):
            eval_result = EvaluationResult(
                case_id=case_result.get("case_id", 0),
                question=case_result.get("question", ""),
                llm_answer=case_result.get("generated_answer", ""),
                citations_used=case_result.get("contexts_used", []),
                flags=["error"] if case_result.get("error") else [],
                errors={"error": case_result.get("error")} if case_result.get("error") else None,
            )
            evaluation_results.append(eval_result)

        total_duration = (time.time() - start_time) * 1000

        logger.info(
            "Evaluation completed",
            run_id=run_id,
            total_cases=results.get("total_cases", 0),
            successful_cases=results.get("successful_cases", 0),
            duration_ms=total_duration,
            trace_id=trace_id,
        )

        return EvalRunResponse(
            run_id=run_id,
            total_cases=results.get("total_cases", 0),
            completed_cases=results.get("successful_cases", 0),
            avg_faithfulness=results.get("overall_scores", {}).get("faithfulness"),
            avg_answer_relevancy=results.get("overall_scores", {}).get("answer_relevancy"),
            avg_context_precision=results.get("overall_scores", {}).get("context_precision"),
            avg_context_recall=results.get("overall_scores", {}).get("context_recall"),
            results=evaluation_results,
            message=f"Evaluation completed in {total_duration:.1f}ms",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Evaluation request failed", error=str(e), trace_id=trace_id)
        raise HTTPException(status_code=500, detail="Internal evaluation error")


@router.get("/eval/history")
async def get_evaluation_history(limit: int = 10, db=Depends(get_db)):
    """Get recent evaluation runs."""
    try:
        if limit > 100:
            limit = 100

        history = await evaluation_service.get_evaluation_history(db, limit)

        return {"evaluation_runs": history, "total_returned": len(history)}

    except Exception as e:
        logger.error("Failed to get evaluation history", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve evaluation history")


@router.get("/eval/status/{run_id}")
async def get_evaluation_status(run_id: str, db=Depends(get_db)):
    """Get detailed status of a specific evaluation run."""
    try:
        # Get run details
        run_details = db.execute(
            text(
                """
                SELECT run_name, eval_type, total_cases, completed_cases,
                       avg_faithfulness, avg_answer_relevancy, avg_context_precision,
                       avg_context_recall, status, started_at, completed_at, config
                FROM evaluation_runs
                WHERE id = :run_id
            """
            ),
            {"run_id": run_id},
        ).fetchone()

        if not run_details:
            raise HTTPException(status_code=404, detail="Evaluation run not found")

        # Get case results
        case_results = db.execute(
            text(
                """
                SELECT case_id, question, ground_truth_answer, llm_answer,
                       citations_used, flags, errors
                FROM evaluation_results
                WHERE run_id = :run_id
                ORDER BY case_id
            """
            ),
            {"run_id": run_id},
        ).fetchall()

        return {
            "run_id": run_id,
            "run_name": run_details[0],
            "eval_type": run_details[1],
            "total_cases": run_details[2],
            "completed_cases": run_details[3],
            "scores": {
                "faithfulness": run_details[4],
                "answer_relevancy": run_details[5],
                "context_precision": run_details[6],
                "context_recall": run_details[7],
            },
            "status": run_details[8],
            "started_at": run_details[9].isoformat() if run_details[9] else None,
            "completed_at": run_details[10].isoformat() if run_details[10] else None,
            "config": json.loads(run_details[11]) if run_details[11] else {},
            "case_results": [
                {
                    "case_id": row[0],
                    "question": row[1],
                    "ground_truth_answer": row[2],
                    "llm_answer": row[3],
                    "citations_used": json.loads(row[4]) if row[4] else [],
                    "flags": json.loads(row[5]) if row[5] else [],
                    "errors": json.loads(row[6]) if row[6] else {},
                }
                for row in case_results
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get evaluation status", error=str(e), run_id=run_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve evaluation status")
