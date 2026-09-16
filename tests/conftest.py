import os

from cryptography.fernet import Fernet

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())

from agent_service.agents.seed import seed_default_agents  # noqa: E402
from agent_service.agents.store import init_store  # noqa: E402
from agent_service.models.store import init_store as init_model_provider_store  # noqa: E402
from agent_service.tools.seed import seed_default_tools  # noqa: E402
from agent_service.tools.store import init_store as init_tool_store  # noqa: E402

init_store()
init_tool_store()
init_model_provider_store()
seed_default_tools()
seed_default_agents()
