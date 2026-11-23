# 7_guarded_backend.py —— 方式一：继承现有后端（GuardedBackend）
# 给 Agent 的文件工具加"目录保护策略"：直接继承 FilesystemBackend，
# 重写写操作方法，在调用 super() 之前先过策略检查。
# 局限：只能用于 FilesystemBackend，换其他后端要重新写子类。
# 对比：6_policy_wrapper_backend.py 用的是方式二（通用包装器，后端无关）。

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
from deepagents.backends.protocol import WriteResult, EditResult, DeleteResult

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


# ---------- 目录保护策略：公共检查函数 ----------

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


# ---------- 方式一：继承现有后端 ----------

class GuardedBackend(FilesystemBackend):
    """继承 FilesystemBackend 的"带目录保护"后端。

    与包装器（方式二）不同：这里重写写操作方法，在转给 super() 之前
    先做策略检查。只读操作（ls/read/grep/glob）不需要重写，天然继承。
    """

    def __init__(self, *, deny_prefixes: list[str], **kwargs):
        """deny_prefixes 是要保护的目录前缀列表；其余参数原样传给父类
        （如 root_dir、virtual_mode、max_file_size_mb）。"""
        super().__init__(**kwargs)  # 父类完成真实文件系统的初始化
        # 启动时把保护目录统一归一化成规范虚拟路径
        self.protected_dirs = [policy_path(p) for p in deny_prefixes]

    def write(self, file_path: str, content: str) -> WriteResult:
        """写文件：先过目录保护检查，被拒则返回错误结果，放行才调父类。"""
        if denied_by_directory(file_path, self.protected_dirs):
            return WriteResult(error=f"写入被拒绝：{file_path}")
        return super().write(file_path, content)

    def edit(self, file_path: str, old_string: str, new_string: str,
             replace_all: bool = False) -> EditResult:
        """编辑文件：先过目录保护检查，被拒则返回错误结果，放行才调父类。"""
        if denied_by_directory(file_path, self.protected_dirs):
            return EditResult(error=f"编辑被拒绝：{file_path}")
        return super().edit(file_path, old_string, new_string, replace_all)

    def delete(self, file_path: str) -> DeleteResult:
        """删除文件/目录：先过目录保护检查（含祖先反向检查），被拒则返回错误结果。"""
        if denied_by_directory(file_path, self.protected_dirs, deleting=True):
            return DeleteResult(error=f"删除被拒绝：{file_path}")
        return super().delete(file_path)


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

# 组装带目录保护的后端（方式一：一步到位，直接实例化子类）
# 虚拟工作区根目录：Agent 看到的 "/" 就是这个目录（脚本同级的 agent_workspace_subclass/）
WORKSPACE_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "agent_workspace_subclass"
)
os.makedirs(WORKSPACE_ROOT, exist_ok=True)  # 确保目录存在，写文件时不会因路径不存在报错

# virtual_mode=True：所有路径按虚拟路径处理（相对 / 即 WORKSPACE_ROOT），不解析符号链接等存储别名
backend = GuardedBackend(root_dir=WORKSPACE_ROOT, virtual_mode=True, deny_prefixes=["/policies"])

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


# 运行Agent：故意测试"放行的写入""被保护目录的写入"和"删除保护目录本身"
result = agent.invoke(
    {"messages": [{"role": "user", "content": (
        "请用文件工具做三件事，然后分别告诉我每次操作的结果：\n"
        "1) 把一句关于 LangGraph 的简介写入 /notes.md；\n"
        "2) 尝试把一行机密记录写入 /policies/secret.md；\n"
        "3) 尝试删除 /policies 目录本身。"
    )}]}
)

print(result["messages"][-1].content)
