# DiPlay 接入教程

这份文档给想把 2021 款缤瑞德赛车机接进自己 DiPlay 版本的开发者。App 里要改的是 iAP2 传输层的建连入口，握手和 CarPlay 会话接回你现有的流程。

接入前先核对 [原车指纹](原车修改教程.md#输入和输出)，确认补丁版 `gocsdk` 正在监听 `goc_spp`。再用实际装到车机上的 App 试连一次，确认它有权限访问这个套接字。

```text
DiPlay App ← goc_spp 双向字节流 → gocsdk ← 蓝牙 RFCOMM → iPhone
```

| 项目 | 接口约定 |
| --- | --- |
| 本地传输 | Android `LocalSocket`，流式套接字 |
| 套接字名 | `goc_spp`，命名空间 `RESERVED`，对应 `/dev/socket/goc_spp` |
| 第一次写入 | 发送已配对 iPhone 的经典蓝牙地址。去掉冒号并转成大写，例如 `AA:BB:CC:DD:EE:FF` → `AABBCCDDEEFF`。一次写入这 12 个 ASCII 字节，再调用 `flush()` |
| 写入格式 | 只发地址字符，省去前缀、换行和终止符。UUID 已写在补丁里 |
| 后续收发 | 用同一个套接字的输入流和输出流跑 iAP2 |

## Java 接入片段

在后台线程调用下面的 `openGocIap2`。拿到套接字后，把输入流和输出流交给现有的 iAP2 会话。握手要设超时，失败或会话结束时关掉套接字，重试时重新建一个。

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

`openGocIap2` 返回时，App 已连上本地套接字并写出手机地址。接下来由 `gocsdk` 做 SDP 查找和 RFCOMM 建连。V049 写完地址后会直接交出字节流。接入时可以沿用 App 现有的 iAP2 探测和超时逻辑，收到第一个有效的 iAP2 响应再确认手机端链路通了。

## 联调时如何判断失败阶段

| 现象 | 排查方向 |
| --- | --- |
| `ENOENT` 或 `ECONNREFUSED` | 核对 `goc_spp` 是否已监听、监听进程归属，以及 `RESERVED` 命名空间 |
| `EACCES` | 核对 App UID、套接字权限和 SELinux 日志 |
| 本地地址写入成功，RFCOMM 未建立 | 核对 iPhone 经典蓝牙 MAC、配对状态、iAP2 服务是否可发现 |
| RFCOMM 已建立，iAP2 失败 | 检查 App 的探测、握手或认证日志 |

目前补丁还待实车验证。车上联调时，除了试 DiPlay 连接，也要检查补丁进程的部署、原车蓝牙功能和原服务能否恢复。

接口写法参考了 DiPlay V049 APK 里的 `AndroidGocSppSocket` 和 `GocSppTransport`。套接字命名空间见 [Android 文档](https://developer.android.com/reference/android/net/LocalSocketAddress.Namespace)。
