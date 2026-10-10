#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-docs.py —— 文档集合的内部一致性校验

校验项（全部由**侧栏**推导，不需要维护第二份页面清单）：

  1. 侧栏：每页的侧栏条目与分组逐字相同，且恰好一个 aria-current 指向本页
  2. 侧栏链接文字里的编号  = 目标文件名编号
  3. <title> / <h1> / 面包屑 的编号 = 本页文件名编号
  4. 所有内部链接（href / src）指向的文件存在
  5. 「NN 页」引用指向存在的页号
  6. 图 / 表编号的前缀 = 本页编号（跨页引用只提示）
  7. 翻页的上一页 / 下一页与侧栏顺序一致
  8. 每页都有页脚与脚本引用（缺了会让读者少一截）

用法：
    python3 check-docs.py [文档目录]
    文档目录缺省为当前目录。

退出码：0 = 全部一致；1 = 有错误；2 = 环境问题（找不到文档目录或没有任何 .html）
"""

import os
import re
import sys

# ---- 侧栏正则：nav 块本身，以及块内的链接与分组标题 -------------------------
SIDEBAR_RE = re.compile(r'<nav class="sidebar"[^>]*>(.*?)</nav>', re.S)
NAV_LINK_RE = re.compile(r'<li><a href="([^"]+)"([^>]*)>([^<]*)</a></li>')
NAV_GROUP_RE = re.compile(r'<div class="nav-group">([^<]*)</div>')
# 链接文字以两位编号开头（「01 项目概览」）——用于与目标文件名核对
LABEL_NUM_RE = re.compile(r'^(\d\d)\s')
# 文件名编号
FILE_NUM_RE = re.compile(r'^(\d\d)-')
# 页内出现的「NN 页」引用
PAGE_REF_RE = re.compile(r'(?<!\d)(\d\d) 页')
# 图 / 表编号
FIG_RE = re.compile(r'(图 |表 )(\d\d)-(\d+)')
# 本页编号出现在这三处
TITLE_RE = re.compile(r'<title>(\d\d)\s')
H1_RE = re.compile(r'<h1>(\d\d)\s')
CRUMB_RE = re.compile(r'<span class="sep">/</span><span>(\d\d)\s')
# 翻页
PAGER_RE = re.compile(r'<nav class="pager"[^>]*>(.*?)</nav>', re.S)
PAGER_LINK_RE = re.compile(r'<a class="(prev|next)[^"]*" href="([^"]+)"')
# 内部资源引用
ASSET_RE = re.compile(r'(?:href|src)="((?!https?:|#|mailto:)[^"]+)"')


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def sidebar_of(text):
    """抽出侧栏的 (组标题序列, 链接序列)。链接序列是 [(href, label, is_current)]。"""
    block = SIDEBAR_RE.search(text)
    if not block:
        return None
    body = block.group(1)
    groups = NAV_GROUP_RE.findall(body)
    links = []
    for href, attrs, label in NAV_LINK_RE.findall(body):
        links.append((href, label.strip(), 'aria-current' in attrs))
    return groups, links


def main():
    doc_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    doc_dir = os.path.abspath(doc_dir)
    if not os.path.isdir(doc_dir):
        print('错误：不是目录：%s' % doc_dir, file=sys.stderr)
        return 2

    files = sorted(f for f in os.listdir(doc_dir)
                   if f.endswith('.html') and os.path.isfile(os.path.join(doc_dir, f)))
    if not files:
        print('错误：%s 下没有任何 .html 文件。' % doc_dir, file=sys.stderr)
        return 2

    errors = []
    warnings = []

    # ---- 用第一个页面（按文件名排序，即 index.html 之后的内容页）的侧栏作为基准 -
    texts = {}
    for name in files:
        texts[name] = read(os.path.join(doc_dir, name))

    base_name = None
    base_side = None
    for name in files:
        side = sidebar_of(texts[name])
        if side:
            base_name, base_side = name, side
            break
    if base_side is None:
        print('错误：所有页面都找不到 <nav class="sidebar">，无法推导页面清单。', file=sys.stderr)
        return 2

    base_groups, base_links = base_side
    order = [href for href, _label, _cur in base_links]

    # 页号集合：来自侧栏的目标文件名
    num_of_file = {}
    for href in order:
        m = FILE_NUM_RE.match(href)
        page_num = m.group(1) if m else '00'
        num_of_file[href] = page_num
    known_nums = set(num_of_file.values())

    # ---- 1. 侧栏一致性 + 2. 链接文字编号 ------------------------------------
    for name in files:
        side = sidebar_of(texts[name])
        if side is None:
            errors.append('%s：缺少侧栏（nav.sidebar）' % name)
            continue
        groups, links = side
        if groups != base_groups:
            errors.append('%s：侧栏分组与基准页（%s）不一致：%s' % (name, base_name, groups))
        got = [(h, lb) for h, lb, _c in links]
        want = [(h, lb) for h, lb, _c in base_links]
        if got != want:
            errors.append('%s：侧栏条目与基准页（%s）不一致' % (name, base_name))
            for i, (a, b) in enumerate(zip(got, want)):
                if a != b:
                    errors.append('    #%d 本页 %s ／ 基准 %s' % (i + 1, a, b))
            if len(got) != len(want):
                errors.append('    条目数：本页 %d ／ 基准 %d' % (len(got), len(want)))

        cur = [h for h, _lb, c in links if c]
        if len(cur) != 1:
            errors.append('%s：aria-current="page" 有 %d 个（应为 1）' % (name, len(cur)))
        elif cur[0] != name:
            errors.append('%s：aria-current 指向 %s' % (name, cur[0]))

        for href, label in got:
            m = LABEL_NUM_RE.match(label)
            if not m:
                continue
            if m.group(1) != num_of_file.get(href, '00'):
                errors.append('%s：侧栏「%s」的编号 %s ≠ 目标文件编号 %s'
                              % (name, label, m.group(1), num_of_file.get(href, '00')))

    # ---- 3. 本页编号出现在 title / h1 / 面包屑 -------------------------------
    for name in files:
        own = num_of_file.get(name, '00')
        if own == '00':
            continue        # 首页没有编号
        text = texts[name]
        for pat, where in ((TITLE_RE, '<title>'), (H1_RE, '<h1>'), (CRUMB_RE, '面包屑')):
            m = pat.search(text)
            if not m:
                errors.append('%s：%s 里找不到本页编号' % (name, where))
            elif m.group(1) != own:
                errors.append('%s：%s 的编号 %s ≠ 本页编号 %s' % (name, where, m.group(1), own))

    # ---- 4. 内部链接与资源存在 ---------------------------------------------
    for name in files:
        for target in ASSET_RE.findall(texts[name]):
            target = target.split('#')[0]
            if not target:
                continue
            if os.path.exists(os.path.join(doc_dir, target)):
                continue
            if '/vendor/' in target or target.startswith('vendor/'):
                # vendor 目录按设计可以为空（第三方库按需获取），不算错误
                warnings.append('%s：引用了 %s（vendor 库按需获取，缺失属预期）' % (name, target))
            else:
                errors.append('%s：引用的文件不存在：%s' % (name, target))

    # ---- 5. 「NN 页」引用指向存在的页号 ------------------------------------
    for name in files:
        for num in PAGE_REF_RE.findall(texts[name]):
            if num not in known_nums:
                errors.append('%s：正文引用了「%s 页」，但没有这个页号' % (name, num))

    # ---- 6. 图 / 表编号前缀 = 本页编号 -------------------------------------
    for name in files:
        own = num_of_file.get(name, '00')
        for kind, num, _idx in FIG_RE.findall(texts[name]):
            if num != own:
                warnings.append('%s（本页 %s）：%s%s-%s 的编号不是本页号，若是跨页引用可忽略'
                                % (name, own, kind, num, _idx))

    # ---- 7. 翻页与侧栏顺序一致 --------------------------------------------
    for name in files:
        if name not in order:
            continue
        i = order.index(name)
        m = PAGER_RE.search(texts[name])
        if not m:
            errors.append('%s：缺少翻页（nav.pager）' % name)
            continue
        found = dict(PAGER_LINK_RE.findall(m.group(1)))
        if i == 0:
            want_prev = order[0]                       # 首页：上一页指向自己（禁用态）
            want_next = order[1] if len(order) > 1 else order[0]
        else:
            want_prev = order[i - 1]
            want_next = order[i + 1] if i + 1 < len(order) else order[0]
        if found.get('prev') != want_prev:
            errors.append('%s：上一页指向 %s，按侧栏顺序应为 %s' % (name, found.get('prev'), want_prev))
        if found.get('next') != want_next:
            errors.append('%s：下一页指向 %s，按侧栏顺序应为 %s' % (name, found.get('next'), want_next))

    # ---- 8. 页脚与脚本引用 -------------------------------------------------
    for name in files:
        text = texts[name]
        if '<footer class="footer">' not in text:
            warnings.append('%s：缺少页脚（说明本页依据）' % name)
        if 'assets/app.js' not in text:
            errors.append('%s：没有引用 assets/app.js（导航高亮、行号、图表都会失效）' % name)

    # ---- 输出 -------------------------------------------------------------
    if errors:
        print('=== 错误 %d 处 ===' % len(errors))
        for line in errors:
            print('  ' + line)
        print('')

    if warnings:
        print('=== 提示 %d 处（不阻断） ===' % len(warnings))
        for line in warnings[:40]:
            print('  ' + line)
        if len(warnings) > 40:
            print('  …另有 %d 处' % (len(warnings) - 40))
        print('')

    print('─────────────────────────────────────────────')
    print('页面数        %d' % len(files))
    print('侧栏条目数    %d（分组 %d 个）' % (len(order), len(base_groups)))
    print('错误          %d' % len(errors))
    print('提示          %d' % len(warnings))

    if errors:
        print('')
        print('结论：存在不一致，必须修。')
        return 1

    print('')
    print('结论：编号、侧栏、翻页、链接全部一致。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
