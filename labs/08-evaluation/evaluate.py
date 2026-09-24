#!/usr/bin/env python3
"""把固定案例上传到 Phoenix，并在相同输入上运行可比较的实验。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
from phoenix.client import Client
from phoenix.client.experiments import run_experiment

AGENT_DIR = Path(__file__).resolve().parents[1] / "01-mini-coding-agent"
sys.path.insert(0, str(AGENT_DIR))

LAB_DIR = Path(__file__).resolve().parent
DEMO_DIR = LAB_DIR / "demo"

from agent import CodingAgent, MODEL, ReadTool, Workspace  # noqa: E402
from extension import CASES, EvaluationExtension, grade_case  # noqa: E402
from observability import PhoenixTraceObserver, enable_phoenix  # noqa: E402

DATASET_NAME = "ai-is-simple-lab-08-cases"


def _dataset_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "case_id": case["id"],
            "question": case["question"],
            "required_terms": json.dumps(case["expected"]["required_terms"], ensure_ascii=False),
            "must_use_read": case["expected"]["must_use_read"],
        }
        for case in CASES
    ])


def ensure_dataset(client: Client):
    # Stable IDs let Phoenix update the existing dataset version instead of appending duplicates.
    return client.datasets.create_dataset(
        dataframe=_dataset_rows(),
        name=DATASET_NAME,
        input_keys=["case_id", "question"],
        output_keys=["required_terms", "must_use_read"],
        example_id_key="case_id",
    )


def run_agent(input: dict) -> dict:
    case = next(case for case in CASES if case["id"] == input["case_id"])
    events: list[dict] = []
    registered_observer = enable_phoenix()
    # Each case gets its own event bridge, so concurrent experiments cannot mix Span state.
    observer = PhoenixTraceObserver(registered_observer.tracer)

    def emit(event: dict) -> None:
        observer.on_event(event)
        events.append(event)

    agent = CodingAgent(
        Workspace(DEMO_DIR),
        confirm=lambda _action: False,
        emit=emit,
        extensions=(EvaluationExtension(case, read_only=True),),
    )

    # This dataset only needs read-only questions. Removing write, edit, and bash
    # makes an experiment incapable of changing the demo workspace or running commands.
    agent.tools = {"read": ReadTool()}
    with observer.agent_run(input["question"]):
        agent.run(input["question"])

    result = next(
        (event for event in reversed(events) if event.get("type") == "assistant_message"),
        {},
    )
    return {
        "answer": str(result.get("content") or ""),
        "tools_used": [
            str(event.get("name"))
            for event in events
            if event.get("type") == "tool_call"
        ],
    }


def required_facts_score(input: dict, output: dict, expected: dict) -> float:
    required_terms = json.loads(expected["required_terms"])
    scores = grade_case(output, {
        "required_terms": required_terms,
        "must_use_read": expected["must_use_read"],
    })
    return float(scores["required_facts"])


def tool_selection_score(input: dict, output: dict, expected: dict) -> float:
    scores = grade_case(output, {
        "required_terms": [],
        "must_use_read": expected["must_use_read"],
    })
    return float(scores["tool_selection"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="baseline", help="实验版本名，例如 baseline 或 prompt-v2")
    args = parser.parse_args()

    os.environ.setdefault("PHOENIX_PROJECT_NAME", "ai-is-simple-lab-08")
    enable_phoenix()
    client = Client()
    dataset = ensure_dataset(client)
    experiment = run_experiment(
        dataset=dataset,
        task=run_agent,
        evaluators=[required_facts_score, tool_selection_score],
        experiment_name=f"mini-agent-{args.name}",
        experiment_metadata={"model": MODEL, "variant": args.name},
    )
    print(f"实验已保存到 Phoenix：{getattr(experiment, 'id', '完成')}")
    print(f"数据集：{DATASET_NAME}（{len(CASES)} 个固定案例）")
    print("打开 Phoenix 的 Datasets & Experiments 页面查看分数和失败案例。")


if __name__ == "__main__":
    main()
