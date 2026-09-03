import asyncio
import re

import pytest

from benchmarks.benchmark import TrackedClient, _deck_sample, project
from benchmarks.compounding import measure
from benchmarks.metrics import (
    Pricing,
    cost_usd,
    distribution,
    linear_slope,
    quality_metrics,
    rss_bytes,
)
from benchmarks.tasks import COLD_TASK, TASKS
from standup.core import pipeline
from standup.core.agent import Turn
from standup.core.agent.commands import Select, Write
from standup.core.models import Scope, Slide, VisualElement


class DeckModel:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.round = 0

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        self.input_tokens += 10
        self.output_tokens += 5
        self.round += 1
        if self.round == 1:
            return Turn(
                reply="",
                changes_deck=True,
                commands=[
                    Select(
                        action="select",
                        request="recent work",
                        scope=Scope(slide_budget=1),
                    )
                ],
            )
        if self.round == 2:
            candidate = re.search(r"  (.+) \[no slide\]", prompt).group(1)
            return Turn(
                reply="",
                changes_deck=True,
                commands=[
                    Write(
                        action="write",
                        slides=[
                            Slide(
                                candidate_id=candidate,
                                title="Recent work",
                                bullets=["Done"],
                                elements=[
                                    VisualElement(
                                        id="title", kind="text", x=0, y=0, width=100, height=100, text="Recent work"
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        return Turn(reply="Done")

    async def aclose(self):
        pass


class FakeModel:
    def __init__(self, *, fail=False):
        self.input_tokens = 0
        self.output_tokens = 0
        self.fail = fail

    async def structured(self, prompt, schema, *, system=None, max_tokens=None):
        if self.fail:
            raise RuntimeError("upstream failed")
        self.input_tokens += 120
        self.output_tokens += 30
        return Turn(reply="done")

    async def aclose(self):
        pass


def test_performance_tasks_do_not_expire_with_the_calendar():
    prompts = [COLD_TASK[1], *TASKS.values()]
    forbidden = ("today", "yesterday", "this week", "last week", "this month")
    assert not any(term in prompt.lower() for prompt in prompts for term in forbidden)


def test_distribution_uses_interpolated_percentiles_and_keeps_sample_count():
    measured = distribution([1.0, 2.0, 3.0, 4.0])

    assert measured == {
        "n": 4,
        "mean": 2.5,
        "stdev": pytest.approx(1.11803398875),
        "min": 1.0,
        "p50": 2.5,
        "p95": pytest.approx(3.85),
        "max": 4.0,
    }


def test_cost_uses_separate_input_and_output_rates():
    pricing = Pricing(2.0, 10.0, "test")
    assert cost_usd(1_000_000, 500_000, pricing) == 7.0
    assert cost_usd(1, 1, None) is None


def test_steady_state_slope_is_measured_per_project():
    assert linear_slope([2.0, 2.5, 3.0, 3.5]) == pytest.approx(0.5)
    assert linear_slope([7.0]) == 0.0


def test_current_process_rss_is_available_on_the_supported_platform():
    assert rss_bytes() > 0


def test_quality_recall_is_path_based_but_precision_is_candidate_based():
    measured = quality_metrics(
        [["src/auth.py", "src/helper.py"], ["src/noise.py"]],
        {"src/auth.py": 2.0, "src/session.py": 1.0},
    )

    assert measured["recall"] == 0.5
    assert measured["candidate_precision"] == 0.5
    assert measured["selected_candidates"] == 2
    assert measured["selected_paths"] == 3


def test_ndcg_rewards_putting_the_stronger_evidence_first():
    relevant = {"strong.py": 2.0, "weak.py": 1.0}
    right = quality_metrics([["strong.py"], ["weak.py"]], relevant)
    reversed_order = quality_metrics([["weak.py"], ["strong.py"]], relevant)

    assert right["ndcg"] == 1.0
    assert reversed_order["ndcg"] < right["ndcg"]


def test_tracked_client_attributes_each_logical_call_and_failure():
    client = TrackedClient(FakeModel())
    result = asyncio.run(client.structured("prompt", Turn))

    assert result.reply == "done"
    assert client.calls[0]["success"] is True
    assert client.calls[0]["input_tokens"] == 120
    assert client.calls[0]["output_tokens"] == 30
    assert client.calls[0]["response_type"] == "Turn"
    assert client.calls[0]["response_commands"] == []
    assert client.calls[0]["response_reply_present"] is True

    failing = TrackedClient(FakeModel(fail=True))
    with pytest.raises(RuntimeError, match="upstream failed"):
        asyncio.run(failing.structured("prompt", Turn))
    assert failing.calls[0]["success"] is False
    assert "upstream failed" in failing.calls[0]["error"]


def test_deck_sample_records_real_command_outcomes_without_assuming_converse_returns_a_turn(repo):
    sample = asyncio.run(
        _deck_sample(
            TrackedClient(DeckModel()),
            [repo],
            "recap",
            "Give me one slide on recent work",
            "warm",
            1,
        )
    )

    assert sample["success"] is True
    assert sample["written_slides"] == 1
    assert len(sample["command_outcomes"]) == 2
    assert sample["command_outcomes"][0].startswith("select(")
    assert sample["command_outcomes"][1].startswith("write(")


def test_benchmark_project_evicts_process_cache_when_disposed(repo):
    with project([repo]) as (store, project_id):
        root = store.paths(project_id).root
        pipeline._INDEX_CACHE[project_id] = ("fingerprint", None)
        assert root.exists()

    assert not root.exists()
    assert project_id not in pipeline._INDEX_CACHE


def test_a_correction_compounds_into_the_next_select():
    report = measure()

    assert report["compounded"] is True
    assert report["chosen_before_correction"] is False
    assert report["chosen_after_correction"] is True
