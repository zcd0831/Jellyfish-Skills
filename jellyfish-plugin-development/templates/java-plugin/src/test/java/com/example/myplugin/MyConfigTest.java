package com.example.myplugin;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import zcd.jellyfish.api.JellyfishException;

import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 配置解析的单测。
 * <p>
 * 重点不是「能读出值」，而是<b>读不出来时行为可预期</b>：类型写错必须当场报错，
 * 而不是静默回落缺省值——静默回落是「配置不生效」这类问题最常见的成因。
 *
 * @author com.example
 */
@DisplayName("my-plugin 配置解析")
class MyConfigTest {

    @Test
    @DisplayName("整段留空时应走缺省值")
    void from_should_useDefaults_when_configurationMissing() {
        // Given / When
        MyConfig config = MyConfig.from(null);

        // Then
        assertEquals("你好", config.greeting());
        assertTrue(config.stateDirectory().isAbsolute());
    }

    @Test
    @DisplayName("配了 greeting 时应覆盖缺省值")
    void from_should_overrideGreeting_when_configured() {
        // Given
        Map<String, Object> configuration = new HashMap<String, Object>();
        configuration.put("greeting", "Hi");

        // When
        MyConfig config = MyConfig.from(configuration);

        // Then
        assertEquals("Hi", config.greeting());
    }

    @Test
    @DisplayName("greeting 类型不对时应当场报错")
    void from_should_throw_when_greetingIsNotString() {
        // Given
        Map<String, Object> configuration = new HashMap<String, Object>();
        configuration.put("greeting", 42);

        // When / Then
        assertThrows(JellyfishException.class, () -> MyConfig.from(configuration));
    }

    @Test
    @DisplayName("stateDir 里的 ~ 应被展开")
    void from_should_expandTilde_when_stateDirConfigured() {
        // Given
        Map<String, Object> configuration = new HashMap<String, Object>();
        configuration.put("stateDir", "~/my-plugin-state");

        // When
        MyConfig config = MyConfig.from(configuration);

        // Then
        Path directory = config.stateDirectory();
        assertEquals("my-plugin-state", directory.getFileName().toString());
        assertTrue(!directory.toString().startsWith("~"));
    }
}
