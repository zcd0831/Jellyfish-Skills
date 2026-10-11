/* ==========================================================================
 * 源码深度解析文档 — 交互脚本（参考实现）
 * 职责：导航折叠 / 侧栏搜索 / 当前页高亮 / 代码块行号与行锚点 / 代码复制 /
 *       语法高亮与 Mermaid 的「本地优先、CDN 兜底」加载
 *
 * 设计取舍：
 *   1. 全部使用原生 JS（ES5 语法），无构建、无框架 —— 双击本地文件即可运行。
 *      刻意不用 ES module / fetch：file:// 协议下它们会被 CORS 拦住。
 *   2. 每一个增强都先判断前置条件、失败只降级不报错：即使某个资源缺失，
 *      页面仍应保持「可读」。所以这里到处是 try/catch 与能力探测。
 *   3. 行号不写进 innerText（用伪元素 ::before 渲染），否则「复制」会把行号也带走。
 *
 * 替换第三方库时：改下面第 0 节的四个常量（本地路径 + CDN 兜底 URL）即可，
 * 并注意 CDN 版本要与本地文件版本一致，否则渲染结果会有差异。
 * ========================================================================== */
(function () {
  'use strict';

  /* ------------------------------------------------------------------
   * 0. 资源路径
   *    items 的最后一站是 CDN：本地 vendor 缺失时自动回退，保证联网时总能渲染。
   * ------------------------------------------------------------------ */
  var HLJS_LOCAL = 'assets/vendor/highlight.min.js';
  var HLJS_CDN = 'https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/highlight.min.js';
  var MERMAID_LOCAL = 'assets/vendor/mermaid.min.js';
  var MERMAID_CDN = 'https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js';

  /* ------------------------------------------------------------------
   * 1. 工具函数
   * ------------------------------------------------------------------ */
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeAttr(text) {
    return escapeHtml(text).replace(/"/g, '&quot;');
  }

  /** 复制文本：优先用异步剪贴板，file:// 下不可用时用 textarea 兜底 */
  function copyText(text, done) {
    function legacy() {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', 'readonly');
      area.style.position = 'fixed';
      area.style.top = '-1000px';
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(area);
      done(ok);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); },
          function () { legacy(); });
    } else {
      legacy();
    }
  }

  /** 依次尝试一组脚本地址，第一个加载成功的算数；全失败回调 false */
  function loadFirstScript(urls, onDone) {
    var index = 0;

    function attempt() {
      if (index >= urls.length) { onDone(false); return; }
      var url = urls[index++];
      var script = document.createElement('script');
      script.src = url;
      script.async = false;
      script.onload = function () { onDone(true); };
      script.onerror = function () {
        if (script.parentNode) { script.parentNode.removeChild(script); }
        attempt();
      };
      document.head.appendChild(script);
    }

    attempt();
  }

  /* ------------------------------------------------------------------
   * 2. 当前页高亮
   *    HTML 里已写好 aria-current，这里只做兜底：万一手工加页时漏了属性，
   *    用文件名再对一次，保证「导航一致 + 当前页高亮」不依赖人工维护。
   * ------------------------------------------------------------------ */
  function markCurrent() {
    var here = location.pathname.split('/').pop() || 'index.html';
    var links = document.querySelectorAll('.nav-list a');
    for (var i = 0; i < links.length; i++) {
      var target = links[i].getAttribute('href');
      if (target && target.split('#')[0] === here) {
        links[i].setAttribute('aria-current', 'page');
      }
    }
  }

  /* ------------------------------------------------------------------
   * 3. 移动端折叠导航
   * ------------------------------------------------------------------ */
  function initNavToggle() {
    var toggle = document.getElementById('navToggle');
    var sidebar = document.getElementById('sidebar');
    if (!toggle || !sidebar) { return; }

    toggle.addEventListener('click', function () {
      var open = sidebar.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    sidebar.addEventListener('click', function (event) {
      if (window.matchMedia('(max-width: 980px)').matches &&
          event.target && event.target.tagName === 'A') {
        sidebar.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ------------------------------------------------------------------
   * 4. 侧栏搜索过滤
   * ------------------------------------------------------------------ */
  function initNavSearch() {
    var input = document.getElementById('navSearch');
    var sidebar = document.getElementById('sidebar');
    if (!input || !sidebar) { return; }

    var items = sidebar.querySelectorAll('.nav-list li');
    var groups = sidebar.querySelectorAll('.nav-group');

    function apply() {
      var needle = input.value.trim().toLowerCase();
      var shown = 0;

      for (var i = 0; i < items.length; i++) {
        var text = (items[i].textContent || '').toLowerCase();
        var hit = needle === '' || text.indexOf(needle) >= 0;
        items[i].classList.toggle('nav-hidden', !hit);
        if (hit) { shown++; }
      }

      for (var g = 0; g < groups.length; g++) { groups[g].classList.add('nav-hidden'); }

      if (needle !== '') {
        var lists = sidebar.querySelectorAll('.nav-list');
        for (var l = 0; l < lists.length; l++) {
          var visibleInside = lists[l].querySelectorAll('li:not(.nav-hidden)').length > 0;
          var heading = lists[l].previousElementSibling;
          while (heading && !heading.classList.contains('nav-group')) {
            heading = heading.previousElementSibling;
          }
          if (heading && visibleInside) { heading.classList.remove('nav-hidden'); }
        }
      }

      var empty = sidebar.querySelector('.nav-empty');
      if (!empty) {
        empty = document.createElement('div');
        empty.className = 'nav-empty';
        empty.textContent = '没有匹配的页面';
        sidebar.appendChild(empty);
      }
      empty.style.display = shown === 0 ? 'block' : 'none';
    }

    input.addEventListener('input', apply);
    input.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { input.value = ''; apply(); input.blur(); }
    });
  }

  /* ------------------------------------------------------------------
   * 5. 表格横向滚动包裹（窄屏下防止撑破布局）
   * ------------------------------------------------------------------ */
  function wrapTables() {
    var tables = document.querySelectorAll('.content table');
    for (var i = 0; i < tables.length; i++) {
      var table = tables[i];
      if (table.parentNode && table.parentNode.classList.contains('table-scroll')) { continue; }
      var wrap = document.createElement('div');
      wrap.className = 'table-scroll';
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    }
  }

  /* ------------------------------------------------------------------
   * 6. 语法高亮（本地优先）
   * ------------------------------------------------------------------ */
  function highlightAll() {
    if (!window.hljs) { return; }
    var blocks = document.querySelectorAll('pre code');
    for (var i = 0; i < blocks.length; i++) {
      try { window.hljs.highlightElement(blocks[i]); } catch (e) { /* 高亮失败不影响阅读 */ }
    }
  }

  /* ------------------------------------------------------------------
   * 7. 把「已高亮」的代码按行拆开
   *
   * 难点：hljs 输出的是嵌套 <span> 的 HTML，而 <span> 可能跨行。
   * 直接按 innerHTML.split('\n') 会撕坏标签。所以这里做一次带标签栈的
   * 深度优先遍历：每遇到一个换行，就把当前所有未闭合标签补上闭合、
   * 下一行开头重新打开，从而保证每一行都是独立、合法的 HTML 片段。
   * ------------------------------------------------------------------ */
  function attrsOf(element) {
    var out = '';
    var attrs = element.attributes;
    for (var i = 0; i < attrs.length; i++) {
      out += ' ' + attrs[i].name + '="' + escapeAttr(attrs[i].value) + '"';
    }
    return out;
  }

  function splitLines(root) {
    var lines = [];
    var current = [];

    function flush(path) {
      var tail = '';
      for (var i = path.length - 1; i >= 0; i--) { tail += path[i].close; }
      lines.push(current.join('') + tail);
      current = [];
      for (var j = 0; j < path.length; j++) { current.push(path[j].open); }
    }

    function walk(node, path) {
      var kids = node.childNodes;
      for (var i = 0; i < kids.length; i++) {
        var child = kids[i];

        if (child.nodeType === 3) {                       // 文本节点
          var parts = child.nodeValue.split('\n');
          for (var p = 0; p < parts.length; p++) {
            if (p > 0) { flush(path); }                   // 换行 → 结束当前行
            if (parts[p] !== '') { current.push(escapeHtml(parts[p])); }
          }
        } else if (child.nodeType === 1) {                // 元素节点
          var tag = child.tagName.toLowerCase();
          if (tag === 'br') { flush(path); continue; }
          var open = '<' + tag + attrsOf(child) + '>';
          var close = '</' + tag + '>';
          current.push(open);
          walk(child, path.concat([{ open: open, close: close }]));
          current.push(close);
        }
      }
    }

    walk(root, []);
    lines.push(current.join(''));
    return lines;
  }

  /* ------------------------------------------------------------------
   * 8. 给单个代码块加行号、行锚点、锚标与复制按钮
   * ------------------------------------------------------------------ */
  function ensureWrap(pre) {
    if (pre.parentNode && pre.parentNode.classList && pre.parentNode.classList.contains('code-wrap')) {
      return pre.parentNode;
    }
    var wrap = document.createElement('div');
    wrap.className = 'code-wrap';
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    return wrap;
  }

  function addCopyButton(wrap, code) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'copy-btn';
    button.textContent = '复制';
    button.setAttribute('aria-label', '复制这段代码（不含行号）');
    wrap.appendChild(button);

    button.addEventListener('click', function () {
      // 逐行拼接：避免把行号带进复制结果（行号是伪元素，本来也不在 textContent 里，
      // 但按行取能保证多行结构与视觉一致）
      var lineEls = code.querySelectorAll('.code-line');
      var text;
      if (lineEls.length > 0) {
        var buf = [];
        for (var i = 0; i < lineEls.length; i++) { buf.push(lineEls[i].textContent); }
        text = buf.join('\n');
      } else {
        text = code.innerText || code.textContent || '';
      }

      copyText(text, function (ok) {
        button.textContent = ok ? '已复制' : '复制失败';
        button.classList.toggle('done', ok);
        window.setTimeout(function () {
          button.textContent = '复制';
          button.classList.remove('done');
        }, 1600);
      });
    });
  }

  /** 锚标：显示本块的短锚点，点击复制含完整行锚点的说明链接 */
  function addAnchorBadge(wrap, cbId, lineCount) {
    var badge = document.createElement('a');
    badge.className = 'code-anchor';
    badge.href = '#' + cbId;
    badge.textContent = '#' + cbId;
    badge.setAttribute('aria-label', '复制这个代码块的锚点链接');
    badge.title = '锚点：' + cbId + '（共 ' + lineCount + ' 行；第 N 行的锚点是 #' + cbId + '-LN）';
    badge.addEventListener('click', function (event) {
      event.preventDefault();
      var url = location.href.split('#')[0] + '#' + cbId;
      copyText(url, function (ok) {
        badge.textContent = ok ? '已复制链接' : '#' + cbId;
        window.setTimeout(function () { badge.textContent = '#' + cbId; }, 1600);
      });
    });
    wrap.appendChild(badge);
  }

  var decorated = 0;
  var firstBlockId = null;

  function decorateOne(code) {
    var pre = code.parentNode;
    if (!pre || pre.getAttribute('data-decorated') === '1') { return; }
    pre.setAttribute('data-decorated', '1');

    var wrap = ensureWrap(pre);

    // 锚点前缀：优先用 HTML 里显式写的 data-anchor / id（长期稳定——以后在页面前面
    // 插入新代码块也不会让已分享的锚点漂移），否则按本页出现顺序自动编号为 cb-N
    var cbId = pre.getAttribute('data-anchor') || pre.getAttribute('id');
    if (!cbId) { cbId = 'cb-' + (++decorated); }
    if (!firstBlockId) { firstBlockId = cbId; }

    var lines;
    try {
      lines = splitLines(code);
    } catch (e) {
      lines = null;
    }

    if (lines && lines.length > 0) {
      var html = '';
      for (var i = 0; i < lines.length; i++) {
        var n = i + 1;
        html += '<span class="code-line" id="' + cbId + '-L' + n + '" data-ln="' + n + '">'
              + lines[i] + '</span>';
      }
      code.innerHTML = html;
      wireLineAnchors(code, cbId);
    }

    addAnchorBadge(wrap, cbId, lines ? lines.length : 0);
    addCopyButton(wrap, code);
  }

  /** 点击每行左侧的行号区 → 复制该行的锚点链接 */
  function wireLineAnchors(code, cbId) {
    var lineEls = code.querySelectorAll('.code-line');
    if (lineEls.length === 0) { return; }

    // 命中区宽度跟着实际的行号留白走（移动端字号更小，留白也更窄）
    var zone = 46;
    try {
      var padding = window.getComputedStyle(lineEls[0]).paddingLeft;
      var value = parseFloat(padding);
      if (value > 0) { zone = value + 4; }
    } catch (e) { /* 取不到就用默认值 */ }

    for (var i = 0; i < lineEls.length; i++) {
      (function (line) {
        line.addEventListener('click', function (event) {
          var rect = line.getBoundingClientRect();
          if (event.clientX - rect.left > zone) { return; }   // 点在代码正文上，正常选择
          var url = location.href.split('#')[0] + '#' + line.id;
          copyText(url, function (ok) {
            if (ok) {
              line.setAttribute('data-copied', '1');
              window.setTimeout(function () { line.removeAttribute('data-copied'); }, 1200);
            }
          });
        });
      })(lineEls[i]);
    }
  }

  function decorateCodeBlocks() {
    var codes = document.querySelectorAll('pre > code');
    for (var i = 0; i < codes.length; i++) {
      try { decorateOne(codes[i]); } catch (e) { /* 单块失败不影响其余 */ }
    }
  }

  /* ------------------------------------------------------------------
   * 9. 行锚点跳转
   *    支持两种 hash：
   *      #cb-3-L45  —— 精确：第 3 个代码块的第 45 行
   *      #L45       —— 简写：本页「第一个代码块」的第 45 行
   * ------------------------------------------------------------------ */
  function flash(el) {
    el.classList.add('code-line-hit');
    window.setTimeout(function () { el.classList.remove('code-line-hit'); }, 2200);
  }

  function goToHash() {
    var raw = location.hash || '';
    if (raw.length < 2) { return; }

    var id;
    try { id = decodeURIComponent(raw.slice(1)); } catch (e) { id = raw.slice(1); }

    var el = document.getElementById(id);

    // 简写 #L45 → 落到「本页第一个代码块」的第 45 行
    if (!el && /^L\d+$/.test(id) && firstBlockId) {
      el = document.getElementById(firstBlockId + '-' + id);
    }

    if (!el) { return; }

    try {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
    } catch (e) {
      el.scrollIntoView();   // 老浏览器不支持 options
    }
    flash(el);
  }

  /* ------------------------------------------------------------------
   * 10. Mermaid：渲染，失败则降级为可读的源码块
   * ------------------------------------------------------------------ */
  function mermaidConfig() {
    var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    return {
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'base',
      fontFamily: '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
      themeVariables: dark ? {
        background: '#181d26',
        primaryColor: '#1f2531',
        primaryTextColor: '#e4e8ef',
        primaryBorderColor: '#3a4356',
        lineColor: '#8b95a6',
        secondaryColor: '#1b2a44',
        tertiaryColor: '#14302a',
        fontSize: '14px'
      } : {
        background: '#ffffff',
        primaryColor: '#e8f0fd',
        primaryTextColor: '#1d2430',
        primaryBorderColor: '#a9c4ea',
        lineColor: '#55606f',
        secondaryColor: '#f2f4f7',
        tertiaryColor: '#e6f5ee',
        fontSize: '14px'
      },
      flowchart: { curve: 'basis', htmlLabels: true, useMaxWidth: true },
      sequence: { useMaxWidth: true, wrap: true },
      state: { useMaxWidth: true },
      er: { useMaxWidth: true }
    };
  }

  /** 降级：把 mermaid 源码原样展示出来，至少让读者能看懂图在说什么 */
  function fallbackMermaid(note) {
    var nodes = document.querySelectorAll('.mermaid');
    var converted = 0;

    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (node.getAttribute('data-processed') === 'true') { continue; }

      var source = (node.textContent || '').replace(/^\s*\n/, '').replace(/[ \t]+$/, '');
      node.setAttribute('data-processed', 'true');
      node.classList.add('is-fallback');

      var pre = document.createElement('pre');
      pre.className = 'mermaid-fallback';
      pre.textContent = source;

      node.textContent = '';
      node.appendChild(pre);
      converted++;
    }

    if (converted > 0) { showOfflineNote(note); }
  }

  var offlineNoteShown = false;

  function showOfflineNote(note) {
    if (offlineNoteShown) { return; }
    offlineNoteShown = true;

    // 三种原因给三种说法：缺库、渲染报错、个别图失败
    var head = '图表以源码形式显示';
    var body = '没有找到本地图表渲染库（<code>assets/vendor/mermaid.min.js</code>），'
      + '且当前无法访问 CDN。图的内容仍完整可读，只是不会画成图形。';

    if (note === 'error') {
      head = '图表渲染失败';
      body = '渲染库已加载，但画图时报错了（多半是某张图的定义有语法问题）。'
        + '各图的源码已原样列在下方，内容不受影响。';
    } else if (note === 'partial') {
      head = '部分图表未能渲染';
      body = '渲染库对个别图处理失败，已把它们的源码原样列在下方。';
    }

    var bar = document.createElement('div');
    bar.className = 'offline-note';
    bar.innerHTML = '⚠️ <strong>' + head + '</strong>：' + body
      + ' 想彻底离线渲染，把 mermaid 10.9.1 的 <code>mermaid.min.js</code> 放进 '
      + '<code>assets/vendor/</code>（想要语法高亮再放一份 highlight.js 11.9.0 的 '
      + '<code>highlight.min.js</code>），刷新即可——版本需与 <code>assets/app.js</code> 里 CDN 兜底的一致。';

    var content = document.querySelector('.content');
    if (content && content.firstChild) {
      content.insertBefore(bar, content.firstChild);
    }
  }

  function renderMermaid() {
    if (!window.mermaid) { fallbackMermaid('missing'); return; }

    try { window.mermaid.initialize(mermaidConfig()); } catch (e) { /* 配置失败也继续试 */ }

    var nodes = document.querySelectorAll('.mermaid');
    if (nodes.length === 0) { return; }

    try {
      var result = window.mermaid.run({ querySelector: '.mermaid' });
      if (result && typeof result.then === 'function') {
        result.then(function () {
          // 逐块检查：mermaid 可能对个别块静默失败，留下未处理的节点。
          // 注意：原生 querySelectorAll 不支持 [attr!="v"] 这种非标准选择器，必须手工过滤。
          var all = document.querySelectorAll('.mermaid');
          var pending = 0;
          for (var i = 0; i < all.length; i++) {
            if (all[i].getAttribute('data-processed') !== 'true') { pending++; }
          }
          if (pending > 0) { fallbackMermaid('partial'); }
        }, function () { fallbackMermaid('error'); });
      }
    } catch (e) {
      // 老版本 API 兜底；两条路都失败则降级
      try {
        window.mermaid.init(undefined, nodes);
      } catch (e2) {
        fallbackMermaid('error');
      }
    }
  }

  /* ------------------------------------------------------------------
   * 11. 启动
   * ------------------------------------------------------------------ */
  function boot() {
    markCurrent();
    initNavToggle();
    initNavSearch();
    wrapTables();

    // 语法高亮：HTML 里已按「本地优先」引用 vendor；缺失时这里回退 CDN
    if (window.hljs) {
      highlightAll();
      decorateCodeBlocks();
    } else {
      loadFirstScript([HLJS_LOCAL, HLJS_CDN], function () {
        if (window.hljs) { highlightAll(); }
        decorateCodeBlocks();   // 即使高亮不可用也要加行号与锚点
      });
    }

    // Mermaid 同理；两处都拿不到就降级为源码展示
    if (window.mermaid) {
      renderMermaid();
    } else {
      loadFirstScript([MERMAID_LOCAL, MERMAID_CDN], function (ok) {
        if (ok && window.mermaid) { renderMermaid(); } else { fallbackMermaid('missing'); }
      });
    }

    // 行锚点跳转：首屏 + 后续 hash 变化
    window.setTimeout(goToHash, 60);
    window.addEventListener('hashchange', goToHash);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
