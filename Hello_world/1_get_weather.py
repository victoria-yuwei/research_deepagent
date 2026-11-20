# 运行前必须先 export 两个环境变量：
#   export SILICONFLOW_API_KEY=sk-你的密钥   # 硅基流动平台的 API 密钥
#   export MODEL_NAME=模型ID                  # 可选，如 zai-org/GLM-5.2；不设则默认 Qwen/Qwen2.5-7B-Instruct
# 协议说明：本脚本通过 OpenAI 兼容协议（/v1/chat/completions）访问硅基流动（SiliconFlow）平台。

import os
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

# 通过硅基流动接入模型（兼容 OpenAI 接口）
model = ChatOpenAI(
    # 当前免费模型，可用 MODEL_NAME 环境变量覆盖（如付费的 zai-org/GLM-5.2）
    model=os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct"),
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
)

def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"

agent = create_deep_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a helpful assistant. Your tone must be very cute. The user you face is Victoria Queen",
)
# agent.invoke(...) 都是一次独立调用。
# 如果你想要真正的多轮对话（agent 记住上一轮），通常要把上一轮的完整消息历史传进去或者用 agent 的会话/记忆机制。
# 你这里手动把历史拼进 messages 列表，是模拟多轮的一种方式，可以工作，但要保证历史顺序正确、最后一条是 user。
result = agent.invoke(
    {"messages": [{"role": "user", "content": "天气怎么样？"},
    {"role": "assistant", "content": "哪里的？"},
    {"role": "user", "content": "呼和浩特"}]}
)

print(result["messages"][-1].content)