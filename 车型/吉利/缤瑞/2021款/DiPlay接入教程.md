# DiPlay 接入教程

适用车型为吉利缤瑞 2021 款德赛车机。接入前由部署方核对 [原车指纹](原车修改教程.md#输入和输出)，确认候选 `gocsdk` 已运行并持有 `goc_spp` 监听，使用实际安装的 App 身份验证套接字访问权限。

```text
DiPlay App ← goc_spp 双向字节流 → gocsdk ← 蓝牙 RFCOMM → iPhone
```

| 项目 | 接口约定 |
| --- | --- |
| 本地传输 | Android `LocalSocket`，流式套接字 |
| 套接字名 | `goc_spp`，命名空间 `RESERVED`，对应 `/dev/socket/goc_spp` |
| 初始写入 | 已配对 iPhone 的经典蓝牙地址，去掉冒号并转大写，以 ASCII 一次写入 12 字节。示例 `AA:BB:CC:DD:EE:FF` → `AABBCCDDEEFF` |
| 初始写入边界 | 只发送地址字符，随后 `flush()`。UUID 由补丁内置，地址字段无换行、终止符或其他前缀 |
| 后续收发 | 复用同一套接字的输入和输出流，按现有 iAP2 协议收发。以 iAP2 有效响应确认端到端链路 |
| 生命周期 | 后台线程建连。为握手设置截止时间，失败或会话结束时关闭套接字，重试时新建套接字 |

## Java 接入片段

将原有 iAP2 传输层的建连函数接到下方接口。调用方持有返回的套接字，把它的输入流和输出流传给已有 iAP2 会话，并在结束时关闭。

```java
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

static LocalSocket openGocIap2(String phoneMac) throws IOException {
    if (phoneMac == null || !phoneMac.trim().matches(
            "(?i)(?:[0-9a-f]{12}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2})")) {
        throw new IllegalArgumentException("Invalid phone Bluetooth address");
    }

    byte[] address = phoneMac.trim()
            .replace(":", "")
            .toUpperCase(Locale.US)
            .getBytes(StandardCharsets.US_ASCII);
    LocalSocket socket = new LocalSocket(LocalSocket.SOCKET_STREAM);
    boolean opened = false;
    try {
        socket.connect(new LocalSocketAddress(
                "goc_spp", LocalSocketAddress.Namespace.RESERVED));
        OutputStream output = socket.getOutputStream();
        output.write(address);
        output.flush();
        opened = true;
        return socket;
    } finally {
        if (!opened) {
            try {
                socket.close();
            } catch (IOException ignored) {
                // 保留建连或发送失败的原始异常。
            }
        }
    }
}
```

`openGocIap2` 返回时，只能确认 App 已接入本地套接字并写出手机地址。手机端 SDP 查找和 RFCOMM 建连由 `gocsdk` 继续处理。V049 的 App 传输层在写入地址后直接交出字节流，接入方可沿用既有 iAP2 探测与超时机制，将首个有效的 iAP2 响应作为远端链路就绪的依据。

## 联调时如何判断失败阶段

| 现象 | 排查方向 |
| --- | --- |
| `ENOENT` 或 `ECONNREFUSED` | 核对 `goc_spp` 是否已监听、监听进程归属，以及 `RESERVED` 命名空间 |
| `EACCES` | 核对 App UID、套接字权限和 SELinux 日志 |
| 本地地址写入成功，RFCOMM 未建立 | 核对 iPhone 经典蓝牙 MAC、配对状态、iAP2 服务是否可发现 |
| RFCOMM 已建立，iAP2 失败 | 检查 App 的探测、握手或认证日志 |

`gocsdk` 交付到 RFCOMM 字节流。iAP2 握手、CarPlay 会话和 App 的超时重试由接入方实现。进程部署、原车蓝牙回归和原服务恢复由实车集成方验收。当前候选仍待实车验证。

接口参照 DiPlay V049 APK 的 `AndroidGocSppSocket` 与 `GocSppTransport`，以及 [Android LocalSocketAddress.Namespace 文档](https://developer.android.com/reference/android/net/LocalSocketAddress.Namespace)。
