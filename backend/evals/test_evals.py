"""Live evals: real agents, real model calls on your Claude plan. Run on demand:

    uv run pytest evals            # all cases
    uv run pytest evals -k maya    # one agent

Not part of the default `pytest` run (see testpaths in pyproject.toml).
"""

import asyncio

import pytest

from evals import harness
from evals.cases import CASES


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_case(case):
    run = harness.run_case(case)
    failures = asyncio.run(harness.evaluate(run))
    assert not failures, "\n".join(["", *failures, "", "--- last reply ---", run.replies[-1][:1500]])
