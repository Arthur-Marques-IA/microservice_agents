import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from agent_service.agents.seed import seed_default_agents  # noqa: E402
from agent_service.agents.store import init_store  # noqa: E402
from agent_service.tools.seed import seed_default_tools  # noqa: E402
from agent_service.tools.store import init_store as init_tool_store  # noqa: E402

init_store()
init_tool_store()
seed_default_tools()
seed_default_agents()
