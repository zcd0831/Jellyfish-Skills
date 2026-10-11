"""最小可用的 Python 脚本插件骨架。

把它拷成 scripts/python/<脚本 id>/ 下的 main.py，改掉工具名与逻辑即可；目录名就是脚本 id。
三件事必须一起改，否则脚本会拒绝服务：

1. ``manifest.json`` 里的 ``entry`` 指到这个文件；
2. ``manifest.json`` 与下面这些装饰器声明**必须逐项一致**（比对的是名字集合）；
3. 改完跑 ``dump_manifest.py <目录> --write`` 重新生成清单。

三条纪律（都踩过）：
* 失败一律 ``raise ScriptError(...)``，**不要**返回 ``{"error": ...}``——后者会被当成正常输出；
* 用 ``__file__`` 定位脚本自己的文件，相对路径会落到宿主的进程工作目录；
* 事件是旁路且可丢的，只用来做通知与统计，不要用它传递必须到达的结果。
"""

import os

from jellyfish_sdk import ScriptError, ToolResult, command, contributes, subscribe, tool

#: 脚本自己的目录：脚本可能从任何工作目录被拉起，相对路径会落到进程的 cwd
HERE = os.path.dirname(os.path.abspath(__file__))

#: 便签文件（示例：往脚本自己的目录里写东西）
NOTES = os.path.join(HERE, "notes.txt")

#: 见过多少次工具执行结束；worker 是单线程的，因此这个计数器不需要加锁
SEEN = {"count": 0}


def _note_count():
    """数一数便签里有几行。

    :return: 非空行数
    """
    if not os.path.exists(NOTES):
        return 0
    with open(NOTES, "r", encoding="utf-8") as handle:
        return len([line for line in handle.read().splitlines() if line.strip()])


@tool(
    name="my_hello",
    description="按名字打招呼（示例工具）",
    parameters={
        "name": {"type": "string", "description": "要打招呼的人"},
    },
    required=["name"],
)
def my_hello(args, ctx):
    """按名字打招呼。

    这里**没有** ``read_only`` 参数：哪些工具在 plan 模式下可用完全由用户在
    ``plugins.configurations.jellyfish-plugin-plan.readOnlyTools`` 里决定，脚本无法自称只读。
    """
    name = (args.get("name") or "").strip()
    if not name:
        # 用抛异常表达失败：返回 {"error": ...} 会被当作正常输出回灌给模型
        raise ScriptError("缺少参数 name")
    return ToolResult("你好，%s！" % name,
                      summary="问候了 %s（便签 %d 条）" % (name, _note_count()))


@command(name="myhello", summary="和示例脚本打个招呼", usage="/myhello <名字>",
         aliases=["mh"], session_required=False)
def myhello(tokens, raw, ctx):
    """``/myhello <名字>``，别名 ``/mh``。

    ``session_required=False`` 是显式声明「本命令不依赖会话」——缺省是 ``True``（保守）：
    一条依赖会话的命令在没有会话的界面里被当成对话发给模型，是更坏的默认。
    """
    who = tokens[0] if tokens else "世界"
    return "你好，%s！" % who


@contributes("prompt")
def prompt(ctx):
    """往 system prompt 里加一段稳定规则。

    易变的状态不要放这里（那会让请求前缀每次都变、整段历史重新计费），要放就放
    ``@contributes("turn_context")`` ——它随本轮用户消息送达。
    """
    return "调用 my_hello 时请把用户的名字原样传进去。"


@subscribe("ToolCallCompletedEvent")
def on_tool_completed(event, ctx):
    """订阅一条通知：事件投影只带标量字段，处理器没有返回值。"""
    SEEN["count"] += 1
