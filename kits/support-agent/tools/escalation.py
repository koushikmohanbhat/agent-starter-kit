from __future__ import annotations

from agent_kit.tools import ToolContext


def escalate_to_human(reason: str, *, ctx: ToolContext) -> dict:
    """Hand the conversation to a human support agent, with a one-line reason."""
    return ctx.services["orders"].ticket(ctx.user.id, reason, ctx.session_id)
