import os

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from agent_service.agents.seed import seed_default_agents  # noqa: E402
from agent_service.agents.store import init_store  # noqa: E402

init_store()
seed_default_agents()
