// 最小可用的 Node 脚本插件骨架（CommonJS —— 入口与 SDK 都用 require，ESM 不在支持范围内）。
//
// 把它拷成 scripts/node/<脚本 id>/ 下的 main.js，改掉工具名与逻辑即可；目录名就是脚本 id。
// 三件事必须一起改，否则脚本会拒绝服务：
//   1) manifest.json 里的 entry 指到这个文件；
//   2) manifest.json 与下面这些声明必须逐项一致（比对的是名字集合）；
//   3) 改完跑 dump_manifest.js <目录> --write 重新生成清单（JS 拿不到注释，description 必须显式写）。
//
// 三条纪律：
//   * 失败一律 throw new ScriptError(...)，不要 return { error: ... }（后者会被当成正常输出）；
//   * 用 __dirname 定位脚本自己的文件，相对路径会落到宿主的进程工作目录；
//   * 事件是旁路且可丢的，只用来做通知与统计。

const fs = require('fs');
const path = require('path');
const { ScriptError, ToolResult, command, contributes, subscribe, tool } = require('jellyfish_sdk');

// 脚本自己的目录：脚本可能从任何工作目录被拉起
const HERE = __dirname;
const NOTES = path.join(HERE, 'notes.txt');

// 见过多少次工具执行结束；worker 是单线程的，因此这个计数器不需要加锁
const seen = { count: 0 };

function noteCount() {
    if (!fs.existsSync(NOTES)) {
        return 0;
    }
    return fs.readFileSync(NOTES, 'utf8').split(/\r?\n/).filter((line) => line.trim()).length;
}

tool({
    name: 'my_hello',
    description: '按名字打招呼（示例工具）',
    parameters: { name: { type: 'string', description: '要打招呼的人' } },
    required: ['name'],
}, (params, ctx) => {
    const name = String(params.args.name === undefined ? '' : params.args.name).trim();
    if (!name) {
        // 用抛异常表达失败：return { error: ... } 会被当作正常输出回灌给模型
        throw new ScriptError('缺少参数 name');
    }
    return new ToolResult(`你好，${name}！`, { summary: `问候了 ${name}（便签 ${noteCount()} 条）` });
});

command({
    name: 'myhello',
    summary: '和示例脚本打个招呼',
    usage: '/myhello <名字>',
    aliases: ['mh'],
    // 显式声明「本命令不依赖会话」：缺省是 true（保守）
    sessionRequired: false,
}, (params) => {
    const who = params.tokens && params.tokens.length ? params.tokens[0] : '世界';
    return `你好，${who}！`;
});

contributes('prompt', () => '调用 my_hello 时请把用户的名字原样传进去。');

subscribe('ToolCallCompletedEvent', (event, ctx) => {
    seen.count += 1;
});
