package com.example.myplugin;

import zcd.jellyfish.api.JellyfishException;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.Map;

/**
 * 本插件的配置解析：把 {@code jellyfish.json} 里 {@code plugins.configurations.my-plugin} 那段
 * 解析成值对象。
 * <p>
 * 惯例是「值对象 + 静态工厂 {@code from(Map)}」：键写错、值越界都在这里当场处理，
 * 而不是让它们跑到运行期变成「配置怎么不生效」。
 * <p>
 * 三条要点：
 * <ul>
 *     <li>{@code ${ENV}} 插值与「项目级覆盖全局级」<b>内核已经做完</b>，这里拿到的是最终值；</li>
 *     <li>{@code ~} <b>不展开</b>（内核只在自己配置文件的路径段上做这件事），插件要自己来；</li>
 *     <li>配置可疑时用 {@code emit(new ConfigWarningEvent(...))} 告诉用户，<b>不要阻断启动</b>。
 *     本类只负责「值合不合法」这一层。</li>
 * </ul>
 * 不可变，可安全跨线程传递。
 *
 * @author com.example
 */
final class MyConfig {

    /** 问候前缀配置键。 */
    private static final String KEY_GREETING = "greeting";

    /** 状态目录配置键。 */
    private static final String KEY_STATE_DIR = "stateDir";

    /** 缺省问候前缀。 */
    private static final String DEFAULT_GREETING = "你好";

    /** 缺省状态目录。 */
    private static final String DEFAULT_STATE_DIR = "~/.jellyfish/my-plugin";

    /** 问候前缀。 */
    private final String greeting;

    /** 状态目录（已展开 {@code ~}）。 */
    private final Path stateDirectory;

    /**
     * 构造配置。
     *
     * @param greeting       问候前缀，非空白
     * @param stateDirectory 状态目录
     */
    private MyConfig(String greeting, Path stateDirectory) {
        this.greeting = greeting;
        this.stateDirectory = stateDirectory;
    }

    /**
     * 从插件配置段解析配置。
     *
     * @param configuration 插件配置段，可为 {@code null}（等价于未配置）
     * @return 配置值对象，保证非 {@code null}
     * @throws JellyfishException 配置值的类型或取值非法时抛出
     */
    static MyConfig from(Map<String, Object> configuration) {
        Map<String, Object> values = configuration == null
                ? Collections.<String, Object>emptyMap() : configuration;
        return new MyConfig(
                text(values.get(KEY_GREETING), KEY_GREETING, DEFAULT_GREETING),
                expand(text(values.get(KEY_STATE_DIR), KEY_STATE_DIR, DEFAULT_STATE_DIR)));
    }

    /**
     * 获取问候前缀。
     *
     * @return 问候前缀
     */
    String greeting() {
        return greeting;
    }

    /**
     * 获取状态目录。
     *
     * @return 状态目录，已展开 {@code ~} 与规范化
     */
    Path stateDirectory() {
        return stateDirectory;
    }

    /**
     * 取一个字符串配置项。
     * <p>
     * 类型不对<b>当场抛</b>：静默回落缺省值会变成「配置不生效」——那是这类问题里最难查的一种。
     *
     * @param raw          配置原值，可为 {@code null}
     * @param key          配置键，用于报错
     * @param defaultValue 缺省值
     * @return 配置值，保证非空白
     * @throws JellyfishException 值不是字符串或为空白时抛出
     */
    private static String text(Object raw, String key, String defaultValue) {
        if (raw == null) {
            return defaultValue;
        }
        if (!(raw instanceof String) || ((String) raw).trim().isEmpty()) {
            throw new JellyfishException(key + " 必须是非空字符串，实际为 " + raw);
        }
        return ((String) raw).trim();
    }

    /**
     * 展开用户主目录前缀并规范化路径。
     *
     * @param raw 配置里的路径原文
     * @return 规范化后的绝对路径
     * @throws JellyfishException 无法确定用户主目录时抛出
     */
    private static Path expand(String raw) {
        String text = raw;
        if (text.startsWith("~")) {
            String home = System.getProperty("user.home");
            if (home == null || home.trim().isEmpty()) {
                throw new JellyfishException("无法展开 ~ ：未取到 user.home");
            }
            text = home + text.substring(1);
        }
        return Paths.get(text).toAbsolutePath().normalize();
    }
}
