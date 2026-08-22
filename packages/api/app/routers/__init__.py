from .workflows import router as workflows_router
from .agents import router as agents_router
from .knowledge import router as knowledge_router
from .tools import router as tools_router
from .memory import router as memory_router
from .auth import router as auth_router
from .marketplace import router as marketplace_router
from .audit import router as audit_router
from .metrics import router as metrics_router
from .skills import router as skills_router

all_routers = [
    auth_router,
    workflows_router,
    agents_router,
    knowledge_router,
    tools_router,
    memory_router,
    marketplace_router,
    audit_router,
    metrics_router,
    skills_router,
]
