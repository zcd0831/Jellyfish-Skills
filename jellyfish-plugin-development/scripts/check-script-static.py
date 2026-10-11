#!/usr/bin/env python3
"""脚本插件清单的静态体检（不需要解释器、不需要联网）。

它是 ``check-script.sh`` 的一部分，也可以单独跑：
    python3 check-script-static.py <脚本目录>

校验的依据是内核桥接层的清单解析器（``jellyfish-script`` 的 ``ScriptManifest``），
因此这里列出的是那份解析器**逐条都在校验**的东西：未知键、必填缺失、类型不对、重复、越界。

两处刻意不重复实现（它们有权威实现，别在这里再写一份）：
  * **清单与实现是否一致** —— 那是 ``dump_manifest --check`` 的活（真源在 SDK 的声明表里）；
  * **可订阅事件的完整白名单** —— 真源在内核的 ``ScriptEventCatalog`` 里。

退出码：0 = 通过（可能有警告）；1 = 有错误；2 = 用法问题。
"""

import json
import os
import re
import sys

# 与 jellyfish-script 的 ScriptManifest.java 保持一致（该文件里的 TOP_KEYS / TOOL_KEYS /
# COMMAND_KEYS / DESCRIPTOR_KEYS / COMMAND_OPTION_KEYS / HANDLER_KEYS / SCHEDULE_KEYS）。
TOP_KEYS = {"id", "entry", "tools", "commands", "commandOptions",
            "contributions", "events", "handlers", "schedules"}
TOOL_KEYS = {"name", "description", "parameters", "required"}
COMMAND_KEYS = {"name", "descriptor", "hasOptions"}
DESCRIPTOR_KEYS = {"summary", "usage", "aliases", "sessionRequired"}
COMMAND_OPTION_KEYS = {"name"}
HANDLER_KEYS = {"type", "route"}
SCHEDULE_KEYS = {"name", "intervalSeconds"}

# 在清单里有专用字段的路由键类型：不能再写进 handlers
DEDICATED_ROUTE_TYPES = {"tool", "command", "command_options"}

# 可以用 handlers 声明的带路由键类型（路由键来自用户配置的那些）
ROUTED_VIA_HANDLERS = {"model_catalog", "input_directive"}

# 类型级扩展点：只能写进 contributions（真源：jellyfish-script 的 ExtensionCodecs.defaults）
TYPE_LEVEL_CONTRIBUTIONS = {
    "prompt", "status_line", "panel", "permission", "session_persist", "session_restore",
    "session_delete", "compaction", "tool_result_post", "tool_argument_pre", "turn_context",
    "session_before_close", "session_before_fork", "compaction_pre", "tool_activation",
    "request_tuning", "aging_strategy", "input_transform", "turn_before",
}

ID_PATTERN = re.compile(r"^[^\s/\\]+$")
MIN_INTERVAL_SECONDS = 1
DEFAULT_INTERVAL_SECONDS = 5

errors = []
warnings = []


def err(message):
    errors.append(message)


def warn(message):
    warnings.append(message)


def check_types(value, expected, where):
    """类型不对就记一条错误（与内核解析器同口径：类型不对一律报错，不静默容忍）。"""
    if not isinstance(value, expected):
        names = expected if isinstance(expected, tuple) else (expected,)
        wanted = " / ".join(t.__name__ for t in names)
        err("%s 必须是 %s，实际是 %s" % (where, wanted, type(value).__name__))
        return False
    return True


def check_unknown_keys(node, allowed, where):
    unknown = sorted(set(node) - allowed)
    if unknown:
        err("%s 含未知键 %s（允许: %s）" % (where, unknown, sorted(allowed)))


def check_string_list(value, where):
    """字符串数组：元素必须是非空字符串。"""
    if not isinstance(value, list):
        err("%s 必须是数组" % where)
        return []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            err("%s[%d] 必须是非空字符串" % (where, index))
    return [item for item in value if isinstance(item, str)]


def check_entry(script_dir, entry):
    if not isinstance(entry, str) or not entry.strip():
        err("entry 是非空字符串，必须提供（它指向入口文件）")
        return
    if os.path.isabs(entry):
        err("entry 不能是绝对路径: %s" % entry)
        return
    normalized = os.path.normpath(entry)
    if normalized.startswith(".." + os.sep) or normalized == "..":
        err("entry 不能用 .. 跳出脚本目录: %s" % entry)
        return
    if not os.path.isfile(os.path.join(script_dir, entry)):
        err("entry 指向的文件不存在: %s" % os.path.join(script_dir, entry))


def check_tools(manifest):
    tools = manifest.get("tools")
    if tools is None:
        return
    if not isinstance(tools, list):
        err("tools 必须是数组")
        return
    seen = set()
    for index, tool in enumerate(tools):
        where = "tools[%d]" % index
        if not isinstance(tool, dict):
            err("%s 必须是 JSON 对象" % where)
            continue
        check_unknown_keys(tool, TOOL_KEYS, where)
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            err("%s 的 name 是非空字符串，必须提供" % where)
        elif name in seen:
            err("%s 工具名重复: %s" % (where, name))
        else:
            seen.add(name)
        description = tool.get("description")
        if description is not None and not isinstance(description, str):
            err("%s.description 必须是字符串" % where)
        parameters = tool.get("parameters")
        if parameters is not None and not isinstance(parameters, dict):
            err("%s.parameters 必须是 JSON 对象（JSON Schema 的 properties 部分）" % where)
        if tool.get("required") is not None:
            check_string_list(tool.get("required"), where + ".required")
    return seen


def check_commands(manifest):
    commands = manifest.get("commands")
    if commands is None:
        return set(), set()
    if not isinstance(commands, list):
        err("commands 必须是数组")
        return set(), set()
    declared = set()
    implied_options = set()
    for index, command in enumerate(commands):
        where = "commands[%d]" % index
        if not isinstance(command, dict):
            err("%s 必须是 JSON 对象" % where)
            continue
        check_unknown_keys(command, COMMAND_KEYS, where)
        name = command.get("name")
        if not isinstance(name, str) or not name.strip():
            err("%s 的 name 是非空字符串，必须提供" % where)
            continue
        if name in declared:
            err("%s 命令名重复: %s" % (where, name))
        declared.add(name)
        if command.get("hasOptions") is not None and not isinstance(command.get("hasOptions"), bool):
            err("%s.hasOptions 必须是布尔值" % where)
        if command.get("hasOptions") is True:
            implied_options.add(name)
        descriptor = command.get("descriptor")
        if descriptor is None:
            continue
        if not isinstance(descriptor, dict):
            err("%s.descriptor 必须是 JSON 对象" % where)
            continue
        check_unknown_keys(descriptor, DESCRIPTOR_KEYS, "commands[%d].descriptor" % index)
        for key in ("summary", "usage"):
            if descriptor.get(key) is not None and not isinstance(descriptor.get(key), str):
                err("commands[%d].descriptor.%s 必须是字符串" % (index, key))
        if descriptor.get("aliases") is not None:
            aliases = check_string_list(descriptor.get("aliases"), "commands[%d].descriptor.aliases" % index)
            for alias in aliases:
                if alias.startswith("/"):
                    err("别名不能以 / 开头（输入阶段已把前缀剥掉，带了就是永不命中的死别名）: %s" % alias)
        if descriptor.get("sessionRequired") is not None \
                and not isinstance(descriptor.get("sessionRequired"), bool):
            err("commands[%d].descriptor.sessionRequired 必须是布尔值" % index)
    return declared, implied_options


def check_command_options(manifest, declared, implied_options):
    options = manifest.get("commandOptions")
    if options is None:
        return
    if not isinstance(options, list):
        err("commandOptions 必须是数组")
        return
    seen = set()
    for index, option in enumerate(options):
        where = "commandOptions[%d]" % index
        if not isinstance(option, dict):
            err("%s 必须是 JSON 对象" % where)
            continue
        check_unknown_keys(option, COMMAND_OPTION_KEYS, where)
        name = option.get("name")
        if not isinstance(name, str) or not name.strip():
            err("%s 的 name 是非空字符串，必须提供" % where)
            continue
        if name in seen:
            err("%s 命令名重复: %s" % (where, name))
        seen.add(name)
        if name not in declared:
            err("%s 候选查询挂在未声明的命令上: %s" % (where, name))
        elif name in implied_options:
            err("%s 与 commands 的 hasOptions 重复声明同一命令: %s" % (where, name))


def check_contributions(manifest):
    contributions = manifest.get("contributions")
    if contributions is None:
        return
    for name in check_string_list(contributions, "contributions"):
        if name in ROUTED_VIA_HANDLERS or name in DEDICATED_ROUTE_TYPES:
            err("contributions 只接受类型级扩展点，%s 带路由键，应写进 tools / commands / "
                "commandOptions / handlers" % name)
        elif name not in TYPE_LEVEL_CONTRIBUTIONS:
            err("contributions 含未知扩展点: %s（已知: %s）"
                % (name, sorted(TYPE_LEVEL_CONTRIBUTIONS)))


def check_events(manifest):
    events = manifest.get("events")
    if events is None:
        return
    check_string_list(events, "events")
    warn("events 已声明；可订阅事件的完整白名单由内核决定（写错会在插件启动期报错），"
         "本脚本不做重复实现")


def check_handlers(manifest):
    handlers = manifest.get("handlers")
    if handlers is None:
        return
    if not isinstance(handlers, list):
        err("handlers 必须是数组")
        return
    seen = set()
    for index, handler in enumerate(handlers):
        where = "handlers[%d]" % index
        if not isinstance(handler, dict):
            err("%s 必须是 JSON 对象" % where)
            continue
        check_unknown_keys(handler, HANDLER_KEYS, where)
        type_name = handler.get("type")
        route = handler.get("route")
        if not isinstance(type_name, str) or not type_name.strip():
            err("%s 的 type 是非空字符串，必须提供" % where)
            continue
        if not isinstance(route, str) or not route.strip():
            err("%s 的 route 是非空字符串，必须提供" % where)
            continue
        if type_name in DEDICATED_ROUTE_TYPES:
            err("%s 的 %s 在清单里有专用字段，请写在 tools / commands / commandOptions 里"
                % (where, type_name))
        elif type_name in TYPE_LEVEL_CONTRIBUTIONS:
            err("%s 的 %s 是类型级扩展点，应写进 contributions" % (where, type_name))
        elif type_name not in ROUTED_VIA_HANDLERS:
            err("%s 含未知扩展点: %s（可走 handlers 的: %s）"
                % (where, type_name, sorted(ROUTED_VIA_HANDLERS)))
        key = "%s::%s" % (type_name, route)
        if key in seen:
            err("%s 重复声明: %s" % (where, key))
        seen.add(key)


def check_schedules(manifest):
    schedules = manifest.get("schedules")
    if schedules is None:
        return
    if not isinstance(schedules, list):
        err("schedules 必须是数组")
        return
    seen = set()
    for index, schedule in enumerate(schedules):
        where = "schedules[%d]" % index
        if not isinstance(schedule, dict):
            err("%s 必须是 JSON 对象" % where)
            continue
        check_unknown_keys(schedule, SCHEDULE_KEYS, where)
        name = schedule.get("name")
        if not isinstance(name, str) or not name.strip():
            err("%s 的 name 是非空字符串，必须提供" % where)
        elif name in seen:
            err("%s 重复声明: %s" % (where, name))
        else:
            seen.add(name)
        interval = schedule.get("intervalSeconds")
        if interval is None:
            continue
        if isinstance(interval, bool) or not isinstance(interval, int):
            err("%s 的 intervalSeconds 必须是整数秒（缺省 %d）" % (where, DEFAULT_INTERVAL_SECONDS))
        elif interval < MIN_INTERVAL_SECONDS:
            err("%s 的 intervalSeconds 不能小于 %d 秒（实际 %d）"
                % (where, MIN_INTERVAL_SECONDS, interval))


def main(argv):
    if len(argv) != 2:
        print("用法: python3 check-script-static.py <脚本目录>")
        return 2

    script_dir = argv[1]
    if not os.path.isdir(script_dir):
        print("ERROR: 不是目录: %s" % script_dir)
        return 2

    manifest_path = os.path.join(script_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print("ERROR: 目录里没有 manifest.json（宿主认识这个脚本的唯一起点）: %s" % manifest_path)
        return 1

    size = os.path.getsize(manifest_path)
    if size > 1024 * 1024:
        err("清单文件过大（%d 字节，上限 1048576 字节）" % size)

    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except ValueError as failure:
        print("ERROR: 清单不是合法 JSON: %s" % failure)
        return 1

    if not isinstance(manifest, dict):
        print("ERROR: 清单必须是 JSON 对象")
        return 1

    check_unknown_keys(manifest, TOP_KEYS, "清单")
    check_entry(script_dir, manifest.get("entry"))

    # id 缺省取目录名，因此两种情况都要能过
    declared_id = manifest.get("id")
    effective_id = declared_id if isinstance(declared_id, str) and declared_id.strip() \
        else os.path.basename(os.path.abspath(script_dir))
    if not ID_PATTERN.match(effective_id) or "::" in effective_id:
        err("脚本 id 非法: %s（不能含空白、/、\\ 或 ::）" % effective_id)

    check_tools(manifest)
    declared_commands, implied_options = check_commands(manifest)
    check_command_options(manifest, declared_commands, implied_options)
    check_contributions(manifest)
    check_events(manifest)
    check_handlers(manifest)
    check_schedules(manifest)

    print("== 清单静态体检: %s ==" % manifest_path)
    print("-- 脚本 id: %s" % effective_id)
    for message in warnings:
        print("WARN : %s" % message)
    for message in errors:
        print("ERROR: %s" % message)
    if errors:
        print("结果: 失败（%d 条错误）—— 宿主解析这份清单时会拒绝加载该脚本" % len(errors))
        return 1
    print("结果: 通过（%d 条警告）" % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
