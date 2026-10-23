"""Standalone runner: ``uv run python main.py learner@example.com``."""

import asyncio
import sys

from dotenv import load_dotenv

from planner.workflow import LessonPlanningWorkflow


async def main(user_id: str) -> None:
    """Prepare the next lesson for one learner and print it as JSON."""
    package = await LessonPlanningWorkflow().run(user_id)
    print(package.model_dump_json(indent=2))


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "learner@example.com"))
