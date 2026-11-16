"""GitHub adapter: start the repository's "Import region" workflow (ADR 033, step 3).

The only thing it does is ``POST /repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches``
with the region, whether to import the gazetteer first, and the job id. It has what architecture
section 6 asks of every provider: an identifying User-Agent, a timeout, a daily call budget in
``app.provider_usage`` reserved atomically before the call, and a fallback (every failure becomes a
state in the result, never an exception). There is nothing to cache.

Terms read on 2026-11-17 (https://docs.github.com/en/site-policy/github-terms/github-terms-of-service,
Section H): "Abuse or excessively frequent requests to GitHub via the API may result in the
temporary or permanent suspension of your Account's access to the API." and "You may not share API
tokens to exceed GitHub's rate limitations." Rate limit read the same day
(https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api): "All of these
requests count towards your personal rate limit of 5,000 requests per hour." The endpoint is
documented at https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
(body: ``ref`` required, ``inputs`` at most 25 properties; the success answer is 200 with the run's
identifiers; classic tokens need the ``repo`` scope, the page does not name a fine-grained
permission, so the token needs Actions: write, which the owner confirms when creating it).
"""

import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import structlog
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from detour_api.settings import Settings

log = structlog.get_logger("detour.github")

PROVIDER = "github"
API_VERSION = "2022-11-28"
State = Literal["started", "disabled", "unavailable", "budget_exhausted", "refused"]


@dataclass(frozen=True)
class DispatchOutcome:
    state: State
    run_url: str | None = None


class GitHubDispatcher:
    def __init__(
        self,
        settings: Settings,
        engine: Engine | None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self._settings.github_token is not None and self._engine is not None

    def dispatch_import(
        self, region_id: str, job_id: uuid.UUID, gazetteer: bool
    ) -> DispatchOutcome:
        if not self.enabled:
            return DispatchOutcome("disabled")
        if not self._reserve_call():
            log.warning("github_budget_exhausted", budget=self._settings.github_daily_budget)
            return DispatchOutcome("budget_exhausted")
        s = self._settings
        assert s.github_token is not None  # noqa: S101
        url = (
            f"{s.github_api_url.rstrip('/')}/repos/{s.github_repository}/actions/workflows/"
            f"{s.github_workflow}/dispatches"
        )
        body: dict[str, Any] = {
            "ref": s.github_ref,
            "inputs": {"region": region_id, "gazetteer": gazetteer, "job_id": str(job_id)},
        }
        headers = {
            "Authorization": f"Bearer {s.github_token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": s.github_user_agent,
        }
        try:
            with httpx.Client(transport=self._transport, timeout=s.github_timeout_seconds) as c:
                response = c.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("github_unavailable", error=type(exc).__name__)
            return DispatchOutcome("unavailable")
        if response.status_code in (200, 204):
            run_url = None
            try:
                found = response.json().get("html_url") if response.content else None
                if isinstance(found, str) and found.startswith("https://"):
                    run_url = found
            except ValueError:
                pass
            return DispatchOutcome("started", run_url)
        # 401, 403, 404, 422: the token, its permission or the workflow is wrong. Never log the body
        # (it may echo request data); the status is enough to act on.
        log.warning("github_refused", status=response.status_code)
        return DispatchOutcome("refused" if response.status_code < 500 else "unavailable")

    def _reserve_call(self) -> bool:
        assert self._engine is not None  # noqa: S101
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    text(
                        "INSERT INTO app.provider_usage (provider, usage_date, calls)"
                        " VALUES (:p, (now() AT TIME ZONE 'UTC')::date, 1)"
                        " ON CONFLICT (provider, usage_date) DO UPDATE SET"
                        " calls = provider_usage.calls + 1"
                        " WHERE provider_usage.calls < :budget RETURNING calls"
                    ),
                    {"p": PROVIDER, "budget": self._settings.github_daily_budget},
                ).first()
        except SQLAlchemyError as exc:
            log.warning("github_budget_unavailable", error=type(exc).__name__)
            return False
        return row is not None
