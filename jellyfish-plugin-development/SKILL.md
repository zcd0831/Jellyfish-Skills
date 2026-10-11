---
name: jellyfish-plugin-development
description: 从一句需求做到一个能装的 Jellyfish 插件：先把需求翻成「模型面 / 用户面 / 内核面」并映射到现有扩展点，再在 Java 插件与 Python/Node 脚本插件之间定选型，然后按对应工序写代码、单测、打包安装并真跑一遍验收。适用场景：用户说「给 jellyfish 加个能力 / 加个工具 / 加个命令 / 写个插件」时需要判断用哪种插件实现、并把它做完。
---

# Jellyfish 插件开发：从需求到可安装的插件

一套工序，产出是**一个能装进 jellyfish、模型或用户真能用上的插件**——Java 插件（PF4J jar）或
Python / Node 脚本插件（一个脚本目录 + `manifest.json`），二者择一。

工序分四阶段，**顺序不能颠倒**：

```
① 需求分析 ──→ ② 选型 ──→ ③ 实现 ──→ ④ 验收
翻成三个面      Java / 脚本   工程与骨架    真跑 + 回读
出「能力清单」  出「选型结论」 出代码与单测  出验收结论
      │              │            │            │
      └── 落不到现有扩展点 ── 停下说清，不改内核 ──┘
```

**「先决定用哪种插件」不是建议而是工序里的第②步**：选型没落定就动手，代价是一整轮返工
（Java 插件要建 Maven 工程、脚本只要两个文件，走错一条等于把简单的事做复杂）。

## 什么时候用 / 不用

**用**：要给 jellyfish 添一个新能力——一个工具、一条命令、一块面板、一条权限规则、一种持久化/压缩策略……

**不用**：

| 你的目标 | 该用的做法 |
|---|---|
| 只是想配置已有插件（换路径、开白名单） | 改 `jellyfish.json` 的 `plugins.configurations`，不写代码 |
| 想接一个现成的 MCP server | 装 MCP 插件并配 server，不写代码 |
| 想改内核行为本身（ReAct 循环、会话结构） | 这不是插件的事——插件只能注册扩展点，见下面红线 2 |
| 想给某个 skill 加内容 | 那是 `SKILL.md`，与插件无关 |

## 四阶段工序

| 阶段 | 目标 | 产出（下一阶段的输入） | 详细做法 |
|---|---|---|---|
| ① 需求分析 | 把用户的一句话翻成能落地的能力清单 | **能力清单**：每个能力写明「谁触发 / 要什么 / 命中哪个扩展点」 | `references/01-requirement.md` |
| ② 选型 | 在 Java 与脚本之间定一个 | **选型结论**：哪种插件 + 理由 + 已知代价 | `references/01-requirement.md` |
| ③ 实现 | 工程、骨架、注册、配置、单测 | 可打包的插件 | `references/02-java-plugin.md` / `references/03-script-plugin.md` |
| ④ 验收 | 证明它真的能用 | 验收记录：装上了、调通了、失败模式可解释 | `references/04-verification.md` |

**逐阶段的验收点**（不通过不要往下走）：

- ① → ②：能不能说清「这个能力被谁在什么时候触发」？说不清就是需求还没读懂。
- ② → ③：选型结论有没有正面回答「为什么不选另一个」？答不上来多半是没看判据表。
- ③ → ④：`mvn -q test` / `dump_manifest --check` 是否为绿？测试没跑过不算写完。
- ④：**装上去、重启、真调一次**——「编译通过、单测绿」不等于「模型调得到」。

## 五条红线

1. **选型先落定，再动代码**。类型、扩展点清单、交付形态先写清楚并与用户确认（多个方案都说得通时逐个列给用户挑）。
2. **只注册、不改内核**。插件只能注册 `jellyfish-api` 里已有的扩展点。需求落不到任何现有扩展点，
   就停下来说明「哪个能力做不到、为什么、退化方案是什么」，**不要新增扩展点、不要改内核**。
   脚本侧明确不做的那几类扩展点见 `references/01-requirement.md` 的「做不到的边界」。
3. **`jellyfish-api` 永远 `provided`**。插件 jar 里不许出现 `zcd/jellyfish/api/` 或 `org/pf4j/` 的类，
   shade 的 `includes` 里也不许出现——自带 api 会遮蔽父加载器里那一份，内核加字段时**静默丢失**，
   内核加载期会直接拒绝这种 jar。装之前用 `scripts/check-plugin-jar.sh` 体检一次。
4. **清单与实现不许漂移**（脚本插件）。工具的描述与参数**只在 `manifest.json` 里**决定模型看到什么，
   而实现的事实写在装饰器里；两者不一致脚本会拒绝服务。改完脚本必须
   `dump_manifest.py --write`（或 `--check`）。
5. **不臆造 API**。仓库 README 与示例可能落后于代码（已知一处：README 的 `ToolDescriptor` 骨架签名是旧的），
   一切签名以 `jellyfish-api` 源码 / SDK 源码为准；拿不准就用 `scripts/` 里的体检脚本与编译验证。

## 交付前必须过的门槛

```bash
# Java 插件
mvn -q clean package                 # 必须 clean：增量编译会把「编译不过」伪装成运行期报错
sh <skill>/scripts/check-plugin-jar.sh target/<artifact>-<version>.jar

# 脚本插件（python 为例；node 换成 node/dump_manifest.js）
sh <skill>/scripts/check-script.sh ./my-script          # 静态体检
python3 ~/.jellyfish/gateway/python/<digest>/script/dump_manifest.py ./my-script --check
```

**「看起来没问题」不算通过**：脚本必须真跑出退出码 0，插件必须真装上并被调用一次（见
`references/04-verification.md`）。安装与重启会动用户的 `~/.jellyfish`，**动手前先征得用户同意**。

## 附带文件导航

正文只写主干。需要细节时按下表取用——不要一次全读。

| 文件 | 什么时候读它 |
|---|---|
| `references/01-requirement.md` | 阶段①②：需求 → 扩展点映射表、Java/脚本选型判据、做不到的边界 |
| `references/02-java-plugin.md` | 阶段③④：写 Java 插件（工程配置、注册、配置段、单测、打包安装、调试） |
| `references/03-script-plugin.md` | 阶段③④：写脚本插件（manifest 规格、两门语言 SDK、目录与配置、验证工序） |
| `references/04-verification.md` | 阶段④：验收清单与自检脚本用法、真跑一遍的步骤 |
| `references/05-pitfalls.md` | 遇到诡异现象、或准备交付之前 |
| `templates/java-plugin/` | 从零起一个 Java 插件工程时整目录拷走 |
| `templates/script-python/` `templates/script-node/` | 从零写一个脚本插件时拷贝，`manifest.json` 与入口一起改 |
| `templates/README.md` | 每份模板「拷完要替换什么」的清单 |
| `scripts/check-plugin-jar.sh` | 体检插件 jar：描述符键、自带 api/pf4j、shade 污染 |
| `scripts/check-script.sh` | 体检脚本目录：清单静态校验 + 调用官方 `dump_manifest --check` |
| `scripts/check-script-static.py` | 上一行调用的静态校验器（也可单独跑） |

## 复用优先于重建

**先看仓库里有没有同类插件**，照它写：同一个仓库里的插件就是最好的范例（工具、命令、面板、权限各有一份现成实现）。
本技能的 `templates/` 是**参考实现**：目标是「从零起一个」，或者「已有插件明显更烂」时才拷。

改的是**官方插件仓库**里的插件时，除了本技能，仓库自己的 `AGENTS.md`（模块边界、编码规范、
`cpPlugins.sh`、内核升级后必跑的三个 `-P*-it`）优先级更高，以它为准。

## 验收标准（Definition of Done）

- [ ] 能力清单里每一项都指明了扩展点与触发者（模型 / 用户 / 内核流程）
- [ ] 选型结论写明了「为什么不是另一种」，并记下所选方案的已知代价
- [ ] Java 插件：`mvn -q clean package` 过；单测覆盖「注册成功」与「返回值正确」；`check-plugin-jar.sh` 退出码 0
- [ ] 脚本插件：`check-script.sh` 与 `dump_manifest --check` 都退出码 0；清单里的描述/参数与声明一致
- [ ] 插件真的装上、进程重启、**真调过一次**（模型调工具 / 敲命令 / 看到面板），并说明怎么看出来的
- [ ] 失败路径解释得清：脚本崩了、依赖没装、配置写错、无审批者的外壳下会发生什么
- [ ] 插件改动涉及工具 / 命令 / 配置字段时，文档（README / 插件自己的说明）一起改了

## 常见坑（完整清单见 `references/05-pitfalls.md`）

1. **README 的骨架代码可能过时**：`ToolDescriptor` 的第 4 个参数是必填参数名列表，不是 `order`。
2. **脚本工具的描述与参数只在清单里**：改代码不改清单 → 模型按旧的签名调用。
3. **热路径扩展点（`request_tuning` / `aging_strategy`）脚本不冷启动**：只提供这两个的脚本永远不会被拉起。
4. **面板 / 状态栏处理器跑在界面渲染线程且没有超时**：联网取数要放到另一个脚本里（示例：`stock` + `stockpanel`）。
5. **权限拦截没有「允许」三态之外的东西**：插件只能收紧；抛异常按拒绝（fail-closed）。
6. **插件生命周期是 fail-closed 的**：`stop()` 之后任何注册、发布都当场失败；后台线程必须在 `stop()` 返回前停掉。
