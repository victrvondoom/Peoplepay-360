import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agents.orchestrator.case_workflow import case_workflow
from app.models.domain import Domain


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a fast LangGraph healthcare workflow smoke test.")
    parser.add_argument("--query", default="Does Star Health cover cataract surgery?")
    parser.add_argument("--institution", default="Star Health")
    args = parser.parse_args()

    state = await case_workflow.run(
        {
            "case_id": "smoke-test",
            "user_id": "local-test",
            "domain": Domain.HEALTH_INSURANCE,
            "case_summary": args.query,
            "institution_name": args.institution,
        }
    )
    print(f"workflow_engine={state.get('workflow_engine')}")
    print(f"route={state.get('route')}")
    print(f"llm_call_count={state.get('llm_call_count')}")
    print(f"specialists={[output.get('route') for output in state.get('specialist_outputs', [])]}")
    print(f"trace={state.get('agent_trace')}")


if __name__ == "__main__":
    asyncio.run(main())
