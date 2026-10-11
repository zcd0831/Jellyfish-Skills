package com.example.myplugin;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import zcd.jellyfish.api.JellyfishException;
import zcd.jellyfish.api.extension.ToolCallRequest;
import zcd.jellyfish.api.extension.ToolCallResult;
import zcd.jellyfish.api.extension.ToolDescriptor;
import zcd.jellyfish.api.extension.ToolMetadata;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 工具处理器的单测：不经内核，直接调 {@code handle}。
 * <p>
 * 只 mock 外部依赖或协作者；本类没有协作者，因此连 Mockito 都用不上——
 * 「工具不认识插件上下文」这个设计在这里收了利息。
 *
 * @author com.example
 */
@DisplayName("my_hello 工具")
class MyToolTest {

    /** 被测处理器：配置留空，走缺省问候前缀。 */
    private final MyTool tool = new MyTool(MyConfig.from(null));

    @Test
    @DisplayName("给了名字时应返回问候语")
    void handle_should_returnGreeting_when_nameProvided() throws Exception {
        // Given
        ToolCallRequest request = request("张三");

        // When
        ToolCallResult result = tool.handle(request);

        // Then
        assertEquals(MyTool.NAME, result.getToolName());
        assertEquals("你好，张三！", result.getOutput());
    }

    @Test
    @DisplayName("缺参数时应抛 JellyfishException 而不是返回一句错误文本")
    void handle_should_throw_when_nameMissing() {
        // Given
        ToolCallRequest request = request("   ");

        // When / Then
        // 首行会显示在内核的轨迹行上，因此这里断言的是「抛出来了」，而不是文案
        assertThrows(JellyfishException.class, () -> tool.handle(request));
    }

    @Test
    @DisplayName("成功时应带上给界面看的单行摘要")
    void handle_should_reportSummaryMetadata_when_success() throws Exception {
        // Given
        ToolCallRequest request = request("张三");

        // When
        ToolCallResult result = tool.handle(request);

        // Then
        assertEquals("问候了 张三", ToolMetadata.summaryOf(result.getMetadata()));
        // 元数据不是给模型的：正文里不应该混进那句话
        assertTrue(!String.valueOf(result.getOutput()).contains("问候了"));
    }

    @Test
    @DisplayName("工具名片的必填参数应包含 name")
    void descriptor_should_requireNameArgument() {
        // Given / When
        ToolDescriptor descriptor = MyTool.descriptor();

        // Then
        assertEquals(MyTool.NAME, descriptor.getName());
        assertEquals(MyTool.requiredArguments(), descriptor.getRequired());
        assertTrue(descriptor.getParameters().containsKey("name"));
    }

    /**
     * 造一个工具调用请求。
     *
     * @param name 参数 name 的取值
     * @return 请求对象
     */
    private static ToolCallRequest request(String name) {
        Map<String, Object> arguments = new HashMap<String, Object>();
        arguments.put("name", name);
        return new ToolCallRequest(MyTool.NAME, Collections.unmodifiableMap(arguments), "session-1");
    }
}
