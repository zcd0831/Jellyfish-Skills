# assets/vendor — 第三方前端库（可选，用于完全离线阅读）

本目录存放文档用到的外部依赖。**它们是可选的**：目录为空时文档照样能读，只是：

| 缺失的文件 | 后果 | 自动兜底 |
| --- | --- | --- |
| `highlight.min.js` | 代码块没有语法着色（仍是等宽、有行号、可复制） | `assets/app.js` 会尝试从 CDN 加载 |
| `mermaid.min.js` | 图表**以源码文本形式展示**，并在页首给出提示条 | 同上 |

也就是说：**能联网时不需要做任何事**；想完全离线（内网机器、断网、拷给别人），
把文件放进来即可。

## 一键获取

```sh
sh assets/vendor/fetch-vendor.sh
```

脚本会下载文件、校验体积下限、检查内容不是 HTML 错误页，任一项不过就报错删除。
要下载的清单与地址写在脚本顶部的 `ASSETS` 变量里。

## 手动获取

| 文件名（必须一致） | 来源 | 版本 | 约大小 |
| --- | --- | --- | --- |
| `highlight.min.js` | `https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/highlight.min.js` | highlight.js 11.9.0 | 约 120 KB |
| `mermaid.min.js` | `https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js` | mermaid 10.9.1 | 约 3 MB |

版本要与上表一致（也要和 `assets/app.js` 第 0 节里 CDN 兜底用的版本一致），
否则可能出现渲染差异。浏览器也可以直接打开上面的 URL 另存为。

> **注意 `highlight.js` 与 `@highlightjs/cdn-assets` 是两个不同的 npm 包。**
> 前者的 `lib/*.js` 是给打包器用的 **CommonJS** 模块（内部 `require("./core")`），
> 直接丢进浏览器会报 `require is not defined`；只有后者的 `highlight.min.js`
> 是预构建的浏览器 bundle。这个坑很常见，判据在 `templates/vendor-fetch.sh` 的注释里。

## 为什么不内联进页面

两个库合计约 3 MB。内联进 N 个页面会让每个 HTML 文件膨胀到几 MB：
打开变慢、diff 不可读，而且它们是有版本的第三方构建产物，放在同一目录便于**独立升级**。

所以采用「**本地优先 + CDN 兜底 + 缺失即降级**」三档，任何一档都能读。

（另外提醒：`app.js` 里回退到 CDN 的 URL 和本目录的文件名是**两处版本声明**，
换版本时两处都要改——见 `references/05-pitfalls.md` 第 9 条。）

## 要不要提交进版本库

**默认不要。** 它们是第三方构建产物，提交进去会让仓库膨胀，以后每次升级都产生巨大 diff。

做法：

1. 把这两个文件名写进 `.gitignore`
2. README 里写明「克隆后跑一次 `sh assets/vendor/fetch-vendor.sh` 即可完全离线」
3. 说明不跑也没关系（CDN 兜底 + 优雅降级）

真正需要「开箱即用、不联网」的场景（外部交付、归档），再把产物打成一个压缩包发布。
