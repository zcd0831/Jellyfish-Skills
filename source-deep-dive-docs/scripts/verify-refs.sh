#!/bin/sh
# ============================================================================
# verify-refs.sh —— 文档「文件:行号」引用自检
#
# 作用：把 *.html 里所有 `Xxx.java:123` / `path/to/pom.xml:54-56` 形式的引用抽出来，
#       逐个落到源码上，报出「缺文件 / 越界 / 歧义 / 可疑」四类问题。
#
# 用法（本脚本常驻技能目录 `source-deep-dive-docs/scripts/`，因此文档目录建议显式给；
#       选项必须写在位置参数之前——解析到第一个非选项参数就停）：
#     sh verify-refs.sh <文档目录> <源码根...>     # 推荐：文档目录与源码根都显式给
#     sh verify-refs.sh <文档目录>                # 只给文档目录，源码根自动探测
#     sh verify-refs.sh -v <文档目录>             # 额外列出「引用注释/注解行」的条目
#     sh verify-refs.sh -x java,ts,go <文档目录>  # 只校验这些扩展名的引用
#     sh verify-refs.sh -h                       # 帮助
#
# 文档目录省略时用当前目录；当前目录也没有 .html 才回退到「脚本所在目录的上一级」，
# 那是「脚本与文档同放」的老布局——脚本住在技能目录里时那一级是技能目录，别指望这个回退。
#
# 关于「歧义」：同名文件在大仓库里极多。多候选时**必须报错而不是静默取第一个**，
# 否则会把校验落到别的文件上，报出假的错误（或假的通过）。
#
# 关于「可疑」：文档经常**有意**引用注释原文（例如引 javadoc 解释设计意图），
# 所以「首行是注释/注解」不算问题，默认只汇总数量；只有「首行为空行」「首行是纯括号」
# 才说明行号可能偏了。
#
# 退出码：0 = 无越界/缺文件；1 = 有；2 = 环境问题（找不到文档或源码根）
#
# 两条硬性实现约束（都踩过坑，别改）：
#   1. 所有变量展开一律写成 ${var}。变量名后紧跟中日韩字符或全角标点时，
#      某些 shell 在非 UTF-8 locale 下会把多字节字符的首字节吃进变量名，
#      配合 set -u 直接报 "unbound variable" 并中止。
#   2. 只用 find 与 grep（+ sh 内建）。不依赖 awk/sed/sort/uniq/mktemp/cut/tr/dirname/basename，
#      因为受限环境里它们可能不可用。
#
# 已知限制：
#   - 只校验「带文件名」的引用。形如 <code>:645</code> 的简写（依赖上文提到的文件名）
#     无法自动校验，脚本会报出这类引用的数量。
#   - 索引按行处理，因此**路径里不能有换行**；含空格可以（按整行读取）。
# ============================================================================
set -u

# ---- 可调项 ---------------------------------------------------------------
# 要校验的引用扩展名（正则片段）。要覆盖别的语言，在这里加。
DEFAULT_EXT_RE='java|md|xml|json|sh|py|js|mjs|ts|tsx|go|rs|c|h|cpp|hpp|cc|cs|rb|php|kt|kts|scala|sql|yaml|yml|toml|gradle|groovy|vue|svelte|dart|swift|m|mm|pl|lua|ex|exs|erl|hs|clj|proto'
# 建索引时要跳过的目录名（不含通配符，因此可以安全地由变量拼进 find）
PRUNE_NAMES='-name .git -o -name target -o -name node_modules -o -name build -o -name dist -o -name out -o -name .venv -o -name venv -o -name __pycache__ -o -name .idea -o -name .gradle -o -name .mvn'

# ---- 0. 参数 --------------------------------------------------------------
VERBOSE=0
EXT_RE=${DEFAULT_EXT_RE}
ROOTS_GIVEN=""

while [ $# -gt 0 ]; do
    case "${1}" in
        -h|--help)
            echo "用法: sh ${0} [-v] [-x 扩展名,扩展名] [文档目录] [源码根...]"
            echo "  文档目录不给时用当前目录（当前目录没有 .html 才回退到脚本所在目录的上一级）；"
            echo "  源码根不给时从文档目录向上自动探测（找 .git 或常见构建文件）。"
            echo "  脚本住在技能目录，调用时请显式给文档目录；选项写在位置参数之前。"
            echo "  -v        额外列出「引用注释/注解行」的条目（默认只汇总数量）。"
            echo "  -x LIST   只校验这些扩展名的引用，逗号分隔。默认覆盖常见数十种语言。"
            echo "  多仓库工作区请显式给出多个源码根："
            echo "      sh ${0} docs repo-a repo-b"
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -x)
            if [ $# -lt 2 ]; then
                echo "错误：-x 后面要跟扩展名列表。" >&2
                exit 2
            fi
            # 用 shell 内建把逗号列表拼成正则的 | 分支（不引入 tr，保持只依赖 find/grep）
            EXT_RE=""
            OLD_IFS=${IFS}
            IFS=','
            for one in ${2}; do
                if [ -z "${one}" ]; then
                    continue
                fi
                if [ -z "${EXT_RE}" ]; then
                    EXT_RE="${one}"
                else
                    EXT_RE="${EXT_RE}|${one}"
                fi
            done
            IFS=${OLD_IFS}
            if [ -z "${EXT_RE}" ]; then
                echo "错误：-x 的扩展名列表是空的。" >&2
                exit 2
            fi
            shift 2
            ;;
        -*)
            echo "错误：未知选项 ${1}" >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done

# ---- 1. 文档目录 -----------------------------------------------------------
# 优先用位置参数；否则用当前目录；再否则用脚本自身所在目录的上一级。
# （最后这档是「脚本与文档同放」的老布局兜底：脚本住在技能目录里时，那一级是技能目录而不是文档目录。）
case "${0}" in
    */*) SCRIPT_DIR=${0%/*} ;;
    *)   SCRIPT_DIR=. ;;
esac
SCRIPT_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}" && pwd) || exit 2

HTML_COUNT=$(ls "${PWD}"/*.html 2>/dev/null | grep -c "" )
if [ "${HTML_COUNT}" -gt 0 ]; then
    DOC_DIR=${1:-${PWD}}
else
    DOC_DIR=${1:-$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)}
fi
if [ $# -gt 0 ]; then
    shift
fi

if [ ! -d "${DOC_DIR}" ]; then
    echo "找不到文档目录：${DOC_DIR}" >&2
    exit 2
fi
DOC_DIR=$(CDPATH= cd -- "${DOC_DIR}" && pwd)
DOC_HTML=$(ls "${DOC_DIR}"/*.html 2>/dev/null | grep -c "")
if [ "${DOC_HTML}" -eq 0 ]; then
    echo "错误：${DOC_DIR} 下没有任何 .html 文件。" >&2
    exit 2
fi

# ---- 2. 源码根 -------------------------------------------------------------
# 显式给出的都收下；没给就自动探测。
ROOTS=""
if [ $# -gt 0 ]; then
    for cand in "$@"; do
        if [ -d "${cand}" ]; then
            ROOTS="${ROOTS}
$(CDPATH= cd -- "${cand}" && pwd)"
        else
            echo "警告：源码根不存在，已忽略：${cand}" >&2
        fi
    done
fi

if [ -z "${ROOTS}" ]; then
    # 从文档目录逐级向上找「像仓库根」的目录：含 .git 或常见构建文件
    probe=${DOC_DIR}
    depth=0
    while [ "${depth}" -lt 8 ]; do
        if [ -d "${probe}/.git" ] || [ -f "${probe}/pom.xml" ] || [ -f "${probe}/package.json" ] \
           || [ -f "${probe}/go.mod" ] || [ -f "${probe}/Cargo.toml" ] || [ -f "${probe}/pyproject.toml" ] \
           || [ -f "${probe}/setup.py" ] || [ -f "${probe}/build.gradle" ] || [ -f "${probe}/Makefile" ] \
           || [ -f "${probe}/composer.json" ] || [ -f "${probe}/Gemfile" ]; then
            ROOTS="${ROOTS}
${probe}"
            break
        fi
        parent=${probe%/*}
        if [ -z "${parent}" ] || [ "${parent}" = "${probe}" ]; then
            break
        fi
        probe=${parent}
        depth=$((depth + 1))
    done
fi

if [ -z "${ROOTS}" ]; then
    echo "找不到源码根（从 ${DOC_DIR} 向上探测 8 层，没发现 .git 或常见构建文件）。" >&2
    echo "" >&2
    echo "请显式指定（注意某些环境不允许 VAR=值 前缀写法）：" >&2
    echo "    sh ${0} <文档目录> <源码根> [更多源码根...]" >&2
    exit 2
fi

echo "文档目录   ${DOC_DIR}"
printf '源码根    '
first=1
for root in ${ROOTS}; do
    if [ "${first}" = "1" ]; then
        printf '%s\n' "${root}"
        first=0
    else
        printf '          %s\n' "${root}"
    fi
done
echo ""

# ---- 3. 建一次文件名索引 ---------------------------------------------------
# ★ 只索引「最外层」的源码根：若一个根被另一个根包含（例如工作区根 . 与它下面的 Jellyfish/），
#   两者都索引会让同一文件在索引里出现两次，于是所有「按后缀匹配」的引用都会被误报成歧义。
#   嵌套的根仍然保留在 ROOTS 里参与「逐个根试拼」，只是不重复建索引。
INDEX_ROOTS=""
for root in ${ROOTS}; do
    nested=0
    for other in ${ROOTS}; do
        if [ "${root}" != "${other}" ]; then
            case "${root}/" in
                "${other}/"*) nested=1 ;;
            esac
        fi
    done
    if [ "${nested}" = "0" ]; then
        case "${INDEX_ROOTS}
" in
            *"
${root}
"*) ;;
            *) INDEX_ROOTS="${INDEX_ROOTS}
${root}" ;;
        esac
    fi
done

TMP_BASE=${TMPDIR:-/tmp}
TMP_ALL="${TMP_BASE}/.verify-refs.$$"
TMP_INDEX="${TMP_ALL}.index"
TMP_REFS="${TMP_ALL}.refs"
TMP_SEEN="${TMP_ALL}.seen"
trap 'rm -f "${TMP_ALL}" "${TMP_INDEX}" "${TMP_REFS}" "${TMP_SEEN}" "${TMP_ALL}.raw"' 0 1 2 3 15

: > "${TMP_INDEX}"
for root in ${INDEX_ROOTS}; do
    # 一次遍历，再按扩展名筛：比每个扩展名跑一次 find 快得多
    find "${root}" \( ${PRUNE_NAMES} \) -prune -o -type f -print >> "${TMP_ALL}.raw" 2>/dev/null
    grep -E "\.(${EXT_RE})\$" "${TMP_ALL}.raw" >> "${TMP_INDEX}" 2>/dev/null
    : > "${TMP_ALL}.raw"
done
rm -f "${TMP_ALL}.raw"

INDEX_COUNT=$(grep -c "" "${TMP_INDEX}" 2>/dev/null)
echo "索引文件数 ${INDEX_COUNT}"
printf '索引根    '
first=1
for root in ${INDEX_ROOTS}; do
    if [ "${first}" = "1" ]; then
        printf '%s\n' "${root}"
        first=0
    else
        printf '          %s\n' "${root}"
    fi
done
echo ""

# ---- 4. 抽出引用并逐条校验 -------------------------------------------------
REF_PATTERN="[A-Za-z0-9_\$./-]+\.(${EXT_RE}):[0-9]+(-[0-9]+)?"

grep -rhoE "${REF_PATTERN}" "${DOC_DIR}"/*.html 2>/dev/null > "${TMP_REFS}"
: > "${TMP_SEEN}"

total=0
located=0
missing=0
out_of_range=0
suspicious_other=0
suspicious_comment=0
ambiguous=0
printable=""

while IFS= read -r ref; do
    [ -z "${ref}" ] && continue

    # 同一引用在多页出现只校验一次
    if grep -qFx -- "${ref}" "${TMP_SEEN}" 2>/dev/null; then
        continue
    fi
    echo "${ref}" >> "${TMP_SEEN}"

    total=$((total + 1))

    name=${ref%:*}
    spec=${ref##*:}
    start=${spec%%-*}
    end=${spec##*-}

    # ---- 4.1 定位文件：逐个源码根试拼，再按路径后缀匹配 ----------------------
    path=""
    for root in ${ROOTS}; do
        if [ -f "${root}/${name}" ]; then
            path="${root}/${name}"
            break
        fi
    done

    if [ -z "${path}" ]; then
        # 按「路径结尾」匹配。多候选时静默取第一个会校验到别的文件上，
        # 于是报出假的空行/越界；这里如实报「歧义」并提示补全路径。
        # 用 case 的引号模式做字面量后缀匹配，避免为正则转义引入 sed。
        hits=0
        cand=""
        while IFS= read -r line; do
            [ -z "${line}" ] && continue
            case "${line}" in
                */"${name}") hits=$((hits + 1)); cand="${line}" ;;
            esac
        done <<EOF
$(grep -F "/${name}" "${TMP_INDEX}" 2>/dev/null)
EOF
        if [ "${hits}" -gt 1 ]; then
            ambiguous=$((ambiguous + 1))
            printable="${printable}
歧义     ${ref}  （${hits} 个同名文件；请把路径补到能唯一确定的一层）"
            continue
        fi
        if [ "${hits}" = "1" ]; then
            path="${cand}"
        fi
    fi

    if [ -z "${path}" ] || [ ! -f "${path}" ]; then
        missing=$((missing + 1))
        printable="${printable}
缺文件   ${ref}"
        continue
    fi

    located=$((located + 1))

    # ---- 4.2 行数与越界 -----------------------------------------------------
    lines=$(grep -c "" "${path}" 2>/dev/null)
    [ -z "${lines}" ] && lines=0

    if [ "${start}" -gt "${lines}" ] 2>/dev/null; then
        out_of_range=$((out_of_range + 1))
        printable="${printable}
越界     ${ref}  （文件仅 ${lines} 行）"
        continue
    fi
    if [ "${end}" -gt "${lines}" ] 2>/dev/null; then
        out_of_range=$((out_of_range + 1))
        printable="${printable}
越界     ${ref}  （区间末端 ${end} > 文件 ${lines} 行）"
        continue
    fi

    # ---- 4.3 取第 start 行 --------------------------------------------------
    numbered=$(grep -n "" "${path}" 2>/dev/null | grep -m1 "^${start}:")
    text=${numbered#*:}

    # ---- 4.4 可疑判定 -------------------------------------------------------
    reason=""
    if echo "${text}" | grep -qE '^[[:space:]]*$'; then
        reason="首行为空行"
    else
        case "${name}" in
            *.java|*.kt|*.kts|*.scala|*.c|*.h|*.cpp|*.hpp|*.cc|*.cs|*.php|*.swift|*.dart|*.ts|*.tsx|*.js|*.mjs|*.vue|*.svelte)
                if echo "${text}" | grep -qE '^[[:space:]]*(//|/\*|\*)'; then
                    reason="首行是注释行（引用注释时可忽略）"
                elif echo "${text}" | grep -qE '^[[:space:]]*(@|import[[:space:]]|package[[:space:]]|use[[:space:]]|from[[:space:]])'; then
                    reason="首行是注解或 import/package"
                elif echo "${text}" | grep -qE '^[[:space:]]*(\}|\);?|\{)[[:space:]]*$'; then
                    reason="首行是纯括号"
                fi
                ;;
            *.go|*.rs)
                if echo "${text}" | grep -qE '^[[:space:]]*(//|/\*|\*)'; then
                    reason="首行是注释行（引用注释时可忽略）"
                elif echo "${text}" | grep -qE '^[[:space:]]*(import[[:space:]]|package[[:space:]]|use[[:space:]])'; then
                    reason="首行是 import/package"
                elif echo "${text}" | grep -qE '^[[:space:]]*(\}|\)|\{)[[:space:]]*$'; then
                    reason="首行是纯括号"
                fi
                ;;
            *.py|*.rb|*.sh|*.pl|*.yaml|*.yml|*.toml)
                if echo "${text}" | grep -qE '^[[:space:]]*#'; then
                    reason="首行是注释行（引用注释时可忽略）"
                fi
                ;;
            *.xml|*.html|*.md)
                if echo "${text}" | grep -qE '^[[:space:]]*(<!--|-->)'; then
                    reason="首行是 XML/HTML 注释"
                fi
                ;;
        esac
    fi

    if [ -n "${reason}" ]; then
        case "${reason}" in
            首行是注释行*|首行是注解*|首行是\ import*|首行是\ XML*)
                # 引注释/注解是常见且有意的写法，默认只计数
                suspicious_comment=$((suspicious_comment + 1))
                if [ "${VERBOSE}" = "1" ]; then
                    printable="${printable}
注释引用 ${ref}  （${reason}）"
                fi
                ;;
            *)
                suspicious_other=$((suspicious_other + 1))
                printable="${printable}
可疑     ${ref}  （${reason}）"
                ;;
        esac
    fi
done < "${TMP_REFS}"

# 简写引用数量（形如 <code>:645</code>，没有文件名，无法自动校验）
shorthand=$(grep -rhoE '<code>:[0-9]+' "${DOC_DIR}"/*.html 2>/dev/null | grep -c "")

# ---- 5. 输出与汇总 --------------------------------------------------------
if [ -n "${printable}" ]; then
    shown=$(echo "${printable}" | grep -c "")
    if [ "${shown}" -gt 60 ]; then
        # 打印上限：数量极大时（通常是源码根选错）逐条列出会把关键提示淹没
        echo "${printable}" | grep -v '^$' | grep -m60 ""
        echo ""
        echo "…另有 $((shown - 61)) 条未列出（数量这么大，先看文末的提示，多半是源码根选错了）"
    else
        echo "${printable}" | grep -v '^$'
    fi
    echo ""
fi

echo "─────────────────────────────────────────────"
echo "带文件名的引用  ${total}（已定位 ${located}）"
echo "缺文件          ${missing}"
echo "越界            ${out_of_range}"
echo "可疑            ${suspicious_other}（首行为空行或纯括号，说明行号可能偏了）"
echo "歧义            ${ambiguous}（同名文件有多个候选，本脚本无法判定；不算硬错误，但建议补路径）"
echo "引用注释/注解行  ${suspicious_comment}（属预期；加 -v 可列出）"
echo "另有「只有行号」的简写引用 ${shorthand} 处，本脚本无法自动校验"
echo "  （形如 <code>:645</code>，依赖上文提到的文件名；要校验得先改写成带文件名的形式）"

if [ "${out_of_range}" -gt 0 ] || [ "${missing}" -gt 0 ]; then
    echo ""
    echo "结论：存在越界或缺文件，必须修。"
    echo ""
    # 大量「缺文件」往往不是文档的问题，而是源码根选错了——典型情形：文档自己是一个
    # git 仓库，于是自动探测停在文档仓库，而引用指向的是它旁边的源码仓库。
    # 这种情况必须明确提示，否则一个选错的根会伪装成上千条「缺文件」。
    if [ "${missing}" -gt 10 ]; then
        echo "提示：缺文件数量较多（${missing}），先确认源码根是不是选错了。"
        echo "      本次索引只覆盖 ${INDEX_COUNT} 个文件；若这个数明显偏小（少于文档的引用条数），"
        echo "      基本可以断定根选错了——特别是「文档独立成仓库、源码在它旁边」的布局。"
        echo "      请显式给出源码根（可以给多个，按优先级从具体到宽泛）："
        echo "          sh ${0} <文档目录> <源码根> [更多源码根...]"
        exit 1
    fi
    exit 1
fi

echo ""
echo "结论：无越界、无缺文件。"
if [ "${suspicious_other}" -gt 0 ]; then
    echo "      上面的「可疑」建议逐条确认是否行号偏了。"
fi
if [ "${ambiguous}" -gt 0 ]; then
    echo "      上面的「歧义」意味着这几条引用根本没被校验，建议补全路径后重跑。"
fi
exit 0
