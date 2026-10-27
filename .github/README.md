<div align="center">

# 绝区零一条龙 · macOS 移植版

**ZenlessZoneZero-OneDragon for macOS (PlayCover / iOS)**

<img alt="platform" src="https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon)-blueviolet">
<img alt="license" src="https://img.shields.io/badge/license-GPL--3.0-blue">

[中文](#中文) · [English](#english)

</div>

> [!IMPORTANT]
> 本仓库是 [OneDragon-Anything/ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon)（绝区零一条龙）的**非官方 macOS 移植**。
> 原项目的全部功能、识别模型和绝大部分代码都来自原作者团队，在此致以诚挚的感谢 ❤️
> 移植版的问题请在本仓库提 Issue，**不要**去原仓库反馈。
> 原项目说明见 [README_upstream.md](README_upstream.md)。
>
> This is an **unofficial macOS port** of ZenlessZoneZero-OneDragon. All credit for the original features, models and the vast majority of the code goes to the original team. Please report port-specific problems here, **not** upstream.

---

## 中文

### 这是什么

macOS 上没有 PC 版绝区零，只能通过 [PlayCover](https://playcover.io/) 运行 iOS 版。本移植让一条龙通过 PlayCover 分支版内置的 **MaaTools** 服务（和 MAA 明日方舟助手 macOS 版用的是同一套）在游戏进程内截图、注入多指触控，从而在 macOS 上运行一条龙的日常功能。

移植原则：**业务逻辑不写平台分支**。iOS 和 PC 的差异只放在两处：

- **输入**：新的控制器 `ZMaaToolsController`，把 PC 的键鼠动作转成触控（摇杆、技能按钮、镜头拖动等）
- **画面**：移动端画面变体 `assets/game_data/mobile/`，按区域覆盖 PC 的画面配置；移动端模板放在 `assets/template/mobile_*`

技术细节见 [macOS 移植设计文档](../docs/develop/one_dragon/macos_playcover_design.md)。

### 已实测可用

| 功能 | 状态 |
|------|------|
| 邮件、兑换码、每日签到、活跃度奖励 | ✅ |
| 录像店营业、随便观、咖啡店（可选饮料，如「鲜萃红茶」） | ✅ |
| 丽都城募、丽都周纪、情报板（含委托战斗） | ✅ |
| 体力刷本（实战模拟室 / 代理人方案培养等） | ✅ |
| 恶名狩猎 | ✅ |
| 式舆防卫战 | ✅（自动选队、判断阶段结束已适配） |
| 迷失之地 | ⚠️ 基本可跑，寻路偶尔卡住 |
| 自动战斗 | ✅ 通用状态已适配，部分角色专属状态还没有移动端模板 |
| 自动启动游戏、叠加层、画中画 | ❌ 需手动打开游戏；叠加层依赖 Windows 接口 |

### 环境要求

| 项目 | 要求 |
|------|------|
| 电脑 | Apple Silicon（M1 及以后）的 Mac。实测机型 Mac mini M4 |
| 系统 | macOS 14 及以上（实测 macOS 27） |
| 游戏 | 绝区零 **iOS 版（国服）**，通过 PlayCover 运行 |
| PlayCover | **MaaTools 分支版** [hguandl/PlayCover](https://github.com/hguandl/PlayCover/releases)（官方版没有 MaaTools 服务） |
| Python | 3.11.x，由 uv 自动安装，无需手动装 |
| 工具 | [Homebrew](https://brew.sh/)、git、[uv](https://github.com/astral-sh/uv) |
| 内存 | 建议 16GB 以上（脚本约 1～1.3GB，游戏另算） |

### 一、部署绝区零（iOS 版 + PlayCover）

1. 下载并安装 [PlayCover 分支版](https://github.com/hguandl/PlayCover/releases)（文件名带 `maa`），拖进「应用程序」。
2. 获取绝区零 iOS 版的**解密 IPA**，在 PlayCover 中点「+」导入。
   > 请通过合法途径获取，本项目不提供 IPA。
3. 在 PlayCover 中右键游戏 →「设置」：
   - **绕过（Bypass）** 页：勾选 **MaaTools**，端口保持 **1717**；**不要**勾选「从 Metal 抓取」
   - **图像（Graphics）** 页：分辨率选 **16:9**，例如 1920×1080
4. 启动游戏并登录。窗口标题出现 `[localhost:1717]` 表示 MaaTools 已开启。
5. 游戏内建议：画质随意，但**不要改 UI 缩放**；键位保持默认触屏布局。

> [!WARNING]
> MaaTools 监听所有网卡，同一局域网的其它设备也能连上并操作游戏。请只在可信网络下使用，或用 macOS 防火墙阻止外部连接。

### 二、部署一条龙脚本

```bash
brew install git uv
```

```bash
git clone https://github.com/luoxia001/ZenlessZoneZero-OneDragon-macOS.git
```

```bash
cd ZenlessZoneZero-OneDragon-macOS && uv sync
```

- `uv sync` 会自动下载 Python 3.11 和全部依赖（macOS 使用 CPU / CoreML 版 onnxruntime 1.23.2）。
- 首次启动后，在设置里下载 OCR 和识别模型（与 Windows 版相同）。

### 三、启动

1. **先手动打开游戏**并进入主界面（脚本目前不会自动启动游戏）。
2. 启动一条龙 GUI，任选一种：

   ```bash
   PYTHONPATH=src uv run python src/zzz_od/gui/app.py
   ```

   或在 Finder 里双击 `deploy/macos/start.command`（后台启动，日志在 `.log/gui_launch.log`）。

3. macOS 上实例的「平台」默认就是 **iOS（PlayCover）**，MaaTools 地址 `127.0.0.1:1717`。如改过端口，在实例配置 `config/<实例>/game.yml` 里改 `maatools_port`。
4. 和 Windows 版一样配置并运行「一条龙」。游戏窗口**可以在后台**，不需要前台。

### 四、权限（可选）

在「系统设置 → 隐私与安全性 → 辅助功能」里给运行脚本的终端（或 Python）授权后：

- 快捷键（如 F9 开始 / 停止）可用
- 兑换码等文字输入会用 Cmd+V 粘贴

不授权时界面按钮照常可用，文字输入改为点击输入框自带的粘贴按钮。

### 常见问题

| 现象 | 处理 |
|------|------|
| 连不上 MaaTools | 确认用的是分支版 PlayCover、游戏设置里勾了 MaaTools、窗口标题有 `[localhost:1717]` |
| 截图比例不对、点击偏移 | 游戏分辨率必须是 16:9 |
| 角色往斜方向走、寻路丢目标 | 不要改游戏内的摇杆位置和 UI 缩放 |
| 脚本被强制结束后某个按钮一直“按下” | 重新启动脚本即可，连接时会自动抬起所有残留的手指 |

### 免责声明

- 本项目仅供学习交流，使用本工具产生的一切风险由使用者自行承担。
- 本移植版与原项目团队、米哈游均无关联，**不得用于任何商业用途或售卖**。
- 项目 LOGO 版权归原项目的[巡夜子](https://github.com/yokuminto)及全体开发者所有。
- 本项目沿用原项目的 [GPL-3.0](../LICENSE) 许可证。

### 致谢

- [OneDragon-Anything/ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon) 的全体开发者 —— 本移植的一切基础
- [hguandl/PlayCover](https://github.com/hguandl/PlayCover) 的 MaaTools 服务
- [PlayCover](https://github.com/PlayCover/PlayCover)

---

## English

### What is this

There is no PC build of Zenless Zone Zero for macOS — only the iOS build running through [PlayCover](https://playcover.io/). This port lets OneDragon drive the iOS build through the **MaaTools** service built into a PlayCover fork (the same one used by MAA for macOS): in-process screenshots plus multi-touch injection.

Design rule: **no platform branches in business logic**. Differences live in only two places:

- **Input**: a new `ZMaaToolsController` translating PC keyboard/mouse actions into touches (joystick, skill buttons, camera drags)
- **Screens**: mobile screen variants in `assets/game_data/mobile/` that override PC screen areas, plus mobile templates in `assets/template/mobile_*`

See the [design document (Chinese)](../docs/develop/one_dragon/macos_playcover_design.md) for details.

### Requirements

- Apple Silicon Mac (M1 or later), macOS 14+
- Zenless Zone Zero **iOS build (CN server)** running in the **MaaTools fork of PlayCover**: [hguandl/PlayCover](https://github.com/hguandl/PlayCover/releases)
- Homebrew, git, [uv](https://github.com/astral-sh/uv) (uv installs Python 3.11 automatically)
- 16 GB RAM recommended

### Game setup

1. Install the PlayCover fork (`maa` in the file name) and import a decrypted ZZZ IPA (obtain it legally; none is provided here).
2. In the game's PlayCover settings: **Bypass** tab → enable **MaaTools**, port **1717**, leave "capture from Metal" off; **Graphics** tab → a **16:9** resolution such as 1920×1080.
3. Launch the game. `[localhost:1717]` in the window title means MaaTools is running.

> [!WARNING]
> MaaTools listens on all network interfaces. Use it only on a trusted network or block inbound connections with the macOS firewall.

### Script setup and launch

```bash
brew install git uv
```

```bash
git clone https://github.com/luoxia001/ZenlessZoneZero-OneDragon-macOS.git
```

```bash
cd ZenlessZoneZero-OneDragon-macOS && uv sync
```

Open the game first and go to the main screen, then start the GUI:

```bash
PYTHONPATH=src uv run python src/zzz_od/gui/app.py
```

You can also double-click `deploy/macos/start.command` in Finder. On macOS the instance platform defaults to **iOS (PlayCover)** at `127.0.0.1:1717`. The game window can stay in the background. On first launch, download the OCR and detection models from the settings, as on Windows.

Optional: grant Accessibility permission to your terminal (or Python) to enable hotkeys such as F9 and Cmd+V text input.

### Disclaimer

For learning and personal use only, at your own risk. Not affiliated with the original team or HoYoverse. **Commercial use or resale is not allowed.** Licensed under [GPL-3.0](../LICENSE), same as the original project.

### Credits

All the developers of [OneDragon-Anything/ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon). This port would not exist without their hard work. Thanks also to [hguandl/PlayCover](https://github.com/hguandl/PlayCover) for MaaTools and to [PlayCover](https://github.com/PlayCover/PlayCover).
