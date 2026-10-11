# Jellyfish-Skills

给 Jellyfish 用的**技能（skill）集合**：一个子目录就是一个技能——`SKILL.md` 写「什么时候用、按什么工序做」，
`references/` 放按阶段取用的细节，`scripts/` 放能真跑的自检脚本，`templates/` 放从零开始时的骨架。

技能正文只在模型判断「相关」时才被取回上下文（见下面的三层渐进披露），所以这里的内容写得细也不占日常对话的额度。
本仓库是纯文本 + 脚本，**没有构建步骤**。

## 仓库里的两个技能

| 目录 | 技能名（头部 `name` 与目录同名） | 解决什么 | 产出什么 |
| --- | --- | --- | --- |
| `jellyfish-plugin-development/` | `jellyfish-plugin-development` | 从一句需求做到一个能装的 Jellyfish 插件：需求 → 三个面（模型面 / 用户面 / 内核面）、Java 与脚本插件选型、工程与实现、真跑验收 | 一个能装进 jellyfish 的插件——PF4J jar 或 Python / Node 脚本目录 |
| `source-deep-dive-docs/` | `source-deep-dive-docs` | 把一个源码仓库读成一套多页 HTML 学习文档：跑起来 → 顺一条数据流深读 → 切页成书 → 逐条核验「文件:行号」引用 | 一套可离线阅读的 HTML 文档，如 [Jellyfish-Docs](https://github.com/zcd0831/Jellyfish-Docs) |

两个技能都是**四阶段工序 + 五条红线 + 一份 Definition of Done**，阶段之间设了「不通过不要往下走」的验收点：

```
jellyfish-plugin-development   ① 需求分析 → ② 选型 → ③ 实现 → ④ 验收（真装、真调一次）
source-deep-dive-docs          ① 解析 → ② 设计 → ③ 撰写 → ④ 核验（引用逐条落地）
```

## 安装与生效

技能由官方插件 `jellyfish-plugin-skills` 按目录发现——**一个子目录一个技能，认的是 `SKILL.md`**：

```bash
git clone https://github.com/zcd0831/Jellyfish-Skills.git
mkdir -p ~/.jellyfish/skills
cp -r Jellyfish-Skills/jellyfish-plugin-development ~/.jellyfish/skills/
cp -r Jellyfish-Skills/source-deep-dive-docs       ~/.jellyfish/skills/
```

| 事项 | 说明 |
| --- | --- |
| 前提 | 装好并启用 `jellyfish-plugin-skills` 插件（该插件缺省启用），否则技能不会被发现 |
| 扫描根 | 缺省 `["~/.jellyfish/skills", "./.jellyfish/skills"]`，**有序、同名先到者胜**（用户级在前）。项目级配置里写 `roots` 时，每一项必须是项目目录内的相对路径——这个键决定「去哪读会被当成系统指令的文本」，不能随仓库走 |
| 生效方式 | **改完立即生效**，不需要重启，也不需要 `/reload`（按文件系统签名失效，给还缺东西的目录补上也算） |
| 查看 | 在 jellyfish 里敲 `/skills`：列出根目录、已加载清单与扫描期问题（目录写错、缺 `description`、名称被前面的根占掉） |

## 一个技能长什么样

```
<skill>/
├── SKILL.md          # 正文（写什么、按什么工序做）+ 头部元信息
├── references/       # 按阶段取用的细节文档：正文只写主干，细节在这里
├── scripts/          # 能真跑的自检脚本；核验类脚本不复制进产出物
└── templates/        # 从零开始时整目录拷走的骨架（不一定每个技能都有）
```

`SKILL.md` 的头部只是 `---` 围栏里的扁平 `key: value`（**不是完整 YAML**，支持 `>` / `|` 折行与引号）：

```markdown
---
name: my-skill
description: 什么时候用这个技能：一句话说清触发场景
---
```

- **`description` 必填**：它是模型判断「该不该用这个技能」的唯一依据，缺了整条会被跳过。
- **`name` 可省**：省略时用目录名。
- **三层渐进披露**：名称 + 描述常驻 system prompt；模型判断相关时调 `skill` 工具取回正文；
  正文里提到的 `references/`、`scripts/`、`templates/` 再用 `read_file` / `shell` 按需读取。

## 脚本与模板的依赖

- `scripts/` 下的脚本用 `sh` 与 `python3`（**只用标准库**），不需要装第三方依赖。
  `verify-refs.sh` 刻意只用 `find` 与 `grep`，受限环境里也能跑。
- `templates/java-plugin/` 带一份可用的 `pom.xml`，就地验证需要 JDK 8 + Maven；
  构建产物（`target/`）与 Python 字节码缓存（`__pycache__/`）都已在 `.gitignore` 里排除。
- 技能里的核验脚本一律**从技能目录调用**，不复制进产出物目录——复制一份就会各自漂移。

## 相关仓库

| 仓库 | 关系 |
| --- | --- |
| [Jellyfish](https://github.com/zcd0831/Jellyfish) | 内核。技能产出的插件装进它，技能读的源码也是它 |
| [Jellyfish-Plugins](https://github.com/zcd0831/Jellyfish-Plugins) | 官方插件仓库：`jellyfish-plugin-skills` 负责发现并加载本仓库的技能；插件开发教程与 `jellyfish-plugin-development` 讲的是同一件事 |
| [Jellyfish-Docs](https://github.com/zcd0831/Jellyfish-Docs) | 在线文档站，`source-deep-dive-docs` 技能的核验脚本就是为这类文档准备的 |
| [Jellyfish-Spring-Boot-Starter](https://github.com/zcd0831/Jellyfish-Spring-Boot-Starter) | 把内核接进已有的 Spring Boot 应用 |
