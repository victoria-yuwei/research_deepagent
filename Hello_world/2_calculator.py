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



# 运行前必须先 export 两个环境变量：
#   export SILICONFLOW_API_KEY=sk-你的密钥   # 硅基流动平台的 API 密钥
#   export MODEL_NAME=模型ID                  # 可选，如 zai-org/GLM-5.2；不设则默认 Qwen/Qwen2.5-7B-Instruct
# 协议说明：本脚本通过 OpenAI 兼容协议（/v1/chat/completions）访问硅基流动（SiliconFlow）平台。

def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
    # 只解析数字、括号和四则运算，不执行模型生成的 Python 代码
    import ast
    import operator

    if len(expression) > 200:
        raise ValueError("表达式过长")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("表达式过于复杂")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub,
                  ast.Mult: operator.mul, ast.Div: operator.truediv}

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("只支持数字、括号和 + - * / 运算")

    return evaluate(tree.body)

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
    tools=[calculate],
    system_prompt="You are a helpful assistant. Your tone must be very cute. The user you face is Victoria Queen",
)


result = agent.invoke(
    {"messages": [{"role": "user", "content": "1+1=几"},
    {"role": "assistant", "content": "2"},
    {"role": "user", "content": "再加一呢？"}]}
)
print(result["messages"][-1].content)
