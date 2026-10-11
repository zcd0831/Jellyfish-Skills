#!/bin/sh
#
# 体检一个脚本插件目录（Python / Node 通用）。
#
# 用法：  sh check-script.sh <脚本目录>
# 退出码：0 = 通过（可能有警告）；1 = 有错误；2 = 用法/环境问题
#
# 两步：
#   1) 清单静态体检（本目录的 check-script-static.py）：未知键、必填缺失、类型不对、重复、越界；
#   2) 如果本机已经解包过网关资源，再跑一次官方生成器的 --check：
#      清单与实现（装饰器声明）必须逐项一致，否则脚本被拉起时会拒绝服务。
#      找不到生成器不算失败（那说明这台机器还没用过这个语言的桥接插件），只给一条提示。
#
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "$#" -ne 1 ]; then
    echo "用法: sh check-script.sh <脚本目录>"
    exit 2
fi

DIR="$1"
if [ ! -d "$DIR" ]; then
    echo "ERROR: 不是目录: $DIR"
    exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: 本脚本需要 python3（脚本插件的运行环境本来也需要解释器）"
    exit 2
fi

failed=0

echo "=== 1/2 清单静态体检 ==="
if ! python3 "$HERE/check-script-static.py" "$DIR"; then
    failed=1
fi

echo
echo "=== 2/2 清单与实现一致性（官方生成器） ==="

# 语言：有 main.js 就当 Node，否则当 Python（也可显式用 --lang 覆盖，这里从简）
if [ -f "$DIR/main.js" ]; then
    LANG_NAME="node"
    GENERATOR="dump_manifest.js"
    INTERPRETER="node"
else
    LANG_NAME="python"
    GENERATOR="dump_manifest.py"
    INTERPRETER="python3"
fi

GATEWAY_ROOT="${JELLYFISH_GATEWAY_ROOT:-$HOME/.jellyfish/gateway}"
GENERATOR_PATH="$(find "$GATEWAY_ROOT/$LANG_NAME" -name "$GENERATOR" -path '*/script/*' 2>/dev/null | head -1)"

if [ -z "$GENERATOR_PATH" ]; then
    echo "跳过：没找到 ${GENERATOR}（本机还没用过 $LANG_NAME 桥接插件）。"
    echo "      第一次真跑过某个脚本之后，网关资源会解包到 $GATEWAY_ROOT/$LANG_NAME/<摘要>/script/。"
    echo "      若配过 gatewayRoot，请设 JELLYFISH_GATEWAY_ROOT 指向它；Node 需要 $INTERPRETER 可用。"
else
    echo "-- 生成器: $GENERATOR_PATH"
    if ! "$INTERPRETER" "$GENERATOR_PATH" "$DIR" --check; then
        echo "ERROR: 清单与实现不一致（缺省 manifestStrict=true 时该脚本会拒绝服务）"
        echo "       修法：$INTERPRETER $GENERATOR_PATH $DIR --write  然后重启进程（清单在插件启动期读入）"
        failed=1
    fi
fi

echo
if [ "$failed" -eq 0 ]; then
    echo "结果: 通过"
    exit 0
fi
echo "结果: 有失败项（见上面的 ERROR）"
exit 1
