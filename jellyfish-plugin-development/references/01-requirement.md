# ① 需求分析 与 ② 选型

这两阶段只产出两张纸：**能力清单**与**选型结论**。看起来像「还没开始写代码」，实际上它们决定了后面
所有返工：扩展点选错要么写不出来（脚本做不到的点），要么做完发现模型根本调不到（清单没写对）。

## ① 需求分析：把一句话翻成能落地的能力清单

用户说的是「加个能查 A 股行情的工具」这类一句话，你要拆成下面四个问题，每个能力都答一遍：

1. **谁触发**——模型自己决定调用（工具）？人敲出来的（命令 / 输入标记 / 快捷键）？还是内核走到某一步时问插件（权限、提示词、落盘）？
2. **什么时候**——每次工具调用、每轮对话、每帧渲染、启动期、会话关闭时？这决定线程与性能约束。
3. **要拿到什么**——只读数据？有副作用的写入？要给模型看一段文本，还是给界面看一行状态？
4. **失败了怎么办**——回灌给模型看（抛异常）、还是静默降级（不表态）？**这一条决定返回值怎么写**。

产出写成一张表：

```
| 能力 | 谁触发 | 命中扩展点 | 失败语义 | 备注 |
| 查行情 | 模型 | tool: stock_quote | 抛错（模型看到原因） | 需要网络，能超时 |
| /panel 开关 | 用户 | command: panel | 返回 ERROR 文本 | 需要会话 |
```

**做完这一步再往下走**：如果某项能力的「谁触发」答不出来，说明需求还没读懂，回去问用户。

## 需求 → 扩展点映射表

一个需求通常能落到好几个点上，选**最贴近触发者**的那一个：模型要用的能力就是工具，人敲的就是命令，
不要用「命令 + 提示词」去模拟工具。

### 模型面（模型能调用的能力）

| 想要的效果 | 扩展点（Java 请求类，脚本 `type`） | 注册 | 关键约束 |
|---|---|---|---|
| 模型能调用一个新工具 | `ToolCallRequest`，`tool` | `handle`（路由键 = **工具名**）+ `ToolDescriptor` | 工具名全局唯一；结果正文首行写结论；失败**抛异常** |
| 某些情况下把某工具从清单里拿掉 | `ToolActivationRequest`，`tool_activation` | `contribute` | 每轮组装清单都会被问；抛异常按「保持可见」 |
| 改写模型给的参数 | `ToolArgumentPreRequest`，`tool_argument_pre` | `contribute` | 链式；发生在**权限判定之前**，不能拿它绕过审批 |
| 整形工具结果 | `ToolResultPostRequest`，`tool_result_post` | `contribute` | 链式；在**截断与落盘之前**，否则内容会与落盘副本分叉 |
| 工具行的渲染样式 | `ToolRenderHintRequest` | `handle`（路由键 = 工具名） | **只能 Java**：跑在渲染线程，脚本的进程往返不可接受 |

### 用户面（人敲出来的东西）

| 想要的效果 | 扩展点 | 注册 | 关键约束 |
|---|---|---|---|
| 一条命令 | `CommandRequest`，`command` | `handle`（路由键 = **命令名**）+ `CommandDescriptor` | `sessionRequired` 缺省 `true`（保守）；理由见下 |
| 命令的二级选择页（候选） | `CommandOptionRequest`，`command_options`（或清单里的 `hasOptions`） | `handle` | 候选查询那次必须只读且快；**那次 `tokens` 是 `None`** |
| `!` `@` 这类输入标记 | `InputDirectiveRequest`，`input_directive` | `handle`（路由键 = **标记字符**） | 只声明「该当成哪次工具调用」，执行走内核完整权限链 |
| 输入框补全（如 `@文件`） | `InputReferenceRequest` | `handle`（路由键 = 标记字符） | **只能 Java**：每帧可能问一次，慢实现会卡住整个界面 |
| 用户回车后改写原文 | `InputTransformRequest`，`input_transform` | `contribute` | 链式；可 `handled` 接过去不进对话 |
| 快捷键 | `ShortcutContributionRequest` | `contribute` | **只能 Java**：外壳收集键位表是启动期动作 |
| 常驻面板 | `PanelContributionRequest`，`panel` | `contribute` | 每插件至多一块；**渲染线程，纯只读、必须快、不得发 `UiInvalidatedEvent`** |
| 状态栏片段 | `StatusLineContributionRequest`，`status_line` | `contribute` | 同上，每插件至多一段 |

### 内核流程面（拦 / 改 / 存 / 供）

| 想要的效果 | 扩展点 | 注册 | 关键约束 |
|---|---|---|---|
| 拦某些工具调用 | `PermissionCheckRequest`，`permission` | `contribute` | 只能收紧（`deny` / `ask`，**没有 allow**）；抛异常按拒绝 |
| 往 system prompt 加一段 | `PromptContributionRequest`，`prompt` | `contribute` | 进**可缓存前缀**：放稳定的规则，别放每轮都变的状态 |
| 每轮随用户消息送达的即时状态 | `TurnContextRequest`，`turn_context` | `contribute` | 易变状态放这里，别放上面那一格 |
| 回合开始前拦下 / 改写本轮输入 | `TurnBeforeRequest`，`turn_before` | `contribute` | 嵌套（子代理）回合忽略「改写输入」 |
| 会话落盘 / 恢复 / 删除 | `SessionPersistRequest` / `SessionRestoreRequest` / `SessionDeleteRequest`，`session_persist` / `session_restore` / `session_delete` | `contribute` | **落盘与删除的异常会上抛**（= 操作失败）；恢复失败只跳过自己 |
| 会话关闭前 / 分支前的放行判定 | `SessionBeforeCloseRequest` / `SessionBeforeForkRequest`，`session_before_close` / `session_before_fork` | `contribute` | 只能拦，不能放行之外地干预 |
| 压缩策略（压成什么样） | `CompactionStrategyRequest`，`compaction` | `contribute` | 逐字段「表态」，不表态的字段回落内核配置 |
| 这次压缩要不要做 | `CompactionPreRequest`，`compaction_pre` | `contribute` | `cancel` 立即短路 |
| 出站请求的缓存参数 | `RequestTuningRequest`，`request_tuning` | `contribute` | **热路径**：每次组装请求都问；脚本侧不冷启动 + 2 秒截止 |
| 较早工具结果的老化策略 | `AgingStrategyRequest`，`aging_strategy` | `contribute` | **热路径**，同上 |
| 接一个自建模型服务 | `ProviderRegistrationRequest` | `handle`（路由键 = **provider 类型**） | **只能 Java**：要返回一个带流式回调的 Java 对象 |
| 补全模型清单 | `ModelCatalogRequest`，`model_catalog` | `handle`（路由键 = **provider 名**） | 脚本必须用 `handler` 声明；空列表 = 「不表态」 |
| 存一点属于自己的会话内状态 | `PluginContext.putExtensionEntry` / `removeExtensionEntry` / `extensionEntries` | — | **只有 Java 有**（脚本 SDK 未暴露）；随会话落盘、不进模型上下文；单条 64 KiB、每会话 64 条 |
| 给外壳推一句通知 / 说「我脏了」 | `PluginContext.present` + 发布 `PluginNotificationEvent` | — | 展示数据、**可丢**（满了丢最新），不能当失败去重试 |
| 知道外面发生了什么 | `PluginContext.observe` / 脚本 `subscribe` | — | 通知是旁路、可丢；要可靠投递就用工具返回值 |

**「谁触发」决定线程**：凡是标注「渲染线程」的点（面板、状态栏、别名补全、渲染提示、输入标记解析）
都**不得做 IO、不得阻塞、不得发 `UiInvalidatedEvent`**（会形成「失效 → 收集 → 失效」死循环）。
联网取数这类慢活要拆到另一个插件/脚本里（官方范例：`stock` 取数 + `stockpanel` 只读缓存画面板）。

## ② 选型：Java 插件还是脚本插件

### 判据（按顺序问自己）

| 需求里有没有这一条 | 结论 |
|---|---|
| 要用渲染线程 / 启动期的扩展点（`ToolRenderHintRequest`、`InputReferenceRequest`、`ShortcutContributionRequest`） | **只能 Java** |
| 要返回 Java 对象（`ProviderRegistrationRequest` 给 `LlmTransport`） | **只能 Java** |
| 要用 `PluginContext` 的 Java 侧能力（会话扩展条目、`submit(PluginAction)`、`askUser()`、子代理委派） | **只能 Java** |
| 要用热路径扩展点（`request_tuning` / `aging_strategy`），且要求冷启动也生效 | **Java**（脚本对它们不冷启动，只提供这两个的脚本永远不会被拉起） |
| 要复用 Python / Node 生态（`akshare`、`playwright`、npm 包、现成 SDK） | **脚本** |
| 需要「崩了也只波及自己」「依赖装在插件自己的环境里」 | **脚本**（每脚本一个 worker 进程） |
| 开发机上没有 JDK / Maven，或希望改实现不用重新打包 | **脚本** |
| 以上都不占 | **默认脚本**：交付物是两个文件，代价最小 |

### 代价对比

| | Java 插件 | 脚本插件（Python / Node） |
|---|---|---|
| 交付物 | 一个 PF4J jar（`plugin.properties` + 插件类） | 一个脚本目录（`manifest.json` + 入口） |
| 装载时机 | 内核启动期全部装载 | 启动期只读清单；**首次调用才起进程**，空闲自毁 |
| 崩溃影响 | 与内核同进程 | 只让该脚本的调用失败，冷却后自动半开 |
| 依赖 | 必须 shade 进 jar，且**不能含 api** | 装在脚本自己的环境里 |
| 扩展点覆盖 | 全部 | 能力档：`in` 的那一批；**4 类明确不做**（见下） |
| 改一行实现 | 重新打包 → 拷 jar → 重启进程 | 改文件即可；等那只 worker 空闲回收（或让进程重启）后再调用生效 |
| 改清单 / 描述符 | 要重新打包（描述符在 jar 里） | 改 `manifest.json` 要重启进程（清单在插件启动期读入） |
| 单测 | JUnit5 + Mockito，可跑真实的注册表与插件管理器 | 无框架级单测；靠 `dump_manifest --check` 与真跑 |

### 做不到的边界（要在这个阶段就说清，别拖到实现时才发现）

**脚本插件明确不做的四类**（真源：桥接插件的 `script/extension-points.json`）：

| 扩展点 | 为什么不做 |
|---|---|
| `ProviderRegistrationRequest` | 结构上做不到：要返回一个带流式回调的 Java 对象，不是数据载荷 |
| `ToolRenderHintRequest` | 渲染线程内联执行（一卡整个界面都不动），脚本一次进程往返不可接受 |
| `InputReferenceRequest` | 输入框补全，慢实现直接卡住界面 |
| `ShortcutContributionRequest` | 外壳收集键位表是启动期动作，与「启动期零进程」冲突 |

**两类插件都动不了的**：

- **拿不到会话与工作目录**：`PluginContext` 没有「列出 / 新建会话」的入口，`RuntimeInfo` 刻意不含
  `sessionId` / `agentId` / `cwd`；工具的相对路径按**进程工作目录**解析。
- **起不了回合、停不了回合**：插件不能新开会话、不能起回合，中止回合是用户主权；Java 侧最多
  `submit(PluginAction)` 投五种动作（`SEND_USER_MESSAGE` / `COMPACT` / `SWITCH_MODEL` / `FORK_SESSION` /
  `REBUILD_TOOL_CATALOG`），脚本侧连这个都没有。
- **造不了界面组件**（子优先类加载器），只能给「外壳渲染的数据」。
- **不能自称只读**：`ToolDescriptor` 里没有该字段，谁能进 plan 名单由用户配置说了算。
- **改不了内核既有流程**：只能注册扩展点（红线 2）。

需求撞上以上任何一条时，**停下来说清**：哪个能力做不到、机制上为什么、替代方案是什么
（换扩展点 / 拆成两个插件 / 只做其中一部分 / 让用户改配置）。

## 两个走完① ② 的例子

**例 1：「让模型能查我们内网的部署状态」**

① 能力清单：模型触发；只读 HTTP 调用；失败要把真实原因给模型看（抛错）。→ 命中 `tool`。
② 选型：要调内网 API、要用 `requests` 与现成的签名 SDK；没有任何 Java 独占项 → **Python 脚本插件**。
代价：首次调用才起进程（几十毫秒）；崩了只影响这个脚本。

**例 2：「在侧栏常驻显示当前 git 状态」**

① 能力清单：内核每帧（缓存失效时）问一次；只读；要快。→ 命中 `panel`。
② 选型：面板处理器在渲染线程，不能跑 `git status` 这种子进程；但**只读文件**很快 → 可行，但要
「先算好、面板只读内存」。用哪门语言？两者都行，脚本更省事 → **Python 脚本插件**；
若还要在输入框补全分支名（`InputReferenceRequest`）→ 只能 **Java**（脚本不做）。
这条例子里最容易踩的是：把 `git` 子进程放进面板处理器 → 界面卡死。

**例 3：「禁止模型碰 `/etc` 下的文件」**

① 能力清单：内核在每次工具调用前问；只收紧；判不出来时按拒绝。→ 命中 `permission`。
② 选型：逻辑是路径前缀判定，纯计算 → 两者皆可 → **Python 脚本插件**够用；
但要注意「抛异常 = 拒绝」这条 fail-closed 语义，别把「读配置失败」当成放行（见 `05-pitfalls.md`）。
