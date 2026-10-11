# 模板怎么用

两份骨架都是「整目录拷走再改」：拷之前先读 `../references/02-java-plugin.md`（Java）或
`../references/03-script-plugin.md`（脚本），它们解释了每处为什么这么写。

## `java-plugin/`（独立 Maven 工程）

```
java-plugin/
├── pom.xml                                       # api 与 slf4j 都是 provided；infra 只在 test scope
└── src
    ├── main/java/com/example/myplugin/
    │   ├── MyPlugin.java                         # 入口：注册工具 / 命令 / 提示词贡献 / 事件订阅
    │   ├── MyTool.java                           # 工具处理器（不认识 PluginContext，可单独单测）
    │   └── MyConfig.java                         # 配置值对象（from(Map) + ~ 展开 + 类型校验）
    ├── main/resources/plugin.properties          # PF4J 描述符，必须落在 jar 根目录
    └── test/java/com/example/myplugin/
        ├── MyToolTest.java                       # 处理器行为
        ├── MyConfigTest.java                     # 配置解析（含「配错了要当场报错」）
        └── MyPluginLoadingTest.java              # 加载链路：真实描述符 → 状态 STARTED → 能力可路由 → 回收
```

**拷完要替换的**：

| 位置 | 换成什么 |
|---|---|
| `pom.xml` 的 `groupId` / `artifactId` / `version` | 自己的坐标（`artifactId` 建议与 `plugin.id` 一致） |
| 包名 `com.example.myplugin` | 自己的包（`plugin.properties` 里的 `plugin.class` 一起改） |
| `plugin.properties` 的 `plugin.id` / `plugin.description` / `provider` | 自己的身份。**`plugin.id` 同时是注册表的 owner**，别含 `::` |
| `MyTool.NAME`（`my_hello`） | 自己的工具名，建议带插件前缀避免与别的插件撞名 |
| `MyPlugin.COMMAND_NAME` | 自己的命令名 |

**开箱即用的验证**：

```bash
mvn -q clean test                                   # 5 条单测 + 3 条加载链路用例
mvn -q package -DskipTests
sh ../scripts/check-plugin-jar.sh target/my-plugin-0.1.0.jar
cp target/my-plugin-0.1.0.jar ~/.jellyfish/plugins/   # 然后重启 jellyfish
```

## `script-python/` `script-node/`

```
script-python/
├── main.py           # 入口：@tool / @command / @contributes / @subscribe
└── manifest.json     # 与实现逐项一致；模型的工具定义只在它里面
```

**拷完要做的**：把目录放到 `scriptsRoot` 下（缺省 `scripts/python` / `scripts/node`，相对进程工作目录），
**目录名就是脚本 id**；改工具名 / 命令名之后，用生成器重新生成清单（别手改描述，那会与实现漂移）：

```bash
cp -r script-python ~/.jellyfish/scripts/python/my-script
python3 ~/.jellyfish/gateway/python/<摘要>/script/dump_manifest.py ~/.jellyfish/scripts/python/my-script --write
sh ../scripts/check-script.sh ~/.jellyfish/scripts/python/my-script
```

`<摘要>` 是网关资源目录（内容摘要）——第一次用过某脚本之后它才会出现，用 `find` 找即可：

```bash
find ~/.jellyfish/gateway -name dump_manifest.py
```

**开箱即用的验证**：上面两条命令的退出码都是 0，然后重启 jellyfish，看 `/python`（或 `/node`）台账，
并真调一次工具与命令。
