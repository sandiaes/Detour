"""Starting a region import from the app (ADR 033, step 3): the catalog, the owner gate, the
GitHub dispatch through a recorded transport, one import at a time, stalled jobs, and the job
command the workflow runs. GitHub itself is never called."""

import json
import uuid
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from detour_api.adapters.github import GitHubDispatcher
from detour_api.importer import cli
from tests.conftest import ApiEnv
from tests.test_api_planning import sql

pytestmark = pytest.mark.db

LONDON = "greater-london"


class Github:
    """What the fake GitHub saw and answers."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.fail = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectTimeout("simulated", request=request)
        body = {"workflow_run_id": 1, "html_url": "https://github.com/o/r/actions/runs/1"}
        return httpx.Response(self.status, json=body if self.status == 200 else {})


def _setup(env: ApiEnv, *, owner: bool = True, token: bool = True) -> Github:
    app = env.client.app  # type: ignore[attr-defined]
    github = Github()
    settings = app.state.settings
    settings.github_token = SecretStr("ghp_test_token") if token else None
    settings.owner_installation_ids = str(env.installation_id) if owner else ""
    app.state.github = GitHubDispatcher(settings, app.state.engine, httpx.MockTransport(github))
    return github


def _post(env: ApiEnv, region: str = LONDON, body: Any = None) -> httpx.Response:
    return env.client.post(f"/v1/regions/{region}/import", json=body, headers=env.headers)


def test_the_catalog_lists_the_importable_regions_and_who_may_manage(api_env: ApiEnv) -> None:
    _setup(api_env, owner=False)
    c, h = api_env.client, api_env.headers
    cat = c.get("/v1/regions/catalog", headers=h).json()
    assert cat["can_manage"] is False and cat["import_enabled"] is True
    by_id = {r["id"]: r for r in cat["regions"]}
    assert by_id[LONDON]["state"] == "not_imported" and by_id[LONDON]["download_mb"] == 124
    assert by_id[LONDON]["job"] is None and by_id[LONDON]["country_codes"] == ["GB"]
    assert cat["geo_limit_bytes"] == 250_000_000 and cat["geo_bytes"] > 0
    _setup(api_env)
    assert c.get("/v1/regions/catalog", headers=h).json()["can_manage"] is True


def test_importing_asks_github_to_run_the_workflow_and_records_a_job(api_env: ApiEnv) -> None:
    github = _setup(api_env)
    r = _post(api_env, body={"gazetteer": False})
    assert r.status_code == 202, r.text
    job = r.json()
    assert (
        job["status"] == "requested" and job["run_url"] == "https://github.com/o/r/actions/runs/1"
    )
    (sent,) = github.requests
    assert sent.url.path.endswith("/actions/workflows/import-region.yml/dispatches")
    assert sent.headers["authorization"] == "Bearer ghp_test_token"
    assert sent.headers["accept"] == "application/vnd.github+json"
    assert sent.headers["user-agent"].startswith("Detour-backend")
    body = json.loads(sent.content)
    assert body["ref"] == "main"
    assert body["inputs"] == {"region": LONDON, "gazetteer": False, "job_id": job["id"]}
    # The catalog shows the job on the region.
    cat = api_env.client.get("/v1/regions/catalog", headers=api_env.headers).json()
    assert next(x for x in cat["regions"] if x["id"] == LONDON)["job"]["id"] == job["id"]


def test_only_the_owner_may_import_and_only_catalog_regions(api_env: ApiEnv) -> None:
    github = _setup(api_env, owner=False)
    refused = _post(api_env)
    assert refused.status_code == 403 and refused.json()["code"] == "not_owner"
    _setup(api_env)
    assert _post(api_env, "narnia").status_code == 404
    assert github.requests == []


def test_without_a_token_the_server_cannot_start_imports(api_env: ApiEnv) -> None:
    _setup(api_env, token=False)
    r = _post(api_env)
    assert r.status_code == 503 and r.json()["code"] == "import_unavailable"
    cat = api_env.client.get("/v1/regions/catalog", headers=api_env.headers).json()
    assert cat["import_enabled"] is False
    assert sql(api_env, "SELECT count(*) FROM geo.import_job") == [(0,)]


@pytest.mark.parametrize(
    ("status", "message"), [(401, "refused"), (404, "refused"), (422, "refused"), (503, "reached")]
)
def test_a_github_refusal_is_a_failed_job_and_a_502(
    api_env: ApiEnv, status: int, message: str
) -> None:
    github = _setup(api_env)
    github.status = status
    r = _post(api_env)
    assert r.status_code == 502 and r.json()["code"] == "import_not_started"
    ((state, text),) = sql(api_env, "SELECT status, message FROM geo.import_job")
    assert (state == "failed" and message in text) or "GitHub" in text
    # A failed request does not block the next one.
    github.status = 200
    assert _post(api_env).status_code == 202


def test_github_being_unreachable_is_a_failed_job(api_env: ApiEnv) -> None:
    github = _setup(api_env)
    github.fail = True
    r = _post(api_env)
    assert r.status_code == 502
    assert "reached" in r.json()["detail"]
    assert "ghp_test_token" not in json.dumps(sql(api_env, "SELECT message FROM geo.import_job"))


def test_one_import_at_a_time_until_a_job_stalls(api_env: ApiEnv) -> None:
    _setup(api_env)
    assert _post(api_env).status_code == 202
    again = _post(api_env, "austria")
    assert again.status_code == 409 and again.json()["code"] == "import_running"
    # The workflow reports it is running: still one at a time.
    (job_id,) = sql(api_env, "SELECT id::text FROM geo.import_job")[0]
    assert (
        cli.main(
            [
                "job",
                job_id,
                "running",
                "--run-url",
                "https://github.com/o/r/actions/runs/2",
                "--target-url",
                api_env.database_url,
            ]
        )
        == 0
    )
    assert _post(api_env, "austria").status_code == 409
    # Not heard of for too long: stalled, shown so, and a new request is accepted.
    sql(api_env, "UPDATE geo.import_job SET updated_at = now() - interval '2 hours'")
    cat = api_env.client.get("/v1/regions/catalog", headers=api_env.headers).json()
    assert next(x for x in cat["regions"] if x["id"] == LONDON)["job"]["status"] == "stalled"
    assert _post(api_env, "austria").status_code == 202
    # An import in progress (region importing) also blocks.
    sql(api_env, "UPDATE geo.import_job SET status = 'failed'")
    sql(api_env, "UPDATE geo.region SET status = 'importing' WHERE id = 'test-region'")
    assert _post(api_env).status_code == 409


def test_the_workflow_reports_through_the_job_command(api_env: ApiEnv) -> None:
    _setup(api_env)
    job = _post(api_env).json()
    url = api_env.database_url
    base = ["job", job["id"]]
    assert (
        cli.main(
            [
                *base,
                "running",
                "--run-url",
                "https://github.com/o/r/actions/runs/9",
                "--target-url",
                url,
            ]
        )
        == 0
    )
    assert (
        cli.main(
            [
                *base,
                "succeeded",
                "--message",
                "Imported: the region is available.",
                "--target-url",
                url,
            ]
        )
        == 0
    )
    got = api_env.client.get("/v1/regions/catalog", headers=api_env.headers).json()
    done = next(x for x in got["regions"] if x["id"] == LONDON)["job"]
    assert done["status"] == "succeeded" and done["message"].startswith("Imported")
    assert done["run_url"] == "https://github.com/o/r/actions/runs/9"
    # A run URL that is not https is ignored, and a bad id is refused.
    assert cli.main([*base, "failed", "--run-url", "javascript:x", "--target-url", url]) == 0
    assert "javascript" not in json.dumps(sql(api_env, "SELECT run_url FROM geo.import_job"))
    with pytest.raises(SystemExit):
        cli.main(["job", "not-a-uuid", "running", "--target-url", url])
    assert uuid.UUID(job["id"])


def test_the_daily_budget_limits_dispatches(api_env: ApiEnv) -> None:
    github = _setup(api_env)
    api_env.client.app.state.settings.github_daily_budget = 1  # type: ignore[attr-defined]
    assert _post(api_env).status_code == 202
    sql(api_env, "UPDATE geo.import_job SET status = 'succeeded'")
    r = _post(api_env)
    assert r.status_code == 502 and "today" in r.json()["detail"]
    assert len(github.requests) == 1
