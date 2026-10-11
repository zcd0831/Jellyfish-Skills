#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renumber-pages.py —— 多页面文档的批量重编号 / 重排（两段式，防碰撞）

用途：给页面插入、删除、重排之后，把「页号」在所有出现的地方一次性改对。
     涉及的位置有八类，全都要改，漏一类就会留下死引用：

      1. 侧栏（每个页面里的 nav.sidebar）——整块重建
      2. 翻页（nav.pager）——整块重建
      3. 链接目标文件名 href="NN-slug.html"
      4. 链接文字里的页号 <a href="03-x.html">03 标题</a>
      5. 裸数字链接文字 <a href="03-x.html">03</a>
      6. 首页卡片徽标 <div class="card-no">03</div>
      7. 图 / 表编号（图 03-2 / 表 07-1）
      8. 编号区间（22–27）
      9. 页码引用（「22 页」）
     10. 本页自己的编号（<title> / <h1> / 面包屑）

★ 规则覆盖不到、必须靠「残留检查 + 人眼」兜底的位置：
  图表（mermaid）内部的节点标签、散文里的「15/16 两页」、以及任何非结构化的数字。
  脚本跑完会列这些残留，不要跳过那一段。

★ 为什么必须两段式：页号会互相碰撞（旧 25 恰好是新 21）。逐条顺序替换时，
  一条规则的输出会被后面的规则再次命中，于是有的页号被改了两次。
  做法是：每完成一处替换就换成**不含数字**的占位符，全部规则跑完再统一还原。

★ 为什么规则有顺序：范围更大、更具体的规则必须先跑。典型例子是编号区间
  「22–27 页」——若先跑「NN 页」规则，会把「27 页」先吃掉，区间只剩半截。

用法：
    # 1) 先导出一份当前状态的映射模板，按它编辑
    python3 renumber-pages.py --dump-map > map.txt

    # 2) 编辑 map.txt：行序 = 最终阅读顺序

    # 3) 先 dry-run 看统计与样本，确认无误再 --apply
    python3 renumber-pages.py --map-file map.txt [文档目录]
    python3 renumber-pages.py --map-file map.txt --apply [文档目录]

map.txt 格式（`#` 开头与空行忽略）：

    新编号 新文件名 旧文件名 [分组]
    ---------------------------------
    00 index.html index.html
    01 01-overview.html 01-overview.html
    07 07-tools-io.html 18-tools-io.html
    12 12-assembly.html NEW 二、内核机制      ← 新增页：旧文件名写 NEW，且必须给分组

- 旧文件名写磁盘上现在的名字；新增页写 NEW（该文件必须已存在）。
- 分组只在「新增页」或「要换组」时必须给；其余从当前侧栏继承。
- 页面的侧栏文字 = 原侧栏文字（去掉旧编号）拼上新编号；新增页取它的 <h1>。

退出码：0 = 成功（含 dry-run）；1 = 有错误；2 = 环境问题
"""

import os
import re
import sys

SIDEBAR_RE = re.compile(r'<nav class="sidebar"[^>]*>.*?</nav>', re.S)
SIDEBAR_BODY_RE = re.compile(r'<nav class="sidebar"[^>]*>(.*?)</nav>', re.S)
PAGER_RE = re.compile(r'<nav class="pager"[^>]*>.*?</nav>', re.S)
NAV_LINK_RE = re.compile(r'<li><a href="([^"]+)"([^>]*)>([^<]*)</a></li>')
NAV_GROUP_RE = re.compile(r'<div class="nav-group">([^<]*)</div>')
FILE_NUM_RE = re.compile(r'^(\d\d)-')
H1_RE = re.compile(r'<h1>(?:\d\d\s+)?([^<]*)</h1>')

PAGES_ALL = re.compile(r'^(?:\d\d-[a-z0-9-]+|index)\.html$')


class Pending(object):
    """占位符登记本：把最终文本换成不含数字的占位符，避免被后续规则二次匹配。"""

    def __init__(self):
        self.items = []

    def hold(self, final):
        self.items.append(final)
        index = len(self.items)
        name = ''
        while index:
            index, rem = divmod(index - 1, 26)
            name = chr(ord('a') + rem) + name
        return '\x00' + name + '\x00'

    def restore(self, text):
        for i, final in enumerate(self.items):
            index = i + 1
            name = ''
            while index:
                index, rem = divmod(index - 1, 26)
                name = chr(ord('a') + rem) + name
            text = text.replace('\x00' + name + '\x00', final)
        return text


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def write(path, text):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def current_state(doc_dir, files):
    """从当前侧栏读出：阅读顺序、每页的分组与侧栏文字。"""
    order, group_of, label_of = [], {}, {}
    for name in files:
        text = read(os.path.join(doc_dir, name))
        body = SIDEBAR_BODY_RE.search(text)
        if not body:
            continue
        body = body.group(1)
        # 按出现顺序把「分组标题」与「链接」穿成一条线：遇到分组就记下，之后的链接都归它
        group = None
        cursor = 0
        tokens = []
        for m in NAV_GROUP_RE.finditer(body):
            tokens.append((m.start(), 'group', m.group(1)))
        for m in NAV_LINK_RE.finditer(body):
            tokens.append((m.start(), 'link', (m.group(1), m.group(2), m.group(3))))
        tokens.sort(key=lambda t: t[0])
        for _pos, kind, payload in tokens:
            if kind == 'group':
                group = payload
            else:
                href, _attrs, label = payload
                if href in label_of:
                    continue
                order.append(href)
                group_of[href] = group
                label_of[href] = label.strip()
        return order, group_of, label_of
    return order, group_of, label_of


def parse_map(path):
    entries = []
    with open(path, encoding='utf-8') as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) < 3:
                raise ValueError('map.txt 第 %d 行格式不对（至少要有 新编号 新文件名 旧文件名）：%s'
                                 % (lineno, line))
            new_num, new_file, old_file = parts[0], parts[1], parts[2]
            group = ' '.join(parts[3:]) if len(parts) > 3 else None
            if not re.match(r'^\d\d$', new_num):
                raise ValueError('map.txt 第 %d 行：新编号必须是两位数字：%s' % (lineno, new_num))
            if not PAGES_ALL.match(new_file):
                raise ValueError('map.txt 第 %d 行：新文件名必须是 NN-slug.html 形式：%s'
                                 % (lineno, new_file))
            entries.append({'new_num': new_num, 'new_file': new_file,
                            'old_file': old_file, 'group': group})
    if not entries:
        raise ValueError('map.txt 里没有任何条目。')
    return entries


def build_sidebar(order, label_of, group_of, current_file):
    """按最终顺序重建侧栏；分组变化处插入 nav-group 标题。

    分组为 None 的条目（通常是首页）自成一段 nav-list，不带分组标题——
    这与「首页单独一个列表、之后每组一个列表」的结构一致。
    """
    # 第一行不带缩进：SIDEBAR_RE 从 <nav 开始匹配，它前面的缩进会原样留在正文里，
    # 若这里再补缩进就会叠加（4 空格变 6 空格）。其余行的缩进与原文风格保持一致。
    lines = ['<nav class="sidebar" id="sidebar" aria-label="文档导航">',
             '    <div class="sidebar-title">文档目录</div>']
    # 用一个不可能等于任何分组名的哨兵做初值，保证第一次循环一定进入分支、把 <ul> 打开
    last_group = '\x00init'
    open_list = False
    for file in order:
        group = group_of.get(file)
        if group != last_group:
            if open_list:
                lines.append('    </ul>')
                open_list = False
            if group is not None:
                lines.append('    <div class="nav-group">%s</div>' % group)
            lines.append('    <ul class="nav-list">')
            open_list = True
            last_group = group
        if file == current_file:
            lines.append('      <li><a href="%s" aria-current="page">%s</a></li>'
                         % (file, label_of[file]))
        else:
            lines.append('      <li><a href="%s">%s</a></li>' % (file, label_of[file]))
    if open_list:
        lines.append('    </ul>')
    lines.append('  </nav>')
    return '\n'.join(lines)


def build_pager(order, label_of, current_file):
    if current_file not in order:
        return None
    i = order.index(current_file)
    if i == 0:
        prev = ('      <a class="prev disabled" href="%s">'
                '<span class="pager-dir">上一页</span>已是首页</a>' % order[0])
        nxt_file = order[1] if len(order) > 1 else order[0]
    else:
        prev = ('      <a class="prev" href="%s"><span class="pager-dir">上一页</span>%s</a>'
                % (order[i - 1], label_of[order[i - 1]]))
        nxt_file = order[i + 1] if i + 1 < len(order) else order[0]
    nxt = ('      <a class="next" href="%s"><span class="pager-dir">下一页</span>%s</a>'
           % (nxt_file, label_of[nxt_file]))
    # 同样：第一行不带缩进，避免与原文已有的缩进叠加
    return '<nav class="pager" aria-label="翻页">\n%s\n%s\n    </nav>' % (prev, nxt)


def main():
    argv = sys.argv[1:]
    dump = '--dump-map' in argv
    apply_changes = '--apply' in argv
    map_file = None
    doc_arg = None

    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--dump-map', '--apply'):
            i += 1
        elif a == '--map-file':
            if i + 1 >= len(argv):
                print('错误：--map-file 后面要跟文件名。', file=sys.stderr)
                return 2
            map_file = argv[i + 1]
            i += 2
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            doc_arg = a
            i += 1

    doc_dir = os.path.abspath(doc_arg if doc_arg else '.')
    if not os.path.isdir(doc_dir):
        print('错误：不是目录：%s' % doc_dir, file=sys.stderr)
        return 2

    files = sorted(f for f in os.listdir(doc_dir)
                   if f.endswith('.html') and os.path.isfile(os.path.join(doc_dir, f)))
    if not files:
        print('错误：%s 下没有任何 .html 文件。' % doc_dir, file=sys.stderr)
        return 2

    order, group_of, label_of = current_state(doc_dir, files)
    if not order:
        print('错误：所有页面都找不到侧栏，无法读出当前状态。', file=sys.stderr)
        return 2

    # ---- --dump-map：把当前状态导成映射模板，改起来就有据可依 ---------------
    if dump:
        print('# 由 renumber-pages.py --dump-map 生成。')
        print('# 格式：新编号 新文件名 旧文件名 [分组]')
        print('# 行序 = 最终阅读顺序。改完保存，再用 --map-file 传回来。')
        for file in order:
            num = FILE_NUM_RE.match(file)
            num = num.group(1) if num else '00'
            group = group_of.get(file)
            print('%s %s %s%s' % (num, file, file, (' ' + group) if group else ''))
        not_listed = [f for f in files if f not in order]
        if not_listed:
            print('# 注意：以下页面不在侧栏里，本工具不会处理它们：%s' % ', '.join(not_listed))
        return 0

    if not map_file:
        print('错误：需要 --map-file（或先用 --dump-map 导出一份）。', file=sys.stderr)
        return 2
    try:
        entries = parse_map(map_file)
    except (ValueError, IOError) as exc:
        print('错误：%s' % exc, file=sys.stderr)
        return 2

    # ---- 1. 组装新旧对应关系 ------------------------------------------------
    problems = []
    new_order = []
    new_pages = set()    # 本次新加入（map 里旧文件名写 NEW）的页面
    label_new = {}
    group_new = {}
    rename = {}          # 旧文件名 -> 新文件名
    num_map = {}         # 旧编号 -> 新编号

    for e in entries:
        new_file, new_num = e['new_file'], e['new_num']
        old_file = e['old_file']
        if old_file == 'NEW':
            if not os.path.isfile(os.path.join(doc_dir, new_file)):
                problems.append('新增页 %s 在磁盘上不存在' % new_file)
                continue
            text = read(os.path.join(doc_dir, new_file))
            m = H1_RE.search(text)
            label_new[new_file] = '%s %s' % (new_num, m.group(1).strip() if m else new_file)
            if not e['group']:
                problems.append('新增页 %s 必须给出分组（map.txt 行尾写分组名）' % new_file)
                continue
            group_new[new_file] = e['group']
            new_pages.add(new_file)
        else:
            if not os.path.isfile(os.path.join(doc_dir, old_file)):
                problems.append('旧文件不存在：%s' % old_file)
                continue
            old_label = label_of.get(old_file)
            if old_label is None and old_file != new_file:
                problems.append('旧文件 %s 不在当前侧栏里（无法确定它的分组）' % old_file)
            body = re.sub(r'^\d\d\s+', '', old_label) if old_label else old_file
            if old_label is None:
                m = H1_RE.search(read(os.path.join(doc_dir, old_file)))
                body = m.group(1).strip() if m else old_file
            # 编号 00 是首页，它的侧栏文字不带编号（与既有写法一致）
            label_new[new_file] = body if new_num == '00' else '%s %s' % (new_num, body)
            if e['group']:
                group_new[new_file] = e['group']
            else:
                group_new[new_file] = group_of.get(old_file)
            if old_file != new_file:
                rename[old_file] = new_file
            m = FILE_NUM_RE.match(old_file)
            if m and m.group(1) != new_num:
                num_map[m.group(1)] = new_num
        if new_file in new_order:
            problems.append('新文件名重复：%s' % new_file)
        new_order.append(new_file)

    # 旧编号的另一来源：侧栏里的编号（文件名没变但位置变了的情况）
    for idx, file in enumerate(order):
        if file in rename or file in new_order:
            continue
        problems.append('页面 %s 既不在 map 里也没被改名，会被漏掉' % file)

    if problems:
        print('=== 无法继续，请先修掉 map.txt 的这些问题 ===')
        for p in problems:
            print('  ' + p)
        return 1

    # 编号映射补充：map 里新编号与旧编号不同的，按文件名前缀记一份
    # （num_map 已在上面按 old_file 的前缀登记过，这里不再重复）

    stats = {}
    samples = {}

    def bump(key, before, after):
        stats[key] = stats.get(key, 0) + 1
        samples.setdefault(key, [])
        if len(samples[key]) < 6:
            samples[key].append('%s  →  %s' % (before, after))

    def process(current_file, content):
        pending = Pending()

        # ★ 先整体重建侧栏与翻页，并用占位符保护：
        #   重建后的文本里全是数字，若不保护会被后面的编号规则再改一遍。
        def hold_sidebar(_m):
            return pending.hold(build_sidebar(new_order, label_new, group_new, current_file))

        content, n1 = SIDEBAR_RE.subn(hold_sidebar, content, count=1)
        if n1 == 0:
            problems.append('%s：找不到侧栏' % current_file)

        pager = build_pager(new_order, label_new, current_file)
        if pager:
            content, n2 = PAGER_RE.subn(lambda _m: pending.hold(pager), content, count=1)
            if n2 == 0:
                problems.append('%s：找不到翻页' % current_file)

        # ① href 里的文件名（已重建的侧栏/翻页被占位符挡着，这里只动正文链接）
        def fix_href(m):
            target = m.group(1)
            base = target.split('#')[0]
            if base in rename:
                bump('href 文件名', base, rename[base])
                return 'href="%s%s"' % (rename[base], target[len(base):])
            return m.group(0)

        content = re.sub(r'href="([^"]+\.html)"', fix_href, content)

        # ② 链接文字里的页号：用 href 里的（新）编号覆盖文字里的旧编号
        content, n = re.subn(r'(<a href="(\d\d)-[a-z0-9-]+\.html"[^>]*>)(\d\d)( )',
                             lambda m: m.group(1) + pending.hold(m.group(2)) + m.group(4), content)
        if n:
            bump('链接文字编号', '%d 处' % n, '改为 href 的新编号')

        # ②b 裸数字链接文字：<a href="15-tui.html">15</a>
        content, nb = re.subn(
            r'(<a href="(\d\d)-[a-z0-9-]+\.html"[^>]*>)(\d\d)(</a>)',
            lambda m: m.group(1) + pending.hold(m.group(2)) + m.group(4), content)
        if nb:
            bump('裸数字链接文字', '%d 处' % nb, '改为 href 的新编号')

        # ②c 卡片徽标：<div class="card-no">15</div>（首页页面地图用）
        def fix_card_no(m):
            num = m.group(2)
            if num in num_map and num_map[num] != num:
                bump('卡片徽标', m.group(0), '%s%s%s' % (m.group(1), num_map[num], m.group(3)))
                return pending.hold('%s%s%s' % (m.group(1), num_map[num], m.group(3)))
            return m.group(0)

        content = re.sub(r'(<div class="card-no">)(\d\d)(</div>)', fix_card_no, content)

        # ③ 图 / 表编号
        def fix_fig(m):
            kind, num, tail = m.group(1), m.group(2), m.group(3)
            if num in num_map and num_map[num] != num:
                bump('图/表编号', '%s%s-%s' % (kind, num, tail),
                     '%s%s-%s' % (kind, num_map[num], tail))
                return pending.hold('%s%s-%s' % (kind, num_map[num], tail))
            return m.group(0)

        content = re.sub(r'(图 |表 )(\d\d)-(\d+)', fix_fig, content)

        # ④ 编号区间：必须在 ⑤ 之前，否则「22–27 页」的后半段会被 ⑤ 先吃掉
        def fix_range(m):
            a, b = m.group(1), m.group(2)
            na, nb = num_map.get(a, a), num_map.get(b, b)
            if (na, nb) != (a, b):
                bump('NN–MM 区间', m.group(0), '%s–%s' % (na, nb))
                return pending.hold('%s–%s' % (na, nb))
            return m.group(0)

        content = re.sub(r'(?<!\d)(\d\d)–(\d\d)(?!\d)', fix_range, content)

        # ⑤ 「NN 页」
        def fix_page_ref(m):
            num = m.group(1)
            if num in num_map and num_map[num] != num:
                bump('NN 页', m.group(0), '%s 页' % num_map[num])
                return pending.hold('%s 页' % num_map[num])
            return m.group(0)

        content = re.sub(r'(?<!\d)(\d\d) 页', fix_page_ref, content)

        # ⑥ 本页自己的编号（title / h1 / 面包屑）
        own = FILE_NUM_RE.match(current_file)
        if own:
            old_own = None
            for old, new in rename.items():
                if new == current_file:
                    m = FILE_NUM_RE.match(old)
                    old_own = m.group(1) if m else None
                    break
            if old_own is None and current_file in new_pages:
                # 新增页：没有「旧文件名」可依据，就从它自己的 <title> / <h1> 里读出当前编号。
                # 这样即使新页写的时候沿用了别的编号，也会被改成清单里指定的编号。
                for probe in (r'<title>(\d\d)\s', r'<h1>(\d\d)\s'):
                    m = re.search(probe, content)
                    if m:
                        old_own = m.group(1)
                        break
            if old_own is None:
                m = FILE_NUM_RE.match(current_file)
                old_own = m.group(1) if m else None
            new_own = own.group(1)
            if old_own and old_own != new_own:
                for pat, where in ((r'(<title>)%s ' % old_own, 'title'),
                                   (r'(<h1>)%s ' % old_own, 'h1'),
                                   (r'(<span class="sep">/</span><span>)%s ' % old_own, '面包屑')):
                    def rep(m, nn=new_own):
                        return pending.hold(m.group(1) + nn + ' ')

                    content, k = re.subn(pat, rep, content, count=1)
                    if k:
                        bump('本页编号', '%s(%s)' % (old_own, where), '%s(%s)' % (new_own, where))

        return pending.restore(content)

    # ---- 2. 生成新内容 -----------------------------------------------------
    outputs = {}
    for e in entries:
        new_file = e['new_file']
        src = e['new_file'] if e['old_file'] == 'NEW' else e['old_file']
        outputs[new_file] = process(new_file, read(os.path.join(doc_dir, src)))

    # ---- 3. 落盘：先改名再写内容（改名用两阶段，避免新旧名字相撞）-----------
    if apply_changes:
        tmp_suffix = '.renumber-tmp'
        for old, new in rename.items():
            os.rename(os.path.join(doc_dir, old), os.path.join(doc_dir, old + tmp_suffix))
        for old, new in rename.items():
            os.rename(os.path.join(doc_dir, old + tmp_suffix), os.path.join(doc_dir, new))
        for new_file, text in outputs.items():
            write(os.path.join(doc_dir, new_file), text)

    # ---- 4. 报告 -----------------------------------------------------------
    print('=== 替换统计 ===')
    for key in sorted(stats):
        print('%-16s %s' % (key, stats[key]))
    if not stats:
        print('（没有任何需要改动的地方）')
    print('')
    print('=== 样本 ===')
    for key in sorted(samples):
        print('-- %s' % key)
        for line in samples[key]:
            print('   %s' % line)
    print('')
    print('=== 页面变化 ===')
    print('文件改名      %d 个' % len(rename))
    print('页面重写      %d 个' % len(outputs))

    # 残留检查：只在「旧编号已不复存在」时才有意义。
    # 重排之后有些编号可能仍然存在（例如互换 07↔08 时两个号都还在，只是含义变了），
    # 此时扫描「旧编号」毫无意义，会把正确的新内容全报成残留。
    new_nums = set()
    for file in new_order:
        m = FILE_NUM_RE.match(file)
        if m:
            new_nums.add(m.group(1))
    vanished = [old for old in num_map if old not in new_nums]

    IGNORE_CONTEXT = [
        r'JDK\s*\d\d', r'\d\d\s*fps', r'\d\d\s*列', r'≈\s*\d\d', r':\d\d', r'\d\d:\d\d',
        r'\d\d\s*%', r'\d\d\s*KB', r'\d\d\s*MB', r'v\d\d',
    ]
    leftovers = 0
    ignored = 0
    checked = 0
    for new_file in sorted(outputs):
        text = outputs[new_file]
        for old_num in sorted(vanished):
            for m in re.finditer(r'(?<!\d)%s(?!\d)' % re.escape(old_num), text):
                checked += 1
                context = text[max(0, m.start() - 30):m.end() + 30].replace('\n', ' ')
                if any(re.search(rx, context) for rx in IGNORE_CONTEXT):
                    ignored += 1
                    continue
                leftovers += 1
                if leftovers <= 15:
                    print('  残留 %s 里的旧编号 %s：…%s…' % (new_file, old_num, context))
    print('')
    if not vanished:
        print('旧编号残留    不适用（本次没有编号被彻底废弃，新旧编号集合相同）')
    else:
        print('旧编号残留    %d 处（需人工确认：可能是版本号、行号、或规则覆盖不到的散文/图内标签）'
              % leftovers)
        print('              另有 %d 处已按非页号上下文排除（版本号/行号/比率等）' % ignored)

    if problems:
        print('')
        print('=== 问题 %d 处 ===' % len(problems))
        for p in problems[:30]:
            print('  ' + p)

    if not apply_changes:
        print('')
        print('（dry-run，未写入任何文件。确认统计与样本无误后加 --apply）')
    else:
        print('')
        # 提示里给的是脚本自己的兄弟路径：核验脚本与这个脚本同目录（技能目录），不在文档目录里
        sibling = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check-docs.py')
        print('已写入。请接着跑：python3 "%s" "%s"' % (sibling, doc_dir))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
