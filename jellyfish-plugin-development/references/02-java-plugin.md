# ② ③ Java 插件：从工程到可安装的 jar

读它之前先读完 `01-requirement.md`，确认选型结论是 **Java 插件**。

> 路径约定：`<kernel>` = 内核仓库（`Jellyfish`），`<plugins>` = 官方插件仓库（`Jellyfish-Plugins`）。
> 签名一律以 `<kernel>/jellyfish-api/src/main/java/zcd/jellyfish/api/` 下的源码为准——README 与示例
> 可能落后于代码。

## 工序列（七步，每步都有验收点）

```
① 建工程 ─→ ② 描述符 ─→ ③ 插件类与注册 ─→ ④ 配置解析 ─→ ⑤ 单测 ─→ ⑥ 打包安装 ─→ ⑦ 真跑一遍
   templates/     plugin.       handle/         Config       JUnit5      cp jar +    04-verification.md
   java-plugin/   properties    contribute      值对象       +Mockito    重启
```

### ① 建工程

**推荐做法：把 `templates/java-plugin/` 整目录拷走**，把包名 `com.example.myplugin` 全局替换成自己的。
目录形状（独立 Maven 工程，一个工程一个插件）：

```
my-plugin/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example/myplugin/MyPlugin.java        # 入口：start() 里注册全部能力
    │   ├── java/com/example/myplugin/MyConfig.java        # 配置值对象
    │   └── resources/plugin.properties
    └── test/java/com/example/myplugin/MyPluginLoadingTest.java
```

在**官方插件仓库里加插件**是一个变体：一个插件一个子模块，父 POM `io.github.zcd0831:jellyfish-plugins`
已经配好依赖版本，还要登记到父 POM 的 `<modules>` 并往 `cpPlugins.sh` 加一行。
这条路径下 `<plugins>/AGENTS.md` 优先于本技能。

**pom 的三条硬约束**（照 `templates/java-plugin/pom.xml` 抄）：

| 约束 | 为什么 |
|---|---|
| `jellyfish-api` 必须 `provided` | 插件 jar 里不能含 api 的类；内核加载期会直接拒绝带了 `zcd/jellyfish/api/` 的 jar |
| `slf4j-api` 也 `provided` | 宿主已经提供，自带一份会打出两份日志配置 |
| 私有依赖（Jackson、commons-exec…）用 `compile` + shade 打进 jar，且 `includes` 里**绝不能出现** `jellyfish-api` / `org.pf4j:pf4j` / `slf4j` | 自带 api 会让插件拿旧版本的值类型跑，内核加字段时新字段静默丢失 |

编译器要开 `<parameters>true</parameters>`（api 的值类型反序列化依赖构造器参数名）。
编译目标锁 **JDK 1.8**：内核跑在 1.8 上，插件不能用 Java 9+ 的 API 或语法。
自检：`sh <skill>/scripts/check-plugin-jar.sh target/*.jar`。

### ② 描述符 `plugin.properties`（必须放在 jar 根目录）

```properties
plugin.id=my-plugin
plugin.class=com.example.myplugin.MyPlugin
plugin.version=0.1.0
plugin.provider=com.example
plugin.description=一句话说明这个插件做什么
plugin.requires=*
jellyfish.tags=example
```

| 键 | 必需 | 说明与后果 |
|---|---|---|
| `plugin.id` | 是 | 插件身份，**同时是注册表的 owner**（回收、覆盖、诊断都按它归属）；含 `::` 直接被拒 |
| `plugin.class` | 是 | 必须是 `JellyfishPlugin` 实现、非抽象、**有公开无参构造器**；不符会在加载期抛错，且**中断该次加载**（同批后续插件可能都没装上） |
| `plugin.version` | 否 | 缺失兜底 `0.0.0` |
| `plugin.provider` / `plugin.description` | 否 | 展示用，无校验 |
| `plugin.requires` | 否 | 内核兼容约束；**写成非法 semver 表达式会被归一为 `*` 并记一条描述符错误 → 插件起不来**。内核目前不声明系统版本，写 `*` 是显式「不限版本」 |
| `jellyfish.tags` | 否 | 逗号分隔标签，仅诊断与展示（不参与授权） |

描述符有问题**不会让内核起不来**，但插件会被静默跳过——所以 `04-verification.md` 里「确认它真的 STARTED」
是必需步骤。

### ③ 插件类与注册

```java
public final class MyPlugin implements JellyfishPlugin {

    @Override
    public void start(PluginContext context) {
        // 先装配再注册：处理器一旦注册就可能被调用，依赖必须已经就绪
        MyConfig config = MyConfig.from(context.configuration());
        context.handle(ToolCallRequest.class, "hello", MyTools.HELLO, new HelloTool(config));
    }
}
```

| 事实 | 说明 |
|---|---|
| **注册窗口是整个存活期** | `start()` 返回到 `stop()` 之前都能注册、订阅、发布；不必挤在 `start()` 里 |
| `start()` 抛错 | 插件转 `FAILED`，框架回收已完成的注册，**不保证**再调 `stop()` |
| `stop()` 之后 **fail-closed** | 任何注册 / 发布当场抛 `JellyfishException`；产出注册的后台线程必须在 `stop()` 返回前停下来 |
| 处理器与订阅**不用自行反注册** | 框架按 owner 一次收干净；`Subscription.close()` 只是可选优化 |
| 拿不到的东西 | 没有会话列表、没有 `cwd`；不能新开会话、不能起/停回合（只能 `submit` 五种 `PluginAction`） |

**注册 API**（`PluginContext`）：

| 方法 | 用途 | 冲突 / 顺序规则 |
|---|---|---|
| `handle(requestType, routeKey, descriptor, handler)` | 带路由键的处理器（工具名、命令名、标记字符、provider 名） | 同「类型 + 路由键」**至多一个**；重复注册在启动时以 `DUPLICATE_HANDLER` 当场暴露 |
| `contribute(requestType, descriptor, handler)` | 类型级贡献（0..N 个） | 顺序由 `RegisterOptions.order` 决定；合并规则在**调用点**，见 `01` 的表 |
| `observe(eventType[, filter], listener)` | 订阅通知 | 事件是旁路、**可丢**；不要用它传递必须到达的结果 |
| `emit(event)` | 发布通知 | Java 侧无白名单；但 UI 贡献处理器里**不许**发 `UiInvalidatedEvent`（死循环） |
| `present(contribution)` | 往外壳推展示数据 / 「我脏了」 | 入队即返回；队列满会丢（`DROPPED_QUEUE_FULL`），**不能当失败去重试** |
| `configuration()` | 本插件配置段（已做 `${ENV}` 替换与双源合并） | 未配置时是空映射，不是 `null` |

**想顶替内核自带的工具或命令**：加 `RegisterOptions.override(true)`。它不是就地替换，而是把你的登记
**压在链顶**，旧登记仍在表里；你的插件一被回收（停止 / `/reload`）旧的就自动重新生效——不存在
「插件走了，被它顶掉的内核工具永久消失」。

**工具骨架**（`ToolCallRequest` → `ToolCallResult`）：

```java
private static final ToolDescriptor DESCRIPTOR = new ToolDescriptor(
        "hello", "按名字打招呼",
        Collections.<String, Object>singletonMap("name",
                params("string", "要打招呼的人")),   // 参数的 JSON Schema properties
        Collections.singletonList("name"));         // 必填参数名 —— 不是 order！

ToolCallResult handle(ToolCallRequest request) {
    Object name = request.getArguments().get("name");
    if (name == null || String.valueOf(name).trim().isEmpty()) {
        throw new JellyfishException("缺少参数 name");   // 首行会显示在轨迹行上，写成人能看懂的原因
    }
    return new ToolCallResult("hello", "你好，" + name + "！", metadata("问候 1 次"));
}
```

三条约定：**失败就抛 `JellyfishException`**（不要返回 `{"error": ...}`——那会被当成正常输出）；
**输出首行写结论**（模型据此判断成没成）；给人看的一句话放 `ToolMetadata.KEY_SUMMARY`（单行、不放密钥）。

**命令骨架**（`CommandRequest` → `CommandResult`）：

```java
context.handle(CommandRequest.class, "hello",
        new CommandDescriptor("和插件打个招呼", "<名字>", Arrays.asList("hi"), /* sessionRequired */ false),
        request -> {
            CommandArguments args = request.getArguments();
            String first = args.getTokens().isEmpty() ? "" : args.getTokens().get(0);
            return CommandResult.ok("你好，" + first + "！");
        });
```

`CommandResult` 的构造器是私有的，用静态工厂：`ok(text)` / `choices(text, choices)` / `error(text)` /
`unknown(text)` / `handoff(text)`。**`sessionRequired` 缺省 `true`（保守）**：依赖会话的命令必须显式
声明 `false` 才能在没有会话的界面（如 TUI 首页）里用。`handoff` 只声明「把这段文本当作我的输入继续跑」，
命令本身碰不到模型、也起不了回合。

### ④ 配置解析

用户在 `jellyfish.json` 的 `plugins.configurations.<pluginId>` 下写你的配置：

```java
MyConfig config = MyConfig.from(context.configuration());   // 惯例：值对象 + 静态工厂 from(Map)
```

- `${ENV}` 插值与全局 / 项目双源合并**内核已经做完**，你拿到的是最终值；但 **`~` 不展开**，插件自己展开。
- 键写错、值越界**当场抛**（启动期就该让人看见），不要静默回落默认值——那会变成「配置不生效」。
- 「没配」与「配成某个值」是两件事：不确定就用 `null` 表示「不表态」，别用一个自己编的默认值把内核配置压掉。
- 配置可疑用 `context.emit(new ConfigWarningEvent(...))` 告诉用户，**不要阻断启动**。
- 需要把 JSON 转对象时**自带 Jackson 并 shade 进 jar**（内核的序列化封装在 `jellyfish-infra` 里，插件看不到）。

### ⑤ 单测（三条是底线）

| 用例 | 验什么 |
|---|---|
| 注册成功 | 启动后 `ExtensionRegistry.bindings(...)` 里能看到你的处理器 |
| 返回值正确 | 直接调你的 handler（不经内核），断言输出 / 异常 |
| 卸载回收 | `manager.close()` 后 bindings 为空 |

**做法**：测试期可以把 `jellyfish-infra` 引成 `test` scope，拿到**真实的** `ExtensionRegistry` /
`EventChannel` / `PF4JPluginManager`（注册与派发走的就是内核那条路径；换成 mock 只是验证「我以为内核会怎么查」），
其余内核服务（`SessionManager`、`RuntimeInfoHolder`…）直接 mock。**绝不能把 infra 升为 `compile`。**

**再加一条「加载链路」测试**（这是本技能最推荐的一条）：把真实的 `plugin.properties` 拷进 `@TempDir`
形成 PF4J 认得的插件目录，用真实的插件管理器 `bootstrap()`，断言插件状态是 `STARTED`——
它专治「描述符少一个键 / 入口类没有公开无参构造器」这类**单测全绿但插件根本不生效**的问题。
骨架见 `templates/java-plugin/src/test/java/.../MyPluginLoadingTest.java`。

单测规范（跟所在仓库走，官方仓库的口径）：JUnit5 + Mockito，类名 `{被测类}Test`，方法名
`{方法}_should_{预期}_when_{条件}`，一个方法只验一个行为，不启动 Spring、不访问网络与数据库。

### ⑥ 打包安装

```bash
mvn -q clean package -DskipTests          # 必须 clean：增量编译会把「按旧 api 编出来的 target」当成功
sh <skill>/scripts/check-plugin-jar.sh target/my-plugin-0.1.0.jar
cp target/my-plugin-0.1.0.jar ~/.jellyfish/plugins/     # 或 config.json 里 plugins.roots 指向的目录
# 重启 jellyfish —— 新增 / 删除 jar 只在启动期确定
```

- 扫描**只到 roots 的下一层**（每个插件一个目录，或直接放 jar 由 PF4J 处理）；
  没被加载先确认：jar 在 `plugins.roots` 下、没被 `plugins.disabled` 排掉、然后重启。
- **只改配置段不用重启**：`/reload` 会重启「配置段变了」的插件。
- 内核升级（`jellyfish-api` 版本变了）之后：对齐依赖版本 → `mvn -q clean package` → 重装 → 重跑一次真验证。
  在官方仓库里改插件时另有整套检查（`mvn install` 内核 → `clean package` → 三个 `-P*-it` 全跑），
  以 `<plugins>/AGENTS.md` 为准。

### ⑦ 真跑一遍

装完不算完，**必须真调一次**并说明怎么看出来的（模型调工具 / 敲命令 / 看到面板），
清单见 `references/04-verification.md`。

## 编码约定（第三方仓库自行取舍，官方仓库口径如下）

- 缩进 4 空格、K&R 大括号、文件末尾留换行；类 / 接口 / 方法 / 成员都要文档注释，方法注释写 `@param` / `@return`。
- 注释解释「为什么」，不复述代码；异常统一抛 `JellyfishException`。
- 工具方法 / 常量类用 `final` + 私有构造器；类注释加 `@author <你的名字>`。
- 跨边界值类型**恰好一个可见构造器 + 静态工厂**：引用 api 的值类型时优先用静态工厂
  （内核给值类型加字段时旧代码不用改）；**测试夹具反过来，必须用全字段构造器**（否则「后加字段读不回来」
  会被静默吞掉）。
- 改了用户可见行为（工具名、命令、配置字段）就同步改文档。

## 官方插件里可以照读的范例

| 想看什么 | 读哪个 |
|---|---|
| 最小插件（一个贡献） | `<plugins>/jellyfish-plugin-compact/` |
| 工具 + 命令 + 面板 + 状态栏 + 事件订阅齐全 | `<plugins>/jellyfish-plugin-todo/` |
| 工具 + 权限拦截 + 输入指令 | `<plugins>/jellyfish-plugin-shell/` |
| 自带 Jackson + shade 配置 | `<plugins>/jellyfish-plugin-mcp/` |
| 加载链路端到端测试的完整写法 | `<plugins>/jellyfish-plugin-compact/src/test/java/.../CompactPluginLoadingTest.java` |
