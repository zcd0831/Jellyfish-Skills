package com.example.myplugin;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mockito;
import org.pf4j.PluginState;
import zcd.jellyfish.api.extension.ToolCallRequest;
import zcd.jellyfish.api.extension.ToolCallResult;
import zcd.jellyfish.infra.action.ActionQueue;
import zcd.jellyfish.infra.event.EventChannel;
import zcd.jellyfish.infra.event.EventChannelOptions;
import zcd.jellyfish.infra.extension.ExtensionRegistry;
import zcd.jellyfish.infra.extension.HandlerBinding;
import zcd.jellyfish.infra.metrics.MetricsRegistry;
import zcd.jellyfish.infra.plugin.PF4JPluginManager;
import zcd.jellyfish.infra.plugin.PluginContextFactory;
import zcd.jellyfish.infra.plugin.PluginRuntimeConfig;
import zcd.jellyfish.infra.plugin.RuntimeInfoHolder;
import zcd.jellyfish.infra.registry.TypeRegistry;
import zcd.jellyfish.infra.session.SessionManager;
import zcd.jellyfish.infra.shell.ShellIngress;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 加载链路端到端测试：用<b>真实的</b> {@code plugin.properties} 与真实的插件类跑一遍
 * 「加载 → 描述符体检 → 启动 → 能力可路由 → 卸载回收」。
 * <p>
 * <b>为什么这条测试必须有</b>：描述符少一个键、入口类没有公开无参构造器，都会让插件被<b>静默跳过</b>
 * （内核照常启动，表现是「命令不在 /help 里」而不是报错）。普通单测覆盖不到这一段。
 * <p>
 * <b>依赖口径</b>：{@code jellyfish-infra} 是 {@code test} scope——注册与派发走的是内核那条真实路径，
 * 换成假货只是验证「我以为内核会怎么查」；其余内核服务（会话管理器等）与本次被测无关，直接 mock。
 *
 * @author com.example
 */
@DisplayName("my-plugin 加载链路")
class MyPluginLoadingTest {

    /** 内核里本插件的标识，与 plugin.properties 保持一致。 */
    private static final String PLUGIN_ID = "my-plugin";

    /** 临时插件根目录：PF4J 只在每个 root 的下一层找 plugin.properties。 */
    @TempDir
    Path pluginsRoot;

    /** 共用注册表。 */
    private TypeRegistry registry;

    /** 同步扩展点注册表：工具注册的落点。 */
    private ExtensionRegistry extensions;

    /** 事件通道：插件上下文装配需要。 */
    private EventChannel eventChannel;

    /** 被测插件管理器。 */
    private PF4JPluginManager manager;

    @BeforeEach
    void setUp() {
        registry = new TypeRegistry();
        extensions = new ExtensionRegistry(registry);
        eventChannel = new EventChannel(EventChannelOptions.defaults(), registry);
        eventChannel.start();
    }

    @AfterEach
    void tearDown() {
        if (manager != null) {
            manager.close();
        }
        eventChannel.close();
    }

    @Test
    @DisplayName("真实描述符应让插件启动成功")
    void bootstrap_should_startPlugin_when_descriptorIsValid() throws IOException {
        // Given
        installPlugin();

        // When
        manager = newManager();
        manager.bootstrap();

        // Then
        assertEquals(PluginState.STARTED, manager.stateOf(PLUGIN_ID));
    }

    @Test
    @DisplayName("启动后工具应可路由，并能真的算出结果")
    void bootstrap_should_registerUsableTool_when_pluginStarted() throws IOException {
        // Given
        installPlugin();
        manager = newManager();

        // When
        manager.bootstrap();

        // Then
        List<HandlerBinding<ToolCallRequest, ToolCallResult>> bindings =
                extensions.bindings(ToolCallRequest.class, MyTool.NAME);
        assertEquals(1, bindings.size());

        Map<String, Object> arguments = new HashMap<String, Object>();
        arguments.put("name", "张三");
        ToolCallResult result = extensions.invoke(bindings.get(0).getHandler(),
                new ToolCallRequest(MyTool.NAME, Collections.unmodifiableMap(arguments), "session-1"));

        assertEquals("你好，张三！", result.getOutput());
    }

    @Test
    @DisplayName("插件卸载后注册应按 owner 被回收")
    void close_should_unregisterHandlers_when_pluginStopped() throws IOException {
        // Given
        installPlugin();
        manager = newManager();
        manager.bootstrap();

        // When
        manager.close();
        manager = null;

        // Then
        assertTrue(extensions.bindings(ToolCallRequest.class, MyTool.NAME).isEmpty());
    }

    /**
     * 把真实的 {@code plugin.properties} 装进临时插件根目录，形成 PF4J 认识的独立插件目录。
     *
     * @throws IOException 写入失败时抛出
     */
    private void installPlugin() throws IOException {
        Path pluginDir = pluginsRoot.resolve(PLUGIN_ID);
        Files.createDirectories(pluginDir);
        try (InputStream descriptor = getClass().getResourceAsStream("/plugin.properties")) {
            if (descriptor == null) {
                throw new IllegalStateException("测试类路径上找不到 plugin.properties");
            }
            Files.copy(descriptor, pluginDir.resolve("plugin.properties"));
        }
    }

    /**
     * 构造扫描临时目录的插件管理器。
     *
     * @return 插件管理器
     */
    private PF4JPluginManager newManager() {
        PluginContextFactory contexts = new PluginContextFactory(extensions, eventChannel, registry,
                new RuntimeInfoHolder(), new ActionQueue(), Mockito.mock(SessionManager.class),
                new ShellIngress(new MetricsRegistry()));
        return new PF4JPluginManager(contexts, PluginRuntimeConfig.ofRoots(pluginsRoot), eventChannel);
    }
}
