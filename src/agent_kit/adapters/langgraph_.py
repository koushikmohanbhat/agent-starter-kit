"""LangGraph adapter: a StateGraph (model node <-> ToolNode) compiled per turn, with LangChain chat models.

Models: ChatOpenAI for OpenAI and OpenAI-compatible endpoints (incl. the offline scripted model);
ChatAnthropic (`langchain-anthropic`), ChatBedrockConverse (`langchain-aws`) and ChatGoogleGenerativeAI
(`langchain-google-genai`) when installed."""
from __future__ import annotations

from .base import AdapterError, AdapterResult, FrameworkAdapter, MissingDependency


class Adapter(FrameworkAdapter):
    name, extra = "langgraph", "langgraph"

    def _llm(self):
        m, st = self.model, self.model.settings
        kw = {k: st[k] for k in ("temperature", "max_tokens") if k in st}
        try:
            if m.openai_like:
                import httpx
                from langchain_openai import ChatOpenAI
                # an explicit client per turn: langchain-openai's default async client is cached per process and breaks
                # when the event loop that created it closes (tests, workers that recycle loops)
                return ChatOpenAI(model=m.name, base_url=m.base_url, api_key=m.api_key or "none",
                                  http_async_client=httpx.AsyncClient(timeout=self.definition.limits.timeout_s), **kw)
            if m.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(model=m.name, api_key=m.api_key, **kw)
            if m.provider == "bedrock":
                from langchain_aws import ChatBedrockConverse
                return ChatBedrockConverse(model=m.name, region_name=m.region, **kw)
            if m.provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(model=m.name, project=m.project, location=m.location, vertexai=True, **kw)
        except ImportError as e:
            raise MissingDependency("langgraph", f"langgraph,{m.provider}", e) from e
        raise AdapterError(f"langgraph adapter: unsupported provider {m.provider}")

    async def run(self, instructions, tools, history, message):
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
            from langchain_core.tools import StructuredTool
            from langgraph.graph import END, START, MessagesState, StateGraph
            from langgraph.prebuilt import ToolNode, tools_condition
        except ImportError as e:  # pragma: no cover
            raise MissingDependency("langgraph", self.extra, e) from e

        def wrap(t):
            async def coro(**kwargs):
                return await t.call(kwargs)
            return StructuredTool(name=t.name, description=t.description, args_schema=t.schema, coroutine=coro)

        lc_tools = [wrap(t) for t in tools]
        llm = self._llm().bind_tools(lc_tools)
        system = SystemMessage(instructions)

        async def model_node(state: MessagesState):
            return {"messages": [await llm.ainvoke([system, *state["messages"]])]}

        g = StateGraph(MessagesState)
        g.add_node("model", model_node)
        g.add_node("tools", ToolNode(lc_tools))
        g.add_edge(START, "model")
        g.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
        g.add_edge("tools", "model")
        app = g.compile()
        msgs = [HumanMessage(h["content"]) if h["role"] == "user" else AIMessage(h["content"]) for h in history] + [HumanMessage(message)]
        out = await app.ainvoke({"messages": msgs}, {"recursion_limit": 2 * self.definition.limits.max_turns + 1})
        last = out["messages"][-1]
        usage = {"input_tokens": 0, "output_tokens": 0}
        for mm in out["messages"]:
            um = getattr(mm, "usage_metadata", None) or {}
            usage["input_tokens"] += um.get("input_tokens", 0)
            usage["output_tokens"] += um.get("output_tokens", 0)
        text = last.content if isinstance(last.content, str) else " ".join(p.get("text", "") for p in last.content if isinstance(p, dict))
        return AdapterResult(text, usage, self.model.name, out)
