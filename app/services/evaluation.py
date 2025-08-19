"""Evaluation service using RAGAS metrics."""

import json
import time
import uuid
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from app.core.config import app_config
from app.core.logging import ServiceLogger
from app.services.llm import OllamaService
from app.services.search import HybridSearchService


class RAGASEvaluationService:
    """Service for evaluating RAG system using RAGAS metrics."""

    def __init__(self):
        self.logger = ServiceLogger("ragas_evaluation")

        eval_config = app_config.evaluation.get("ragas", {})
        self.metrics = self._load_metrics(
            eval_config.get(
                "metrics",
                ["faithfulness", "answer_relevancy", "context_precision", "context_recall"],
            )
        )
        self.batch_size = eval_config.get("batch_size", 16)

        # Services for generating answers
        self.search_service = HybridSearchService()
        self.llm_service = OllamaService()

    def _load_metrics(self, metric_names: list[str]) -> list:
        """Load RAGAS metrics based on configuration."""
        available_metrics = {
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_precision": context_precision,
            "context_recall": context_recall,
        }

        metrics = []
        for metric_name in metric_names:
            if metric_name in available_metrics:
                metrics.append(available_metrics[metric_name])
            else:
                self.logger.warning(f"Unknown metric: {metric_name}")

        return metrics

    async def generate_answer_for_evaluation(self, question: str) -> dict[str, Any]:
        """Generate answer using current RAG pipeline for evaluation."""
        try:
            # Get search results
            search_results, _ = await self.search_service.search(question)

            # Generate answer
            llm_response = await self.llm_service.generate_response(question, search_results)

            # Format contexts for RAGAS
            contexts = []
            for result in search_results:
                contexts.append(result["text"])

            return {
                "answer": llm_response["answer"],
                "contexts": contexts,
                "search_results": search_results,
            }

        except Exception as e:
            self.logger.error("Failed to generate answer for evaluation", error=str(e))
            raise

    def prepare_evaluation_dataset(
        self, test_cases: list[dict[str, Any]], generated_answers: list[dict[str, Any]]
    ) -> Dataset:
        """Prepare dataset for RAGAS evaluation."""

        # Prepare data for RAGAS format
        data = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

        for i, test_case in enumerate(test_cases):
            generated = generated_answers[i] if i < len(generated_answers) else {}

            data["question"].append(test_case["question"])
            data["answer"].append(generated.get("answer", ""))
            data["contexts"].append(generated.get("contexts", []))
            data["ground_truth"].append(test_case["ground_truth_answer"])

        # Create dataset
        dataset = Dataset.from_dict(data)
        return dataset

    async def evaluate_test_cases(self, test_cases: list[dict[str, Any]]) -> dict[str, Any]:
        """Evaluate a list of test cases using RAGAS metrics."""
        start_time = time.time()

        try:
            self.logger.info(f"Starting RAGAS evaluation for {len(test_cases)} test cases")

            # Generate answers for all test cases
            generated_answers = []
            failed_cases = []

            for i, test_case in enumerate(test_cases):
                try:
                    generated = await self.generate_answer_for_evaluation(test_case["question"])
                    generated_answers.append(generated)
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate answer for case {i}",
                        error=str(e),
                        question=test_case["question"],
                    )
                    failed_cases.append(
                        {"case_id": i, "question": test_case["question"], "error": str(e)}
                    )
                    generated_answers.append({"answer": "", "contexts": []})

            # Prepare dataset for RAGAS
            dataset = self.prepare_evaluation_dataset(test_cases, generated_answers)

            # Run RAGAS evaluation
            eval_start = time.time()
            try:
                result = evaluate(dataset, metrics=self.metrics)
                eval_time = (time.time() - eval_start) * 1000

                # Convert to regular dict for JSON serialization
                scores = {}
                for metric_name, score in result.items():
                    if hasattr(score, "item"):  # numpy scalar
                        scores[metric_name] = float(score.item())
                    else:
                        scores[metric_name] = float(score)

            except Exception as e:
                self.logger.error("RAGAS evaluation failed", error=str(e))
                # Return default scores if evaluation fails
                scores = {
                    "faithfulness": 0.0,
                    "answer_relevancy": 0.0,
                    "context_precision": 0.0,
                    "context_recall": 0.0,
                }
                eval_time = 0

            # Calculate individual case results
            case_results = []
            for i, test_case in enumerate(test_cases):
                generated = generated_answers[i] if i < len(generated_answers) else {}

                case_result = {
                    "case_id": i,
                    "question": test_case["question"],
                    "ground_truth_answer": test_case["ground_truth_answer"],
                    "generated_answer": generated.get("answer", ""),
                    "contexts_used": generated.get("contexts", []),
                    "search_results_count": len(generated.get("search_results", [])),
                    "error": None,
                }

                # Add error info if case failed
                for failed_case in failed_cases:
                    if failed_case["case_id"] == i:
                        case_result["error"] = failed_case["error"]
                        break

                case_results.append(case_result)

            total_time = (time.time() - start_time) * 1000

            result_summary = {
                "evaluation_id": str(uuid.uuid4()),
                "total_cases": len(test_cases),
                "successful_cases": len(test_cases) - len(failed_cases),
                "failed_cases": len(failed_cases),
                "overall_scores": scores,
                "case_results": case_results,
                "timing": {
                    "total_time_ms": total_time,
                    "evaluation_time_ms": eval_time,
                    "avg_case_time_ms": total_time / len(test_cases) if test_cases else 0,
                },
                "failed_case_details": failed_cases,
            }

            self.logger.info(
                "RAGAS evaluation completed",
                evaluation_id=result_summary["evaluation_id"],
                total_cases=len(test_cases),
                successful_cases=result_summary["successful_cases"],
                failed_cases=len(failed_cases),
                faithfulness=scores.get("faithfulness", 0),
                answer_relevancy=scores.get("answer_relevancy", 0),
                total_time_ms=total_time,
            )

            return result_summary

        except Exception as e:
            total_time = (time.time() - start_time) * 1000
            self.logger.error(
                "RAGAS evaluation failed completely",
                error=str(e),
                total_cases=len(test_cases) if test_cases else 0,
                total_time_ms=total_time,
            )
            raise

    def load_test_cases_from_jsonl(self, file_path: str) -> list[dict[str, Any]]:
        """Load test cases from JSONL file."""
        try:
            test_cases = []
            with open(file_path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        case = json.loads(line)

                        # Validate required fields
                        required_fields = ["question", "ground_truth_answer"]
                        missing_fields = [field for field in required_fields if field not in case]

                        if missing_fields:
                            self.logger.warning(
                                f"Line {line_num}: Missing required fields: {missing_fields}"
                            )
                            continue

                        test_cases.append(case)

                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Line {line_num}: Invalid JSON - {str(e)}")
                        continue

            self.logger.info(f"Loaded {len(test_cases)} test cases from {file_path}")
            return test_cases

        except FileNotFoundError:
            raise ValueError(f"Test file not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Failed to load test cases: {str(e)}")

    async def run_evaluation_from_file(self, file_path: str) -> dict[str, Any]:
        """Run evaluation using test cases from a JSONL file."""
        test_cases = self.load_test_cases_from_jsonl(file_path)
        return await self.evaluate_test_cases(test_cases)
