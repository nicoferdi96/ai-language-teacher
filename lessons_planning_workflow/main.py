from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.tools.tavily import TavilyTools
from dotenv import load_dotenv

load_dotenv()

dietcoach_agent = Agent(
    name="LessonPlanningAgent",
    model=OpenRouter(id="qwen/qwen3.5-flash-02-23"),
    tools=[TavilyTools()],
    instructions=(
        "Write a report on the research topic provided. Output only the "
        "report. Always perform a couple of searches to make sure you are "
        "researching what is expected."
    ),
    markdown=True,
    debug_mode=True,
)


if __name__ == "__main__":
    dietcoach_agent.print_response(
        "What are the latest news in the Agentic AI World for 2026?",
        stream=True,
    )

