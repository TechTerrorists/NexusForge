"""NexusForge middleware pipeline — composable request/response hooks for agents."""

from packages.middleware.pipeline import MiddlewarePipeline, Middleware, MiddlewareContext
from packages.middleware.builtins.budget_guard import BudgetGuardMiddleware
from packages.middleware.builtins.prompt_guard import PromptInjectionGuardMiddleware
from packages.middleware.builtins.pii_redactor import PIIRedactorMiddleware
from packages.middleware.builtins.context_compression import ContextCompressionMiddleware
from packages.middleware.builtins.structured_output import StructuredOutputMiddleware
from packages.middleware.builtins.tool_approval import ToolApprovalMiddleware

__all__ = [
    "MiddlewarePipeline",
    "Middleware",
    "MiddlewareContext",
    "BudgetGuardMiddleware",
    "PromptInjectionGuardMiddleware",
    "PIIRedactorMiddleware",
    "ContextCompressionMiddleware",
    "StructuredOutputMiddleware",
    "ToolApprovalMiddleware",
]
