from __future__ import annotations

import json

from llmwiki.core import pricing
from llmwiki.core.paths import BrainPaths
from llmwiki.db.connection import get_connection
from llmwiki.db.repo import ChangeRequestRepo, JobRepo
from llmwiki.services import stats_service


def _ingest_job(conn, model, ti, to, *, cr_id, files, fallback=False, lat=1000):
    repo = JobRepo(conn)
    jid = repo.create("ingest", json.dumps({"source": "raw/x.txt"}), status="running")
    result = {
        "cr": cr_id,
        "files": files,
        "execution": {
            "model": model,
            "tokens_in": ti,
            "tokens_out": to,
            "latency_ms": lat,
            "tool_calls": 3,
            "used_fallback": fallback,
        },
    }
    repo.complete(jid, result=json.dumps(result))
    return jid


def _cr(conn, brain: BrainPaths, cr_id, status, *, job_id):
    diff = brain.change_requests / cr_id
    diff.mkdir(parents=True, exist_ok=True)
    ChangeRequestRepo(conn).insert(cr_id, "s", 1, str(diff), job_id=job_id)
    if status != "pending_review":
        ChangeRequestRepo(conn).set_status(cr_id, status, applied=(status == "applied"))


class TestPricing:
    def test_ollama_is_free(self) -> None:
        assert pricing.estimate_cost("ollama:llama3.1", 1000, 500) == 0.0

    def test_known_model_cost(self) -> None:
        cost = pricing.estimate_cost("openai:gpt-4o-mini", 1_000_000, 1_000_000)
        assert cost == 0.75  # 0.15 + 0.60

    def test_unknown_model_returns_none(self) -> None:
        assert pricing.estimate_cost("acme:mystery", 1000, 1000) is None

    def test_version_suffix_resolves(self) -> None:
        assert pricing.estimate_cost("anthropic:claude-sonnet-4-20250514", 0, 0) == 0.0


class TestAgentStats:
    def test_two_models_aggregate_correctly(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            j1 = _ingest_job(conn, "ollama:llama3.1", 100, 50, cr_id="CR-0001", files=2)
            j2 = _ingest_job(conn, "ollama:llama3.1", 300, 150, cr_id="CR-0002", files=1)
            j3 = _ingest_job(conn, "openai:gpt-4o-mini", 1000, 500, cr_id="CR-0003", files=1)
            _cr(conn, brain, "CR-0001", "applied", job_id=j1)
            _cr(conn, brain, "CR-0002", "rejected", job_id=j2)
            _cr(conn, brain, "CR-0003", "applied", job_id=j3)
            stats = stats_service.agent_stats(conn, brain)
        finally:
            conn.close()
        by_model = {s.model: s for s in stats}
        llama = by_model["ollama:llama3.1"]
        assert llama.runs == 2
        assert llama.tokens_in_avg == 200.0
        assert llama.tokens_out_avg == 100.0
        assert llama.applied == 1
        assert llama.rejected == 1
        assert llama.est_cost_usd == 0.0
        gpt = by_model["openai:gpt-4o-mini"]
        assert gpt.runs == 1
        assert gpt.est_cost_usd is not None and gpt.est_cost_usd > 0

    def test_fallback_and_phantom_rates(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            _ingest_job(conn, "ollama:m", 10, 10, cr_id="CR-0001", files=0, fallback=True)
            _ingest_job(conn, "ollama:m", 10, 10, cr_id="CR-0002", files=2, fallback=False)
            stats = stats_service.agent_stats(conn, brain)
        finally:
            conn.close()
        s = stats[0]
        assert s.fallback_rate == 0.5
        assert s.phantom_rate == 0.5  # one of two ingest runs wrote 0 files

    def test_jobs_without_execution_ignored(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            repo = JobRepo(conn)
            jid = repo.create("lint", "{}", status="running")
            repo.complete(jid, result=json.dumps({"findings": []}))
            stats = stats_service.agent_stats(conn, brain)
        finally:
            conn.close()
        assert stats == []

    def test_since_filter(self, brain: BrainPaths) -> None:
        conn = get_connection(brain.db_path)
        try:
            _ingest_job(conn, "ollama:m", 10, 10, cr_id="CR-0001", files=1)
            # since far in the future → nothing.
            stats = stats_service.agent_stats(conn, brain, since="2999-01-01")
        finally:
            conn.close()
        assert stats == []
