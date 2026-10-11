# ② ③ 脚本插件：用 Python / Node 写插件

读它之前先读完 `01-requirement.md`，确认选型结论是**脚本插件**，并确认需求没撞上那四类明确不做的扩展点。

> 路径约定：`<plugins>` = 官方插件仓库（`Jellyfish-Plugins`）。机制层是 `<plugins>/jellyfish-script/`，
> 两门语言的桥接插件是 `<plugins>/jellyfish-plugin-python/` 与 `.../jellyfish-plugin-node/`，
> **脚本作者该读的是 `<plugins>/examples/scripts/README.md`（脚本 API 参考）与
> `<plugins>/examples/scripts/{python,node}/{hello,jira}`（可直接拷的示例）**。

## 工序列（六步）

```
① 定语言与目录 ─→ ② 写实现 ─→ ③ 写清单 ─→ ④ 配置段 ─→ ⑤ 自检 ─→ ⑥ 真跑一遍
   python/node     装饰器声明    manifest.json   scripts.<id>  check-script.sh  04-verification.md
   <脚本 id> = 目录名            与实现一致      密钥走这里     + dump_manifest --check
```

## ① 放哪、叫什么

| 事实 | 说明 |
|---|---|
| 脚本根目录 | `scriptsRoot` 缺省 `scripts/python` / `scripts/node`，**相对进程工作目录**解析；配置里可以写成 `~/.jellyfish/scripts/python` |
| 脚本 id | **就是目录名**（清单里的 `id` 缺省取目录名）；配置段与台账都用它 |
| 识别条件 | `scriptsRoot` 的**直接子目录**，且目录里有 `manifest.json`；不含清单的子目录直接跳过 |
| 同 id 冲突 | 两个目录同 id 时后一个被跳过（按名字排序，结果与机器无关） |
| 每脚本一个 worker 进程 | 首次调用才 fork，空闲自毁（缺省 300 秒）；崩了只波及自己，连续失败进熔断冷却 |
| 关掉单个脚本 | **没有逐脚本开关**：去掉它的 `schedules`、把目录移走，或整只桥接插件停用 |

从零开始时把 `templates/script-python/`（或 `script-node/`）整目录拷成一个新目录，改目录名、清单、入口。

## ② 写实现：装饰器声明能力

```python
# main.py —— 目录名就是脚本 id
from jellyfish_sdk import ScriptError, contributes, subscribe, tool, ToolResult

@tool(name="my_ping", description="Ping 一个地址",
      parameters={"host": {"type": "string", "description": "主机名"}},
      required=["host"])
def my_ping(args, ctx):
    """一句话描述（清单里没写 description 时取它的第一行）。"""
    host = args.get("host")
    if not host:
        raise ScriptError("缺少参数 host")      # 失败必须抛，别返回 {"error": ...}
    return ToolResult(do_ping(host), summary="ping 了 %s" % host)
```

```javascript
// main.js（CommonJS；ESM 不在支持范围）
const { ScriptError, tool, ToolResult } = require('jellyfish_sdk');

tool({ name: 'my_ping', description: 'Ping 一个地址',
       parameters: { host: { type: 'string', description: '主机名' } }, required: ['host'] },
     async (params, ctx) => {
         if (!params.args.host) throw new ScriptError('缺少参数 host');
         return new ToolResult(await doPing(params.args.host), { summary: `ping 了 ${params.args.host}` });
     });
```

### 两门语言的 API 对照

| 用途 | Python | Node |
|---|---|---|
| 工具 | `@tool(name, description=None, parameters=None, required=None)`，处理器 `def f(args, ctx)` | `tool({name, description, parameters, required}, (params, ctx) => …)`，参数在 `params.args` |
| 命令 | `@command(name, summary=None, usage=None, aliases=None, has_options=False, session_required=True)`，`def f(tokens, raw, ctx)` | `command({name, summary, usage, aliases, hasOptions, sessionRequired}, (params, ctx) => …)`，用 `params.tokens` / `params.raw` |
| 候选查询（单独函数） | `@command_options("cmd")` | `commandOptions('cmd', fn)` |
| 类型级贡献 | `@contributes("prompt")` | `contributes('prompt', fn)` |
| 事件订阅 | `@subscribe("ToolCallCompletedEvent")` | `subscribe('ToolCallCompletedEvent', fn)` |
| 周期任务 | `@periodic(name, interval_seconds=…)`，`def f(ctx)` | `periodic({name, intervalSeconds}, (params, ctx) => …)` |
| 带路由键的处理器 | `@handler("model_catalog", route="local")` | `handler({type: 'model_catalog', route: 'local'}, fn)` |
| 缺省描述 | 取函数文档字符串第一行 | **必须显式写 `description`**（JS 拿不到注释） |
| 模块格式 | — | CommonJS（入口与 SDK 都用 `require`） |
| 解释器 | `python3`（配置键 `pythonPath`） | `node`（配置键 `nodePath`） |

**`ctx` 里有什么**（Python 下划线 / Node 驼峰）：`script_id`、`session_id`、`parent_session_id`、
`run_id`、`root_run_id`、`agent_id`、`payload`（原始请求副本）、`configuration`、`emit_event(name, payload)`。
**没有**的是：会话列表、工作目录、`askUser`、子代理委派、会话扩展条目——要这些只能 Java 插件。

### 每个扩展点处理器拿到什么、能返回什么

完整表在 `<plugins>/examples/scripts/README.md`；写代码时按下面四条判断就够：

1. **返回值形状**：`None` 通常表示「不表态」（内核按缺省走）；字符串是最短路径（多数点接受 `{"text": ...}` 等价写法）；
   强类型点（权限、工具激活、生命周期）有约定的字典键，写错了不会被识别。
2. **失败**：抛 `ScriptError`。**返回 `{"error": ...}` 会被当成正常输出**回灌给模型，语义静默错位。
3. **事件处理器没有返回值**：事件是通知。
4. **周期任务的「跳过」必须是正常 `return`**：抛异常会被记 WARN 且不发界面失效事件。

### 三条写脚本时最容易踩的

- **用脚本自己的目录定位文件**：Python `os.path.dirname(os.path.abspath(__file__))` / Node `__dirname`。
  相对路径会落到**宿主的工作目录**，不是脚本目录。
- **候选查询那一次 `tokens` 是 `None`**（Node 是 `null`）；`tokens == []` 是「执行且没带参数」，两者不是一回事。
  写成 `has_options=True` 却分不清两条路的函数会在**启动期**被拒绝。
- **不要考虑并发**：worker 单线程，同一脚本的并发调用由网关排队。

## ③ 写清单 `manifest.json`（宿主认识这个脚本的唯一来源）

```json
{
  "entry": "main.py",
  "tools": [
    { "name": "my_ping", "description": "Ping 一个地址",
      "parameters": { "host": { "type": "string", "description": "主机名" } },
      "required": ["host"] }
  ],
  "commands": [
    { "name": "ping", "hasOptions": false,
      "descriptor": { "summary": "Ping 一次", "usage": "/ping <host>", "aliases": [], "sessionRequired": false } }
  ],
  "contributions": ["prompt"],
  "events": ["ToolCallCompletedEvent"]
}
```

| 顶层键 | 必填 | 约束 |
|---|---|---|
| `entry` | **是** | 入口文件，相对脚本目录；**不能是绝对路径、不能靠 `..` 跳出脚本目录**（扫描器还会用真实路径复核符号链接） |
| `id` | 否 | 缺省 = 目录名；不能含空白、`/`、`\`、`::` |
| `tools[]` | 否 | `name` 必填且不重复；`description` / `parameters`（JSON Schema properties）/ `required` 决定**模型看到的工具定义** |
| `commands[]` | 否 | `name` + 可选 `descriptor`（`summary` / `usage` / `aliases` / `sessionRequired`，**`sessionRequired` 缺省 `true`**）+ 可选 `hasOptions`（= 同一命令也回答候选查询） |
| `commandOptions[]` | 否 | `{name}`，必须挂在已声明的命令上，且不能与该命令的 `hasOptions` 重复 |
| `contributions[]` | 否 | 只能写**类型级**扩展点（`prompt`、`status_line`、`panel`、`permission`、`session_persist`、`session_restore`、`session_delete`、`compaction`、`tool_result_post`、`tool_argument_pre`、`turn_context`、`session_before_close`、`session_before_fork`、`compaction_pre`、`tool_activation`、`request_tuning`、`aging_strategy`、`input_transform`、`turn_before`） |
| `events[]` | 否 | 只能写内核**可订阅**的事件名；写错在清单解析期就报错，并把可订阅的名字列出来 |
| `handlers[]` | 否 | `{type, route}`：**只用于「路由键来自用户配置」的点**（`model_catalog` 的 provider 名、`input_directive` 的 `!` `@`）；`tool` / `command` / `command_options` 有专用字段，类型级点要写进 `contributions` |
| `schedules[]` | 否 | `{name, intervalSeconds}`；间隔缺省 5、下限 1，越界报错（不静默抬高） |

**未知键一律报错**（错误里会列出允许的键名）——把 `commands` 写成 `command` 的后果本来是「命令静默消失」。
清单文件上限 1 MiB，单个文本字段上限 8192 字符（超限报错，不截断）。
解析失败只让**这一个脚本** ERROR 跳过，不影响同语言的其它脚本，也不会让桥接插件 FAILED。

**清单与实现必须一致**：worker 冷启动时会比对**名字集合**（工具 / 命令 / 候选 / 贡献 / 事件 / handler / 周期任务），
不一致在缺省 `manifestStrict=true` 下**拒绝服务**（该脚本所有调用失败）。
注意两点：

- 比对**只比名字**，**描述与参数只以清单为准**——清单里写错描述，模型就按错的调，且没有任何报错。
- 因此改完脚本**必须重新生成清单**：

```bash
# 网关资源解包在 ~/.jellyfish/gateway/<语言>/<内容摘要>/script/ 下（首次用到某脚本后才有）
python3 ~/.jellyfish/gateway/python/<digest>/script/dump_manifest.py ./my-script --write
python3 ~/.jellyfish/gateway/python/<digest>/script/dump_manifest.py ./my-script --check   # 退出码 0 才算过
node    ~/.jellyfish/gateway/node/<digest>/script/dump_manifest.js   ./my-script --check
```

`--write` 比 shell 重定向（`> manifest.json`）好：重定向会先把目标文件截空，而生成器要读它确认入口文件名。
`--check` 比整份清单（含描述 / 参数 / `sessionRequired` / 周期任务间隔），比 worker 启动时那次更严。

## ④ 配置段

```json
{
  "plugins": {
    "configurations": {
      "jellyfish-plugin-python": {
        "scriptsRoot": "~/.jellyfish/scripts/python",
        "invokeTimeoutSeconds": 30,
        "scripts": { "my-script": { "apiKey": "${MY_KEY}", "endpoint": "https://…" } }
      }
    }
  }
}
```

脚本里用 `ctx.configuration`（Python 还可用模块级 `configuration()`，注入发生在 import 之前）读到
`scripts.<脚本 id>` 这一段；值对桥接层不透明，写什么都行。

- **密钥只能走配置段**：脚本进程的环境是**严格白名单**（只透传解释器运行与依赖解析必需的几个），
  内核的密钥不会进到脚本里——这是有意的安全取舍。
- **`${ENV}` 是硬失败**：写了 `${SOME_KEY}` 而环境变量没设，进程**启动即失败**。
  不用的密钥就留空字符串，不要写占位符。
- 配置里写了**不存在的脚本 id** → 启动期发一条配置告警（不是错误，但你会想知道）。

## ⑤ 自检

```bash
sh <skill>/scripts/check-script.sh ./my-script                       # 静态体检（清单键、entry、周期任务、脚本 id）
python3 …/dump_manifest.py ./my-script --check                       # 权威一致性检查
```

## ⑥ 真跑一遍

装到 `scriptsRoot` 下、重启进程，然后：**模型能调到工具**、**命令能敲**、**贡献真的出现在界面上**，
并说清怎么看出来的。`/python`、`/node` 是你的排障面板（台账）：

| 行 | 能看出什么 |
|---|---|
| 首行 | 脚本数、已登记能力数 |
| `运行时：` | 网关是否启动（懒加载）、网关与各 worker 的 pid、在途 / 排队请求数 |
| `熔断：` | 每个脚本的熔断状态与剩余冷却时间；从未调用过会写「尚未发生调用」 |
| `事件：` | 推送 N、丢弃 M |
| `问题` | 启动期的清单 / 注册问题逐条列出 |

**改完什么要重启**：改 `manifest.json` → 必须重启进程（清单在桥接插件启动期读入）；
只改入口实现的代码 → 等那只 worker 空闲回收后再调用即生效（拿不准就重启，别猜）。
完整验收清单见 `references/04-verification.md`。

## 官方示例（照抄优先）

| 示例 | 拿它当什么用的 |
|---|---|
| `<plugins>/examples/scripts/python/hello`、`.../node/hello` | 最小可用：一个只读工具 + 一个可写工具 + 一条命令（带别名与候选）+ `prompt` / `status_line` 贡献 + 订阅一个事件 |
| `.../python/jira`、`.../node/jira` | 更接近真实：多个工具（读写分开声明）、命令候选写在单独函数里、`prompt` + `panel`、订阅并发布事件 |
| `.../python/web` | 零第三方依赖的联网搜索 + 网页抓取（含 SSRF 防护），演示「自带配置段 + 外部 HTTP + 结果摘要」 |
| `.../python/stock` + `stockpanel` | 真实形态：取数脚本（有网络、有依赖、有周期任务）与面板脚本**必须拆成两个**——面板跑在渲染线程且没有超时 |

这些示例同时是端到端测试的输入（`mvn -q -Pscript-it test` 会真跑 `hello` / `jira` / `web`），
所以它们不会腐烂——但 `stock` / `stockpanel` 刻意不进 CI（要联网、要 `akshare`），改它们要手动验。
