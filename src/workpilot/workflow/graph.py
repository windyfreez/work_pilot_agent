"""LangGraph 任务工作流：规划 → 执行 → 验证 → 结束。"""

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from workpilot.config import Settings
from workpilot.tools._paths import PathResolver
from workpilot.tools.files import is_overwrite
from workpilot.tools.registry import build_tools

from .state import Plan, TaskState
from .verify import verify_step

_PLANNING_SYSTEM_PROMPT = (
    "你是任务规划器。把用户任务分解为有序步骤，只能使用这些工具："
    "list_files（列出目录下的文件）、read_document（读取文本文件）、"
    "create_document（创建/覆盖文本文件）。"
    "每个步骤包含：工具名 tool、参数 args（dict）、说明 description。"
)


def build_graph(
    settings: Settings,
    model: BaseChatModel,
    checkpointer=None,
    should_cancel=None,
):
    """构建并编译任务工作流图。

    ``should_cancel`` 为可选回调 ``Callable[[str], bool]``，接收 task_id，
    返回 True 时工作流在下一个节点前终止，状态置为 ``cancelled``（协作式取消）。
    """
    should_cancel = should_cancel or (lambda task_id: False)
    tools = build_tools(settings)
    tools_by_name = {t.name: t for t in tools}
    resolver = PathResolver(settings.allowed_dirs)
    planner = model.with_structured_output(Plan)

    def plan_node(state: TaskState) -> dict:
        plan = planner.invoke(
            [
                ("system", _PLANNING_SYSTEM_PROMPT),
                ("human", state["task_input"]),
            ]
        )
        steps = plan.steps[: settings.task_max_steps]  # 限制最大步骤数
        if not steps:
            return {"status": "failed", "error": "规划结果为空"}
        return {"plan": steps, "current_step": 0, "retries": 0, "status": "planned"}

    def execute_node(state: TaskState) -> dict:
        if should_cancel(state.get("task_id", "")):
            return {"status": "cancelled"}
        step = state["plan"][state["current_step"]]

        # 高风险操作（覆盖已存在且内容不同的文件）需人工确认
        if step.tool == "create_document":
            path = step.args.get("path", "")
            content = step.args.get("content", "")
            if is_overwrite(resolver, path, content):
                approve = interrupt(
                    {
                        "action": "confirm_overwrite",
                        "path": path,
                        "description": f"将覆盖已存在的文件：{path}",
                    }
                )
                if not approve:
                    return {"status": "failed", "error": "用户拒绝覆盖文件"}

        tool = tools_by_name[step.tool]
        result = tool.invoke(step.args)
        results = list(state.get("results", [])) + [str(result)]
        return {"results": results, "status": "executing"}

    def verify_node(state: TaskState) -> dict:
        if should_cancel(state.get("task_id", "")):
            return {"status": "cancelled"}
        step = state["plan"][state["current_step"]]
        last = state.get("results", [])[-1] if state.get("results") else ""
        verification = verify_step(step, last, resolver)
        retries = state.get("retries", 0)

        if verification.ok:
            if state["current_step"] + 1 >= len(state["plan"]):
                return {"verification": verification, "status": "succeeded"}
            return {
                "verification": verification,
                "current_step": state["current_step"] + 1,
                "retries": 0,
                "status": "planned",
            }

        if retries < settings.task_max_retries:
            return {
                "verification": verification,
                "retries": retries + 1,
                "status": "planned",
            }
        return {"verification": verification, "status": "failed", "error": verification.message}

    def route_after_plan(state: TaskState) -> str:
        return END if state.get("status") in ("failed", "cancelled") else "execute"

    def route_after_execute(state: TaskState) -> str:
        return END if state.get("status") in ("failed", "cancelled") else "verify"

    def route_after_verify(state: TaskState) -> str:
        if state.get("status") in ("succeeded", "failed", "cancelled"):
            return END
        return "execute"

    graph = StateGraph(TaskState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("verify", verify_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", route_after_plan, {END: END, "execute": "execute"})
    graph.add_conditional_edges("execute", route_after_execute, {END: END, "verify": "verify"})
    graph.add_conditional_edges("verify", route_after_verify, {END: END, "execute": "execute"})

    return graph.compile(checkpointer=checkpointer)
