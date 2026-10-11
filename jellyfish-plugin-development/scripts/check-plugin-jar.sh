#!/bin/sh
#
# 体检一个 Jellyfish 插件 jar。
#
# 用法：  sh check-plugin-jar.sh <plugin.jar>
# 退出码：0 = 通过（可能有警告）；1 = 有错误；2 = 用法/环境问题
#
# 它挡的是「编译通过、单测全绿，但内核静默拒绝加载」那一类问题：
#   * plugin.properties 不在 jar 根目录（PF4J 按名在插件根下找）；
#   * 必填键缺失（plugin.id / plugin.class）；
#   * plugin.class 指向的类不在 jar 里（打包遗漏或类名写错）；
#   * jar 里自带 zcd/jellyfish/api 或 org/pf4j 的类 —— 子优先类加载器会把父加载器那一份遮蔽，
#     内核在加载期直接拒绝这种 jar，而症状常常只是「莫名的新字段读不到」；
#   * 顺带发现 shade 误把 jellyfish-api 打进来的痕迹（META-INF/maven/... 里的坐标）。
#
set -u

usage() {
    echo "用法: sh check-plugin-jar.sh <plugin.jar>"
}

if [ "$#" -ne 1 ]; then
    usage
    exit 2
fi

JAR="$1"
if [ ! -f "$JAR" ]; then
    echo "ERROR: 找不到文件: $JAR"
    exit 2
fi

# 列目录：优先 unzip，其次 python3，最后 jar（JDK 自带）
list_entries() {
    if command -v unzip >/dev/null 2>&1; then
        unzip -Z1 "$JAR"
    elif command -v python3 >/dev/null 2>&1; then
        python3 - "$JAR" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    for name in zf.namelist():
        print(name)
PY
    elif command -v jar >/dev/null 2>&1; then
        jar tf "$JAR"
    else
        echo "ERROR: 需要 unzip、python3 或 jar 之一来读取 jar 内容"
        exit 2
    fi
}

ENTRIES="$(list_entries)" || exit 2
if [ -z "$ENTRIES" ]; then
    echo "ERROR: 读不出 jar 内容（不是 zip，或已损坏）: $JAR"
    exit 2
fi

errors=0
warnings=0

err() { echo "ERROR: $1"; errors=$((errors + 1)); }
warn() { echo "WARN : $1"; warnings=$((warnings + 1)); }

echo "== 体检 $JAR =="

# 1) 自带 api / pf4j 的类（内核加载期硬拒）
if echo "$ENTRIES" | grep -q '^zcd/jellyfish/api/'; then
    err "jar 里含 zcd/jellyfish/api/ 的类：jellyfish-api 必须是 provided 依赖，自带会破坏类型同一性"
fi
if echo "$ENTRIES" | grep -q '^org/pf4j/'; then
    err "jar 里含 org/pf4j/ 的类：pf4j 由内核提供，不要打进插件包"
fi
if echo "$ENTRIES" | grep -q '^META-INF/maven/io.github.zcd0831/jellyfish-api/'; then
    err "jar 里含 jellyfish-api 的 maven 元数据：shade 的 includes 里误加了 jellyfish-api"
fi

# 2) 描述符位置与内容
if ! echo "$ENTRIES" | grep -qx 'plugin.properties'; then
    err "jar 根目录下没有 plugin.properties —— PF4J 只按名在插件根下找，插件不会被加载"
    PLUGIN_PROPS=""
else
    PLUGIN_PROPS="$(mktemp)" || exit 2
    if command -v unzip >/dev/null 2>&1; then
        unzip -p "$JAR" plugin.properties > "$PLUGIN_PROPS"
    elif command -v python3 >/dev/null 2>&1; then
        python3 - "$JAR" "$PLUGIN_PROPS" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as zf:
    data = zf.read('plugin.properties')
with open(sys.argv[2], 'wb') as out:
    out.write(data)
PY
    else
        jar xf "$JAR" plugin.properties && mv plugin.properties "$PLUGIN_PROPS"
    fi
fi

PLUGIN_ID=""
PLUGIN_CLASS=""
if [ -n "$PLUGIN_PROPS" ]; then
    get_key() {
        # 取第一个非注释的 key=value；去空白
        sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\(.*\)$/\1/p" "$PLUGIN_PROPS" | sed -n 1p | sed 's/[[:space:]]*$//'
    }
    PLUGIN_ID="$(get_key 'plugin\.id')"
    PLUGIN_CLASS="$(get_key 'plugin\.class')"

    if [ -z "$PLUGIN_ID" ]; then
        err "plugin.properties 缺少 plugin.id（它是插件身份，同时是注册表的 owner）"
    else
        case "$PLUGIN_ID" in
            *::*) err "plugin.id 含 '::'（那是插件与子身份的分隔符，会被内核直接拒）: $PLUGIN_ID" ;;
            *[[:space:]]*) err "plugin.id 含空白字符: $PLUGIN_ID" ;;
        esac
    fi

    if [ -z "$PLUGIN_CLASS" ]; then
        err "plugin.properties 缺少 plugin.class（插件入口类）"
    else
        CLASS_ENTRY="$(echo "$PLUGIN_CLASS" | tr '.' '/').class"
        if ! echo "$ENTRIES" | grep -qx "$CLASS_ENTRY"; then
            err "plugin.class 指向的类不在 jar 里: ${PLUGIN_CLASS}（期望 ${CLASS_ENTRY}）"
        fi
    fi

    if [ -z "$(get_key 'plugin\.version')" ]; then
        warn "没写 plugin.version（内核会兜底 0.0.0）"
    fi
    REQUIRES="$(get_key 'plugin\.requires')"
    case "$REQUIRES" in
        ""|"*")
            # 缺省与 * 都是正常写法：内核目前不声明系统版本
            ;;
        *)
            warn "plugin.requires 写的是 '$REQUIRES'：内核不声明系统版本，显式写 * 才是「不限版本」；非法表达式会被归一为 * 并记一条描述符错误（插件起不来）"
            ;;
    esac

    rm -f "$PLUGIN_PROPS"
fi

# 3) 提示：嵌套的 plugin.properties（放错位置）
NESTED="$(echo "$ENTRIES" | grep 'plugin\.properties' | grep -v '^plugin\.properties$' || true)"
if [ -n "$NESTED" ]; then
    warn "jar 里还有别处的 plugin.properties（内核只认根目录那一份）: $NESTED"
fi

echo "-- 插件: id=${PLUGIN_ID:-<缺失>} class=${PLUGIN_CLASS:-<缺失>}"
if [ "$errors" -eq 0 ]; then
    echo "结果: 通过（$warnings 条警告）"
    exit 0
fi
echo "结果: 失败（$errors 条错误，$warnings 条警告）"
exit 1
