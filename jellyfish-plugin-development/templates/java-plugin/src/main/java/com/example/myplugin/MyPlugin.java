package com.example.myplugin;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import zcd.jellyfish.api.event.notification.ToolCallCompletedEvent;
import zcd.jellyfish.api.event.notification.UiInvalidatedEvent;
import zcd.jellyfish.api.extension.CommandDescriptor;
import zcd.jellyfish.api.extension.CommandRequest;
import zcd.jellyfish.api.extension.CommandResult;
import zcd.jellyfish.api.extension.PromptContribution;
import zcd.jellyfish.api.extension.PromptContributionRequest;
import zcd.jellyfish.api.extension.ToolCallRequest;
import zcd.jellyfish.api.extension.ToolCallResult;
import zcd.jellyfish.api.plugin.JellyfishPlugin;
import zcd.jellyfish.api.plugin.PluginContext;

import java.util.Arrays;
import java.util.List;

/**
 * 插件入口：在这里把「我会哪些能力」注册给内核。
 * <p>
 * 本模板演示四种注册，正好对应四类常见需求：
 * <ul>
 *     <li>{@link ToolCallRequest} → 一个模型能调用的工具（带路由键，同键唯一）；</li>
 *     <li>{@link CommandRequest} → 一条人敲的命令（带路由键，同键唯一）；</li>
 *     <li>{@link PromptContributionRequest} → 往 system prompt 里加一段上下文（类型级贡献，
 *     可以被问到很多次）；</li>
 *     <li>{@link ToolCallCompletedEvent} → 订阅一条通知（事件是<b>旁路且可丢</b>的，只用来做通知与统计）。</li>
 * </ul>
 * <b>注册窗口是插件的整个存活期</b>，不是 {@code start()} 之内：运行期才知道自己能提供什么能力的插件
 * （例如握手之后才拿到工具清单的客户端）可以在任意时刻继续注册。回收按 owner 一次收干净。
 * <p>
 * 两条边界：插件拿不到会话与工作目录（{@code RuntimeInfo} 刻意不含），也不能新开会话或起回合——
 * 要「替用户说一句话」用 {@link CommandResult#handoff(String)}，要往外壳说话用
 * {@link PluginContext#present}。
 *
 * @author com.example
 */
public final class MyPlugin implements JellyfishPlugin {

    /** 日志。 */
    private static final Logger LOG = LoggerFactory.getLogger(MyPlugin.class);

    /** 命令名。 */
    private static final String COMMAND_NAME = "myhello";

    /** 命令别名：别名里不能带命令前缀 {@code /}，也不能含空白。 */
    private static final List<String> COMMAND_ALIASES = Arrays.asList("mh");

    @Override
    public void start(PluginContext context) {
        // 先装配再注册：处理器一旦注册就可能被调用，依赖必须已经就绪
        MyConfig config = MyConfig.from(context.configuration());

        registerStateChangingTool(context, MyTool.NAME, MyTool.descriptor(), new MyTool(config));
        context.handle(CommandRequest.class, COMMAND_NAME,
                // 末尾显式声明 sessionRequired：本命令不依赖会话，因此在没有会话的界面里也可以用。
                // 缺省是 true（保守）——一条依赖会话的命令被当成对话发给模型，是更坏的默认。
                new CommandDescriptor("和示例插件打个招呼", "<名字>", COMMAND_ALIASES, false),
                request -> {
                    List<String> tokens = request.getArguments().getTokens();
                    String who = tokens == null || tokens.isEmpty() ? "世界" : tokens.get(0);
                    return CommandResult.ok(config.greeting() + "，" + who + "！");
                });

        // 稳定的规则进 system prompt；每轮都变的状态应该走 TurnContextRequest（它随本轮用户消息送达）
        context.contribute(PromptContributionRequest.class,
                request -> PromptContribution.of("调用 my_hello 时请把用户的名字原样传进去。"));

        // 通知是旁路且可丢的：这里只记日志，不用它传递任何必须到达的结果
        context.observe(ToolCallCompletedEvent.class,
                event -> LOG.info("工具执行结束: name={} success={} 用时={}ms",
                        event.getToolName(), event.isSuccess(), event.getDurationMillis()));

        LOG.info("my-plugin 已启动: greeting={} stateDir={}", config.greeting(), config.stateDirectory());
    }

    @Override
    public void stop() {
        // 这里释放插件自己申请的资源（连接、线程、子进程）。
        // 处理器注册与事件订阅由框架按 owner 回收，不用自己反注册；
        // 但**产生注册的后台线程必须在本方法返回前停下来**：stop() 之后任何注册 / 发布都会当场失败。
        LOG.info("my-plugin 已停止");
    }

    /**
     * 注册一个会改动自己贡献内容的工具，并在调用之后告诉外壳「我脏了」。
     * <p>
     * <b>为什么包一层而不是让工具自己发</b>：工具只该关心「把活干完」，「界面要重画」是插件的展示职责；
     * 分开之后 {@link MyTool} 可以在没有任何插件上下文的情况下单测。
     * <p>
     * <b>为什么写失败也发</b>：失效只是「下一帧重问一次」，状态没变时重问所得与之前相同；
     * 而少发一次的代价是「某条分支忘了发」导致界面上挂着陈旧内容。
     * <p>
     * <b>反向的禁令</b>：UI 贡献处理器（面板 / 状态栏）里**不许**发这个事件——那会形成
     * 「失效 → 收集贡献 → 又失效」的死循环。发它的应当是真正改了数据的那一方。
     *
     * @param context    插件上下文
     * @param name       工具名（同时是注册用的路由键）
     * @param descriptor 工具名片
     * @param tool       工具处理器
     */
    private static void registerStateChangingTool(final PluginContext context, String name, Object descriptor,
                                                  final MyTool tool) {
        context.handle(ToolCallRequest.class, name, descriptor, request -> {
            ToolCallResult result = tool.handle(request);
            context.emit(new UiInvalidatedEvent());
            return result;
        });
    }
}
