package com.example.myplugin;

import zcd.jellyfish.api.JellyfishException;
import zcd.jellyfish.api.extension.ExtensionHandler;
import zcd.jellyfish.api.extension.ToolCallRequest;
import zcd.jellyfish.api.extension.ToolCallResult;
import zcd.jellyfish.api.extension.ToolDescriptor;
import zcd.jellyfish.api.extension.ToolMetadata;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 示例工具：模型调用的一个能力。
 * <p>
 * 三条约定（照它写自己的工具）：
 * <ul>
 *     <li>工具名<b>全局唯一</b>，是注册时的路由键；建议带插件前缀，别占用通用名字；</li>
 *     <li>失败<b>抛 {@link JellyfishException}</b>：它的首行会显示在内核的轨迹行上，写成一句人能看懂的原因，
 *     且不要放密钥或大段内容。返回 {@code {"error": ...}} 是错的——那会被当成正常输出；</li>
 *     <li>输出正文的<b>首行写结论</b>（模型据此判断成没成、要不要换参数重来）；给人看的那一句放
 *     {@link ToolMetadata#KEY_SUMMARY}（必须单行），它不进模型上下文。</li>
 * </ul>
 * 本类不认识 {@code PluginContext}：把「存/取数据」与「让界面刷新」分开，
 * 处理器因此可以在没有任何插件上下文的情况下单测。
 *
 * @author com.example
 */
final class MyTool implements ExtensionHandler<ToolCallRequest, ToolCallResult> {

    /** 工具名：同时是注册用的路由键。 */
    static final String NAME = "my_hello";

    /** 参数名。 */
    private static final String ARG_NAME = "name";

    /** 配置。 */
    private final MyConfig config;

    /**
     * 构造工具处理器。
     *
     * @param config 插件配置，不可为 {@code null}
     */
    MyTool(MyConfig config) {
        this.config = config;
    }

    /**
     * 构造工具名片：模型据此决定何时调用。
     * <p>
     * 参数 schema 用的是 JSON Schema 的 {@code properties} 片段；{@code required} 是必填参数名列表
     * （<b>不是</b> {@code order} —— 顺序由注册时的 {@code RegisterOptions} 决定）。
     *
     * @return 工具名片，保证非 {@code null}
     */
    static ToolDescriptor descriptor() {
        Map<String, Object> parameters = new LinkedHashMap<String, Object>();
        Map<String, Object> name = new LinkedHashMap<String, Object>();
        name.put("type", "string");
        name.put("description", "要打招呼的人");
        parameters.put(ARG_NAME, name);
        return new ToolDescriptor(NAME, "按名字打招呼（示例工具）", parameters,
                Collections.singletonList(ARG_NAME));
    }

    @Override
    public ToolCallResult handle(ToolCallRequest request) throws Exception {
        Object raw = request.getArguments().get(ARG_NAME);
        String name = raw == null ? "" : String.valueOf(raw).trim();
        if (name.isEmpty()) {
            throw new JellyfishException("缺少参数 " + ARG_NAME);
        }
        String greeting = config.greeting() + "，" + name + "！";
        return new ToolCallResult(NAME, greeting, summary("问候了 " + name));
    }

    /**
     * 拼一条给界面看的元数据。
     *
     * @param text 单行摘要
     * @return 元数据映射
     */
    private static Map<String, Object> summary(String text) {
        Map<String, Object> metadata = new LinkedHashMap<String, Object>();
        metadata.put(ToolMetadata.KEY_SUMMARY, text);
        return metadata;
    }

    /**
     * 供测试与日志用的必填参数名。
     *
     * @return 参数名列表
     */
    static List<String> requiredArguments() {
        return Collections.singletonList(ARG_NAME);
    }
}
