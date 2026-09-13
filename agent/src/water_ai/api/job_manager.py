"""Job management and task queue for API."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class JobStatus(str, Enum):
    """Job execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobManager:
    """In-memory job manager for strategy requests.
    
    Note: For production, consider using Celery + Redis
    This implementation is suitable for single-server deployments.
    """

    def __init__(self, results_dir: str = "outputs/api_jobs") -> None:
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory job store
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()

    def create_job(
        self,
        scenario: str,
        state: dict[str, Any],
        episodes: int = 1,
        backend: str = "api",
        request_id: str | None = None,
    ) -> str:
        """Create a new job.
        
        Args:
            scenario: Scenario type
            state: Water quality state
            episodes: Number of episodes
            backend: DeepSeek backend type
            request_id: Optional external request ID
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        
        with self.lock:
            self.jobs[job_id] = {
                "job_id": job_id,
                "request_id": request_id,
                "scenario": scenario,
                "state": state,
                "episodes": episodes,
                "backend": backend,
                "status": JobStatus.QUEUED,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
            }
        
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get job details.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job dict or None if not found
        """
        with self.lock:
            return self.jobs.get(job_id)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """Update job status.
        
        Args:
            job_id: Job identifier
            status: New status
            result: Result data (if completed)
            error: Error message (if failed)
            
        Returns:
            True if updated, False if job not found
        """
        with self.lock:
            if job_id not in self.jobs:
                return False
            
            job = self.jobs[job_id]
            job["status"] = status
            
            if status == JobStatus.RUNNING and job["started_at"] is None:
                job["started_at"] = datetime.now(timezone.utc).isoformat()
            
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job["completed_at"] = datetime.now(timezone.utc).isoformat()
            
            if result is not None:
                job["result"] = result
            
            if error is not None:
                job["error"] = error
            
            # Save to disk
            self._save_job(job_id, job)
            return True

    def list_jobs(
        self,
        status: JobStatus | None = None,
        scenario: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filtering.
        
        Args:
            status: Filter by status
            scenario: Filter by scenario
            limit: Maximum number of jobs to return
            
        Returns:
            List of job dicts
        """
        with self.lock:
            jobs = list(self.jobs.values())
        
        # Filter
        if status:
            jobs = [j for j in jobs if j["status"] == status]
        if scenario:
            jobs = [j for j in jobs if j["scenario"] == scenario]
        
        # Sort by creation time (newest first)
        jobs.sort(key=lambda x: x["created_at"], reverse=True)
        
        return jobs[:limit]

    def _save_job(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Save job data to disk.
        
        Args:
            job_id: Job identifier
            job_data: Job data dict
        """
        try:
            job_file = self.results_dir / f"{job_id}.json"
            with open(job_file, "w", encoding="utf-8") as f:
                json.dump(job_data, f, indent=2, ensure_ascii=False, default=str)
        except (OSError, TypeError) as e:
            print(f"Warning: Failed to save job {job_id}: {e}")

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        """Get the final result of a completed job."""
        job = self.get_job(job_id)
        if not job:
            return None
        if job["status"] != JobStatus.COMPLETED:
            return None
        return job.get("result")

    def set_stage(self, job_id: str, stage: str) -> None:
        """Set the current processing stage for a job."""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["current_stage"] = stage

    def get_stage(self, job_id: str) -> str | None:
        """Get the current processing stage for a job."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                return job.get("current_stage")
            return None

    def cleanup_old_jobs(self, days: int = 7) -> int:
        """Remove jobs older than specified days.
        
        Args:
            days: Age threshold in days
            
        Returns:
            Number of jobs removed
        """
        from datetime import timedelta
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        
        with self.lock:
            to_remove = []
            for job_id, job in self.jobs.items():
                created = datetime.fromisoformat(job["created_at"])
                if created < cutoff_time:
                    to_remove.append(job_id)
            
            for job_id in to_remove:
                del self.jobs[job_id]
            
            return len(to_remove)
