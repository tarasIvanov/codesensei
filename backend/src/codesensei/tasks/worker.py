"""arq WorkerSettings entrypoint."""

from __future__ import annotations

from arq.connections import RedisSettings

from codesensei.config import get_settings
from codesensei.indexing.tasks import index_repo_job
from codesensei.tasks.ping import ping_job

HEALTH_CHECK_KEY = "arq:health-check:default"


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """Loaded by `arq codesensei.tasks.worker.WorkerSettings`."""

    functions = [ping_job, index_repo_job]
    redis_settings = _redis_settings()
    keep_result_seconds = get_settings().job_result_ttl_s
    health_check_key = HEALTH_CHECK_KEY
