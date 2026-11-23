# 6_policy_wrapper_backend.py —— 方式二：通用包装器（PolicyWrapper）
# 给 Agent 的文件工具加"目录保护策略"：把策略检查层套在任意后端外面，
# 换后端（FilesystemBackend / StoreBackend / CompositeBackend 等）都不用改代码。
# 对比：7_guarded_backend.py 用的是方式一（继承现有后端）。

# 定义搜索工具引进依赖
import os
from pathlib import PurePosixPath
from typing import Literal
from tavily import TavilyClient

# 创建Agent并提示系统提示词引进依赖
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware

# 文件后端引进依赖（用于给 Agent 的文件工具加"目录保护策略"）
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import (
    BackendProtocol,
    WriteResult,
    EditResult,
    DeleteResult,
)

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


# ---------- 目录保护策略：公共检查函数（两种后端写法共用） ----------

# 统一虚拟路径：把任意写法规范成 "/xxx/yyy" 的形式，并拒绝 ".." 路径穿越
def policy_path(path: str) -> PurePosixPath:
    """统一虚拟路径的起始斜杠、重复斜杠、`.` 和末尾斜杠。"""
    # 补上起始斜杠后交给 PurePosixPath：它会自动合并重复斜杠、去掉 "." 和末尾斜杠
    normalized = PurePosixPath("/" + path.lstrip("/"))
    # 含 ".." 说明想跳出虚拟根目录（路径穿越攻击），直接拒绝
    if ".." in normalized.parts:
        raise ValueError("策略路径不能包含 '..'")
    return normalized


# 判断某个路径是否落入受保护目录；deleting=True 时额外做"祖先反向检查"
def denied_by_directory(
    path: str, protected_dirs: list[PurePosixPath], *, deleting: bool = False
) -> bool:
    """按目录层级判断 path 是否应被拒绝（含路径相等的情况）。"""
    try:
        # 归一化失败（比如含 ".."）一律视为拒绝，宁可错杀不可放过
        target = policy_path(path)
    except ValueError:
        return True
    return any(
        # 正向检查：目标在受保护目录内（is_relative_to 包含相等的情况）。
        # 因此 /policies 和 /policies/rules.txt 都会被拦，/policies-copy 不会误伤。
        target.is_relative_to(directory)
        # 反向检查（仅删除时）：待删目录是受保护目录的祖先。
        # 例如保护 /workspace/policies 时，删除 /workspace 会连它一起删掉，也要拒绝。
        or (deleting and directory.is_relative_to(target))
        for directory in protected_dirs
    )


# ---------- 方式二：通用包装器（套在任意遵循虚拟路径约定的后端外面） ----------

class PolicyWrapper(BackendProtocol):
    """给任意 BackendProtocol 后端套上一层"目录保护"装饰器。

    只读操作（ls/read/grep/glob）原样转发、不设限；
    写操作（write/edit/delete）先过策略检查，被拒时返回带错误信息的
    Result 对象而不是抛异常——模型会看到拒绝原因，可以换路径重试，
    整个 Agent 运行不会崩。
    """

    def __init__(self, inner: BackendProtocol, deny_prefixes: list[str]):
        """保存内层后端，并把保护目录统一归一化成规范虚拟路径。"""
        self.inner = inner  # 被包装的真实后端（如 FilesystemBackend）
        self.protected_dirs = [policy_path(p) for p in deny_prefixes]

    # 内部小工具：判断某路径是否该被拒绝；deleting=True 启用删除专用的反向检查
    def _deny(self, path: str, *, deleting: bool = False) -> bool:
        return denied_by_directory(path, self.protected_dirs, deleting=deleting)

    # ---- 只读操作：不设限制，直接转发给内层后端 ----

    def ls(self, path):
        """列目录：直接转发。"""
        return self.inner.ls(path)

    def read(self, file_path, offset=0, limit=2000):
        """读文件：直接转发。"""
        return self.inner.read(file_path, offset=offset, limit=limit)

    def grep(self, pattern, path=None, glob=None, *, max_count=None):
        """内容搜索：直接转发（max_count 是协议里的可选参数，一并透传）。"""
        return self.inner.grep(pattern, path, glob, max_count=max_count)

    def glob(self, pattern, path=None):
        """按模式匹配文件：直接转发。"""
        return self.inner.glob(pattern, path)

    # ---- 写操作：先查策略，放行才转给内层后端 ----

    def write(self, file_path: str, content: str) -> WriteResult:
        """写文件：先过目录保护检查，被拒则返回错误结果。"""
        if self._deny(file_path):
            return WriteResult(error=f"写入被拒绝：{file_path}")
        return self.inner.write(file_path, content)

    def edit(self, file_path: str, old_string: str, new_string: str,
             replace_all: bool = False) -> EditResult:
        """编辑文件：先过目录保护检查，被拒则返回错误结果。"""
        if self._deny(file_path):
            return EditResult(error=f"编辑被拒绝：{file_path}")
        return self.inner.edit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        """删除文件/目录：先过目录保护检查（含祖先反向检查），被拒则返回错误结果。"""
        if self._deny(file_path, deleting=True):
            return DeleteResult(error=f"删除被拒绝：{file_path}")
        return self.inner.delete(file_path)


# 定义搜索工具引进依赖
def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search for the given query.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
        topic: The topic category for the search.
        include_raw_content: Whether to include raw page content.
    """
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

# 创建Agent并提示系统提示词引进依赖
    # 使用硅基流动接入模型（当前免费的 Qwen2.5-7B 即可跑通，复杂任务可改用 GLM-5.2）
model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct"),  # 可用 MODEL_NAME 覆盖
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
)

# 组装带目录保护的真实文件后端
# 虚拟工作区根目录：Agent 看到的 "/" 就是这个目录（脚本同级的 agent_workspace/）
WORKSPACE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_workspace")
os.makedirs(WORKSPACE_ROOT, exist_ok=True)  # 确保目录存在，写文件时不会因路径不存在报错

# 内层后端：FilesystemBackend 用 virtual_mode=True，
# 所有路径按虚拟路径处理（相对 / 即 WORKSPACE_ROOT），不解析符号链接等存储别名
_fs_backend = FilesystemBackend(root_dir=WORKSPACE_ROOT, virtual_mode=True)

# 外层后端：套上目录保护包装器，/policies 及其全部后代被保护
backend = PolicyWrapper(_fs_backend, deny_prefixes=["/policies"])

research_instructions = """你是一位专业的研究员。
你的工作是进行深入研究，然后撰写一份完整的研究报告。

你可以使用 internet_search 工具搜索互联网获取信息。
你也可以使用文件工具在虚拟工作区里读写文件（根目录 "/" 即你的工作区）。
注意：/policies 目录是受保护区域，你无法在其中写入、编辑或删除任何文件。
"""

agent = create_deep_agent(
    model=model,
    tools=[internet_search],
    system_prompt=research_instructions,
    middleware=[TodoListMiddleware()],
    backend=backend,  # 挂上带目录保护的文件后端
)


# 运行Agent：故意同时测试"放行的写入"和"被保护目录的写入"
result = agent.invoke(
    {"messages": [{"role": "user", "content": (
        "请用文件工具做两件事，然后分别告诉我两次操作的结果：\n"
        "1) 把一句关于 LangGraph 的简介写入 /notes.md；\n"
        "2) 尝试把一行机密记录写入 /policies/secret.md。"
    )}]}
)

print(result["messages"][-1].content)
