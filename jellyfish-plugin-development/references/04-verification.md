# ④ 验收：证明它真的能用

验收分三段，**一段都不能省**。第三段是唯一能证明「模型/用户真的用得上」的一段，也最容易被跳过。

```
① 静态检查 ──→ ② 半自动 ──→ ③ 真跑一遍
  脚本体检      编译 + 单测     装上去 → 重启 → 真调一次
  退出码 0      全绿           留下「怎么看出来的」证据
```

## ① 静态检查

```bash
# Java 插件
sh <skill>/scripts/check-plugin-jar.sh target/my-plugin-0.1.0.jar
#   查：plugin.properties 在不在根、必填键齐不齐、jar 里有没有自带 zcd/jellyfish/api 或 org/pf4j
#   退出码 0 才算过；它挡的正是「编译通过、内核静默拒绝加载」那类问题

# 脚本插件
sh <skill>/scripts/check-script.sh ./my-script
#   查：清单顶层键 / entry 是否落在脚本目录内 / 周期任务间隔 / 脚本 id 合法性 / 入口文件是否存在
python3 ~/.jellyfish/gateway/python/<digest>/script/dump_manifest.py ./my-script --check
#   权威一致性检查：清单与实现（装饰器）是否逐项对得上
```

「看起来没问题」不算通过：**看退出码**。

## ② 半自动：编译与单测

```bash
mvn -q clean package        # 必须 clean：增量编译会把「按旧 api 编出来的 target」当成成功
mvn -q test                 # 单测全绿（Java 插件）
```

Java 插件的三条底线用例（见 `02-java-plugin.md` ⑤）：注册成功、返回值正确、卸载回收；
再加一条「加载链路」用例（真实描述符 → 插件状态 `STARTED`）。
脚本插件没有框架级单测，靠 ① 的两个退出码 + ③ 的真跑。

## ③ 真跑一遍（本段不可省）

### Java 插件

```bash
cp target/my-plugin-0.1.0.jar ~/.jellyfish/plugins/     # 或 config.json 里 plugins.roots 的目录
# 重启 jellyfish
```

**「怎么看出来的」按顺序查**：

| 看什么 | 期望 |
|---|---|
| 启动日志 | `插件运行时已启动: total=… started=… blocked=…`；没有 `插件未通过描述符体检，将不启动…` / `插件依赖未满足，未启动…` / `插件被禁用…` 这类针对你的插件的行 |
| 命令 / 工具可见性 | 命令出现在 `/help`；工具能被模型调用（说一句让模型用它的话） |
| 改配置段 | `/reload` 后日志里出现 `插件配置重载完成: started=… restarted=… failed=…`，且行为按新配置变 |

**没有「列出插件」的系统命令**，因此「日志 + 行为」就是证据；两者都要看，只看一个会漏掉
「插件 STARTED 但能力没注册上」。

### 脚本插件

```bash
cp -r ./my-script ~/.jellyfish/scripts/python/my-script   # scriptsRoot 指向的目录
# 重启 jellyfish
```

| 看什么 | 期望 |
|---|---|
| `/python`（或 `/node`）台账 | 首行脚本数 +1；你的脚本那一行有已登记能力数；`问题` 段为空 |
| 首次调用后 | 台账里你的脚本出现 worker `pid=`；`熔断：` 仍是「尚未发生调用」以外的正常状态 |
| 模型 / 用户路径 | 工具真被调用并返回内容；命令真出结果；贡献（面板 / 状态栏 / 提示词）真出现在界面上 |
| 清单一致性 | 若调用报「清单与实现不一致」，回去跑 `dump_manifest --write` 并重启 |

### 三个外壳的差异（会影响你看到的「失败」）

| 外壳 | 验收时要注意 |
|---|---|
| `-tui` | 有界面：面板 / 状态栏 / 候选补全都能看；审批框在场 |
| `-cli` | **没有审批者，`ask` 就是拒绝**——写类工具在这里被拒不是插件的 bug；面板类贡献可能永远不被询问 |
| `-server` | 会话按 id 寻址，审批走 HTTP 桥 |

## 失败路径要解释得清（验收的一部分）

动手前就该知道、交付时要能说出来：

| 情形 | 会发生什么 |
|---|---|
| Java 插件描述符有问题 | 插件被静默跳过（记为 blocked），**内核照常启动**；启动日志里有 `LOG.error` |
| Java 插件 `start()` 抛错 | 插件转 `FAILED`，已完成的注册被回收，**不保证**再调 `stop()` |
| 插件 `stop()` 之后还在注册 / 发布 | 当场抛 `JellyfishException`（fail-closed）；后台线程必须在 `stop()` 返回前停 |
| 面板 / 状态栏处理器慢或做 IO | 卡住整个界面（跑在渲染线程且没有超时）；跨进程的慢活要拆到另一个脚本 |
| 权限拦截里抛异常 / 返回 `null` | 按**拒绝**处理（fail-closed）；「配置读不出来」绝不能变成放行 |
| 工具处理器抛异常 | 折成失败的 `ToolCallResult`，**回合继续**，模型看到你抛出的首行原因 |
| 脚本 worker 崩了 | 只影响该脚本的调用，计入熔断冷却，冷却后自动半开 |
| 脚本清单与实现不一致 | 首次拉起时拒绝服务（缺省 `manifestStrict=true`），该脚本所有调用失败 |
| 脚本里写 `${ENV}` 而环境变量没设 | **进程启动即失败**（不是「取不到就留空」） |
| 脚本 `request_tuning` / `aging_strategy` 没被问过 | 正常：热路径点不冷启动，只提供这两个贡献的脚本永远不会被拉起 |

## 交付前的自问清单

- [ ] 每个能力都能指出「谁触发 → 命中哪个扩展点 → 失败怎么办」
- [ ] 选型结论写明了「为什么不是另一种」（含已接受的代价）
- [ ] Java：`clean package` + 单测 + `check-plugin-jar.sh` 三者全绿
- [ ] 脚本：`check-script.sh` + `dump_manifest --check` 退出码 0；清单里的描述 / 参数与声明一致
- [ ] 真跑过一次，且能说清怎么看出来的（日志 / 台账 / 界面 / 模型输出）
- [ ] 失败路径里至少覆盖了「依赖缺失 / 配置写错 / 无审批者外壳」三条中的两条，且行为可解释
- [ ] 工具名 / 命令名 / 配置字段这类用户可见的东西，文档一起改了
- [ ] 敏感信息（密钥、内网地址）没有写进代码、清单或文档

## 回滚（装错了怎么退）

```bash
rm ~/.jellyfish/plugins/my-plugin-0.1.0.jar      # Java：删 jar 后重启
mv ~/.jellyfish/scripts/python/my-script /tmp/   # 脚本：把目录挪走（没有逐脚本开关）后重启
```

改配置段不用重启（`/reload`）；**新增 / 删除 jar 与脚本目录都必须重启进程**。

## 内核升级之后

- **第三方插件**：对齐 `jellyfish-api` 的版本（值类型可能加了字段，旧插件多半仍能跑——api 永远是
  provided，插件拿到的就是运行期那一份）→ `mvn -q clean package` → 重装 → 重跑一次真验证。
  升级后最典型的坏味道是 `NoSuchMethodError`，它几乎总是「没 clean」或「把 api 打进了 jar」。
- **在官方插件仓库里改插件**：另有一整套检查（先在本地装内核 → `clean package` → 三个 `-P*-it` 一个不漏），
  以 `<plugins>/AGENTS.md` 为准。
