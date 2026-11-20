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

def convert_currency(amount: float, from_currency: str, to_currency: str = "CNY") -> dict:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert.
        from_currency: The source currency code, e.g. "USD".
        to_currency: The target currency code, defaults to "CNY".
    """
    # 这里用固定汇率做演示；真实场景可接入汇率 API
    rates = {"USD": 7.2, "CNY": 1.0, "EUR": 7.8}
    cny = amount * rates[from_currency]
    return {"amount": round(cny / rates[to_currency], 2), "currency": to_currency}


agent = create_deep_agent(
    model=model,
    tools=[convert_currency],
    system_prompt="You are a helpful assistant. Your tone must be very cute. The user you face is Victoria Queen",
)


result = agent.invoke(
    {"messages": [{"role": "user", "content": "一美元等于多少人民币"},
    {"role": "assistant", "content": "7块多"},
    {"role": "user", "content": "说错了，不是美元，是欧元，那欧元呢？哪个能换更多人民币"}]}
)
print(result["messages"][-1].content)
