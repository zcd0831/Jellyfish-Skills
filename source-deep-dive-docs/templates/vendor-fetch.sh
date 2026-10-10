#!/bin/sh
# ============================================================================
# 下载本套文档需要的第三方前端库到本目录，之后就能**完全离线**阅读。
#
# 用法：
#     sh assets/vendor/fetch-vendor.sh
# 或在目录内：
#     sh fetch-vendor.sh
#
# 默认下载两个文件（版本与页面里 CDN 兜底用的版本保持一致）：
#     highlight.min.js   highlight.js 11.9.0  代码语法高亮
#     mermaid.min.js     mermaid      10.9.1  架构图 / 时序图渲染
#
# 这两个文件缺失时文档**依然可读**（代码不着色、图表以源码形式展示），
# assets/app.js 会自动回退到 CDN；放好文件后回退逻辑不再触发。
#
# 只用 POSIX sh 语法（无 bash 扩展、无 VAR=val 前缀赋值），
# 以便在最小化的环境里也能跑。
# ============================================================================
set -e

DIR=$(cd "$(dirname "$0")" && pwd)

# ---- 依赖的第三方库清单 ----------------------------------------------------
# 格式：文件名|下载地址|体积下限（字节）
#
# ★ 为什么要加体积下限：拿错包或下到错误页时，文件往往只有几 KB 且内容是 HTML，
#   不校验的话会静默装上一个坏文件，直到浏览器里报错才发现（见 references/05-pitfalls.md 第 8 条）。
#
# ★ 换库或升级版本时，注意三点：
#   1. 优先选名字里带 cdn / dist / browser / umd 的包——主包的 lib/*.js 可能是给打包器用的
#      CommonJS 模块，浏览器里会报 require is not defined。
#   2. 地址换完，templates/app.js 第 0 节的 CDN 兜底 URL 要一起换，两处版本必须一致。
#   3. 体积下限按实际文件大小取值，别太贴边（留 20% 余量即可）。
ASSETS='highlight.min.js|https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/highlight.min.js|100000
mermaid.min.js|https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js|2000000'

# ---- 下载器 ---------------------------------------------------------------
download() {
    url=$1
    out=$2
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "${url}" -o "${out}"
    elif command -v wget >/dev/null 2>&1; then
        wget -q "${url}" -O "${out}"
    else
        printf '错误：既没有 curl 也没有 wget。请手动下载：\n  %s\n' "${url}" >&2
        exit 1
    fi
}

# ---- 校验：体积下限 + 内容不是 HTML 错误页 --------------------------------
verify() {
    out=$1
    min=$2

    if [ ! -s "${out}" ]; then
        printf '错误：%s 下载后为空，请检查网络或代理。\n' "${out}" >&2
        return 1
    fi

    # 用内建去掉 wc 输出里的前导空格（不引入 tr）
    size=$(wc -c < "${out}")
    size=${size##* }
    if [ "${size}" -lt "${min}" ]; then
        printf '错误：%s 只有 %s 字节（下限 %s）。\n' "${out}" "${size}" "${min}" >&2
        printf '      多半是下到了错误页或拿错了包（CommonJS 模块的壳通常只有几 KB）。\n' >&2
        printf '      请确认地址指向的是浏览器可用的预构建 bundle。\n' >&2
        return 1
    fi

    if grep -qi '<html' "${out}" 2>/dev/null; then
        printf '错误：%s 的内容看起来是 HTML 页面而不是脚本。\n' "${out}" >&2
        return 1
    fi
    return 0
}

# ---- 主流程 ---------------------------------------------------------------
failed=0
printf '%s\n' "${ASSETS}" | while IFS='|' read -r name url min; do
    [ -z "${name}" ] && continue
    printf '下载 %-20s ← %s\n' "${name}" "${url}"
    if ! download "${url}" "${DIR}/${name}"; then
        printf '错误：%s 下载失败。\n' "${name}" >&2
        rm -f "${DIR}/${name}"
        exit 1
    fi
    if ! verify "${DIR}/${name}" "${min}"; then
        rm -f "${DIR}/${name}"
        exit 1
    fi
    printf '     ✔ 通过校验（%s 字节）\n' "${size}"
done

printf '\n完成。当前目录内容：\n'
ls -l "${DIR}"

printf '\n提示：这两个文件属于第三方构建产物，通常**不应提交进版本库**——\n'
printf '      把它们写进 .gitignore，靠本脚本按需获取即可。\n'
printf '      文件缺失时文档仍可读（CDN 兜底 + 降级），不影响其他人克隆后阅读。\n'
