# macOS（iOS 版 + PlayCover）支持设计文档

## 概述

macOS 上没有 PC 版绝区零，只能通过 PlayCover 运行 iOS 版。iOS 版和 PC 版有两个根本差异：

1. **输入**：iOS 版只认多指触控，不读键盘。移动要按住左下摇杆，转镜头、攻击要另外的手指同时按。
2. **画面**：iOS 版是移动端 UI，没有快捷键和按键提示，很多按钮的位置和图标都和 PC 不同。

本方案的原则是**业务层（application / operation / auto_battle）不写任何平台分支**。差异只放在两处：

| 差异 | 放在哪里 |
|------|---------|
| 输入 | 新的控制器 `ZMaaToolsController`，对外接口和 `ZPcController` 一样 |
| 画面 | 移动端画面变体 `assets/game_data/mobile/screen_info/`，按区域覆盖 PC 的画面配置 |

## 1. 输入：MaaTools 协议

### 1.1 MaaTools 是什么

MaaTools 是 [PlayCover 分支版（hguandl/PlayCover）](https://github.com/hguandl/PlayCover/releases) 在游戏进程里开的一个 TCP 服务（默认端口 1717）。MAA（明日方舟助手）的 macOS 版也用它。它提供：

- 在游戏进程内截图：不依赖窗口位置和标题栏，**游戏窗口在后台也能截**
- 注入触控：每个触控带一个手指编号（contact，0~255），**不同编号是互相独立的手指**，可以同时按住

协议细节见 `src/one_dragon/base/controller/maatools/maatools_client.py` 的注释。

已实测（Mac mini M4，PlayCover v4.0.0.maa，iOS 版国服）：

- 单帧截图约 35ms，前台是其它应用时截图正常
- 手指 0 按住摇杆、手指 1 拖镜头同时进行，角色边跑边转向

### 1.2 坐标

有三套坐标，换算都在控制器内部完成，业务代码只用标准坐标：

| 坐标 | 例子 | 用途 |
|------|------|------|
| 标准坐标 | 1920×1080 | 业务代码、screen_info、触控布局 |
| 截图像素 | 2956×1662 | MaaTools 截图返回的窗口内容像素（BGR），控制器缩放到标准坐标并转成项目统一的 RGB |
| 触控坐标 | 3840×2160 | MaaTools `SIZE` 返回的 iOS 屏幕原生像素，触控时按比例换算 |

### 1.3 PC 动作怎么变成触控

`ZMaaToolsController` 提供和 `ZPcController` 相同的方法，内部这样转换：

| PC 动作 | 触控 |
|---------|------|
| `move_w/a/s/d` 按住 / 松开 | 手指 0 按在摇杆中心并推到对应方向，按住期间一直不松手；同时按多个方向时推到斜方向；全部松开才抬起 |
| `dodge` `normal_attack` 等战斗按键 | 每个动作一根独立的手指（编号 10 起），所以可以和移动同时按 |
| `turn_by_distance` / `move_mouse_relative` | 手指 1 在镜头区域里滑动。PC 鼠标像素 × `camera.scale` = 滑动像素，见下方「镜头」 |
| `click` / `drag_to` / `scroll` | 手指 9 点击或滑动 |
| `mouse_move` | 触屏没有悬停，直接忽略 |
| `input_str` | MaaTools 不支持文字输入。iOS 游戏和 macOS 共用剪贴板：先把文字写进剪贴板，有辅助功能权限时发 Cmd+V，否则点触控布局里的 `text_paste_button`（输入框自带的粘贴按钮） |

点按时手指按住 0.15 秒（`TAP_PRESS_TIME`）。实测菜单按钮 0.05 秒的点按游戏不会响应。战斗按键（`do_action` 的点按）例外，按住 0.05 秒（`BATTLE_TAP_TIME`）：实测切换角色 0.03 秒就能生效，而黄光切人这类连按几个键的操作，每个键都等 0.15 秒会错过极限支援的时间窗口。交互键在大世界里用，仍按 0.15 秒。

摇杆位置固定，不跟随手指。中心必须和游戏画出的摇杆圆心一致（`touch_layout.yml` 的 `joystick.center`，实测 394,781），偏了的话往正前方推会变成斜着走，寻路时目标慢慢滑出画面，反复丢失目标。

每次连上 MaaTools 后，先给 0~31 号手指各发一次抬起事件。原因：脚本进程被强制结束时来不及抬起手指，PlayTools 会让这根手指一直按着，换个脚本进程连上也不会松开。实测出现过普通攻击按钮一直是按下状态（白底黑拳），模板匹配不上，迷失之地以为不在大世界，一直卡在「等待加载」。没按下的手指收到抬起事件不会有影响。

按键语义和 PC 一致：`press=True` 且有 `press_time` 时按住这么久后松开；只有 `press=True` 时一直按住，直到 `release=True`。

**镜头**（实测）：游戏的触屏镜头在手指移动不到约 8 像素时不转（触摸死区），超过后整段都算数；松手时手指还在动会有惯性，快速长距离拖动会转过头。所以每次拖动匀速慢拖（600 像素/秒）、停住再松手、最长 40 像素一段，不足死区的先越过再退回。按这个方式拖动约 1.09 度/像素，`camera.scale = 0.167` 时 2°～90° 的转向误差在 ±10% 内。

各按钮的位置在 `assets/game_data/mobile/touch_layout.yml`。值为 `null` 的按键（例如连携技）还没测量，调用时只记一次警告，不会点击。

### 1.4 兼容 PC 控制器的属性

少数业务代码会直接读 PC 控制器的属性。为了不改业务代码，控制器提供了等价的兼容对象：

| 属性 | 兼容方式 |
|------|---------|
| `game_win` | `MaaToolsGameWindow`，`is_win_active` 恒为真（不需要前台） |
| `btn_controller` / `keyboard_controller` | `MaaToolsKeyShim`，按游戏按键配置把 PC 按键反查成动作。例如 `press('space')` 会变成闪避 |
| `keyboard_controller.keyboard.type` | 转到 `input_str` |
| `screenshot_controller.init_screenshot` | 什么也不做 |
| `enable_background_mode` / `active_window` | 什么也不做 |

## 2. 画面：移动端变体

### 2.1 加载方式

`ScreenContext` 支持「画面变体」。平台为 PlayCover 时，`ZContext.init_controller()` 会把变体设为 `mobile`，然后重新加载画面：

1. 照常加载 PC 的 `assets/game_data/screen_info/`
2. 再读取 `assets/game_data/mobile/screen_info/*.yml`，按 `screen_id` 叠加上去

### 2.2 合并规则

- 画面的其它字段（如 `pc_alt`）：变体里写了就覆盖
- `area_list`：按 `area_name` 对应。变体里写了的字段覆盖 PC 区域，没写的字段沿用 PC
- 变体里新增的 `area_name`：作为新区域加入
- 区域写 `remove: true`：在移动端删除这个区域
- PC 里没有的 `screen_id`：作为移动端专属画面加入

所以变体文件只需要写**和 PC 不一样的地方**。例子见 `assets/game_data/mobile/screen_info/normal_world_basic.yml`：只改了「星期」「按钮-菜单」等几个区域的位置和识别标记，业务代码里用的区域名完全不变。

移动端的模板图片照常放在 `assets/template/` 下的独立子目录，在变体区域里改 `template_sub_dir` / `template_id` 指向它即可。

### 2.3 批量替换模板

很多画面共用的按钮（左上角返回、弹窗关闭、战斗暂停、迷失之地标签）在移动端位置统一。`assets/game_data/mobile/template_replace.yml` 里写一条规则就能替换所有用到某个模板的区域：

```yaml
- template: menu/back                # 原模板
  replace_template: mobile_menu/back # 替换后的模板
  pc_rect: [80, 20, 205, 110]        # 可选 替换后的区域范围
```

替换在按画面合并之前执行，单个画面的变体文件可以再覆盖。

### 2.4 缩放后匹配（template_scale）

区域可以写 `template_scale`：裁剪出区域后先按这个比例缩放再和模板匹配，默认 1。移动端的代理人头像比 PC 大约 1.2 倍，`战斗画面` 的头像区域写 `template_scale: 0.83`，直接复用 PC 的 348 个头像模板（置信度 0.91～0.96）。

### 2.5 保存

在画面管理界面里保存一个被变体覆盖的画面时，会写到 `assets/game_data/mobile/screen_info/` 下，PC 的画面文件和合并文件 `_od_merged.yml` 保持原样，不会被移动端的数据污染。

## 3. 模板变体和角色状态

### 3.1 模板变体

`TemplateLoader` 也有变体，名称和画面变体相同。设为 `mobile` 后，`get_template(sub_dir, id)` 先找 `assets/template/mobile_{sub_dir}/{id}`，没有再用原模板。所以移动端模板统一放在 `mobile_` 开头的子目录，例如 `mobile_battle/btn_normal_attack` 会自动替换 `battle/btn_normal_attack`。

变体目录里放一个 `_variant_only` 标记文件时，这个目录里没有的模板**不再回退**到原模板（返回空）。`mobile_agent_state` 用了这个标记：角色专属状态的 PC 模板坐标在移动端完全不对，读错位置比不读更糟。

### 3.2 角色状态

角色状态（能量、特殊技、终结技等）通过 `agent_state` 模板的 `point_list` 确定裁剪位置。移动端在 `assets/template/mobile_agent_state/` 下重新标定了通用状态（用 300 帧实战截图校验）：

| 状态 | 移动端位置 | 识别参数 |
|------|-----------|---------|
| 能量（前台 / 后台 1 / 后台 2） | 血条下方一行 y=91：x 450–670 / 820–890 / 1040–1110 | 沿用 PC（空的部分灰度约 64，有能量的 ≥108） |
| 前台特殊技、终结技 | 右下角特殊技、终结技按钮的圆 | 改为高饱和度判断（见下） |
| 切人-冷却 | 切人按钮半径 30 的圆 | 沿用 PC |
| 后台终结技 | 队友能量条左侧的橙色小条 | 颜色改为 (215–255,140–215,0–60)，接近满格才算 |
| 血量扣减 | 前台血条一行 y=72 | 颜色改为 (185–225,10–45,10–45) |

两人队伍的位置暂时和三人队前两个相同，还没实拍确认。格挡破碎和大部分角色专属状态还没有移动端模板。

**模板缺失时不记录状态**：`mobile_agent_state` 有 `_variant_only` 标记，移动端缺的模板不会回退到 PC 模板。这时各检查函数返回 -1（读不出来），状态不记录。以前返回 0，等于“读到了 0”，会让依赖它的规则误触发。例如 `叶瞬光-明心境` 一直是 0，「叶瞬光打能量」规则就把每次黄光都改成了闪避，叶瞬光在前台时从不切人触发极限支援。

已补的角色专属状态：叶瞬光的青溟剑势、明心境（和能量条同一位置，进入明心境后能量条变成浅蓝紫色），照的霜寒值。

**战斗按钮的其它识别**（`assets/game_data/mobile/screen_info/battle.yml`）：

| 区域 | 移动端做法 |
|------|-----------|
| 按键-切换角色（快速支援） | 快速支援时切换按钮变成支援角色头像，画法和 PC 一样但约 1.5 倍，配 `template_scale: 0.65` 后复用 PC 的 `battle/avatar_quick_*` 模板。裁剪和缩放统一用 `screen_utils.crop_area` |
| 按键-切换后援-可用颜色 | 切换后援（矩阵行动的协战代理人）是切换角色按钮左边的辐射图标按钮，冷却中灰色、可用时紫色，没有 PC 那样的黑色标记。配置了这个区域时，`_is_switch_backup_ready` 改为判断区域内过半像素落在 `color_range` 里；PC 没有这个区域，照旧用标记 + 灰度区域判断 |

**state_override**：状态模板的 `config.yml` 可以写 `state_override` 覆盖识别参数（`lower_color` / `upper_color` / `hsv_color` / `hsv_color_diff` / `connect_cnt` / `split_color_range` / `max_length` / `template_threshold`），不需要改状态定义。例如移动端特殊技按钮可用时整块变成彩色，不可用时是灰色但中间的星形图标也很亮，所以按 PC 的「白色高亮」会误判，改为统计高饱和度像素：

```yaml
state_override:
  hsv_color: [90, 177, 167]
  hsv_color_diff: [90, 78, 88]
  connect_cnt: 1000
```

### 3.3 式舆防卫战：判断一层是否打完

`ShiyuDefenseBattle` 在战斗画面里「连续 5 秒看不到倒计时」就认为这一层打完了，转去战斗后移动。移动端有几种情况会让这个判断误触发，导致角色站着不动：

| 情况 | 处理 |
|------|------|
| 阶段开头约 8 秒，倒计时位置显示任务提示 | 阶段开始后 12 秒内不做这个判断（`PHASE_START_GRACE_SECONDS`，通用逻辑） |
| Boss 出场后倒计时被 Boss 血条挤到下一行 | 移动端配置「式舆防卫战-倒计时-精英」区域（普通区域下移 95） |
| 倒计时是数码管字体，按轮廓个数判断时会随数字变化（节点 05 剩余约 1 分 10 秒时失效） | 配置了「式舆防卫战-倒计时文字」两个区域时，轮廓判断失败再用 OCR 读 `00:mm:ss` |
| Boss 机制阶段倒计时整段被机制提示替换 | 配置了「式舆防卫战-Boss血条」区域时，右上角有 Boss 血条（上下两条黑色长边框）也算战斗没结束 |

后三个区域只在移动端画面变体里配置，PC 没有这些区域时只按原来的轮廓判断。用录像按秒模拟过：节点 4 Boss 战、节点 05 第一间整场不再误判，节点 2 阶段 1 正常打完仍会转去移动。

## 4. 配置

| 配置 | 位置 | 默认值 |
|------|------|--------|
| 平台 | 实例的 `game_account.platform` | macOS 上默认 `PlayCover`，Windows 上默认 `PC` |
| MaaTools 地址 | 实例的 `game.maatools_host` | `127.0.0.1` |
| MaaTools 端口 | 实例的 `game.maatools_port` | `1717`，要和 PlayCover 游戏设置「绕过」页的端口一致 |
| 游戏 Bundle ID | 实例的 `game.playcover_bundle_id` | `com.miHoYo.Nap`（国服），用于输入文字时把游戏切到前台 |

## 5. 使用前准备

1. 安装 PlayCover 分支版，在游戏设置的「绕过」页勾选 MaaTools，端口保持 1717，不勾「从 Metal 抓取」（只对明日方舟生效）
2. 「图像设置」里使用 16:9 分辨率，例如 1920×1080
3. 启动游戏，窗口标题出现 `[localhost:1717]` 表示服务已开启
4. 需要输入文字（如兑换码）时，给运行脚本的程序开「辅助功能」权限

注意：MaaTools 监听的是所有网卡，同一局域网的其它设备也能连上并操作游戏。请只在可信网络下使用，或用 macOS 防火墙阻止外部连接。

### 5.1 GUI 在 macOS 上的差异

- 叠加层（游戏窗口上的悬浮信息）和画中画都依赖 Windows 窗口接口，macOS 上不启动、不显示入口
- 快捷键监听用 pynput。它的键盘监听线程会读取当前输入法的键盘布局，新版 macOS 只允许在主线程调用这个接口，否则进程直接崩溃（SIGTRAP）。所以启动监听前先在主线程读一次布局，监听线程直接使用这个结果
- 没有辅助功能权限时，快捷键（如 F9 开始运行）不生效，界面上的按钮照常可用

### 5.2 长时间运行的内存

实测过两处会让脚本进程的内存随运行时间一直增长的地方，都已处理：

- **截图接收**：每张截图约 15MB。以前边收边拼接（`buf += chunk`）再复制一份，每张图临时分配好几份大内存，600 张后进程涨到约 800MB 且不回落。现在按长度一次分配缓冲区，用 `recv_into` 直接写入，600 张稳定在约 80MB
- **onnxruntime 版本**：1.24.x 在 macOS arm64 上每跑一次 OCR 文字检测模型就有约 20～50MB 内存不释放（纯 onnxruntime、固定输入尺寸也能复现），整屏 OCR 60 次后进程涨到约 6GB。1.22 / 1.23 跑 40 次后封顶。所以 macOS 依赖固定为 `onnxruntime==1.23.2`，初始化后约 1GB，整屏 OCR 封顶约 1.3GB，速度不变

排查方法：用 `footprint -p <pid>` 看实际物理内存（比 RSS 准），用 `vmmap --summary <pid>` 区分「Malloc Large」（使用中）和「Malloc Large (empty)」（已释放未归还）。

## 6. 现状和后续工作

已完成：

- MaaTools 截图、多指触控、PC 动作转触控；镜头转向校准；无需辅助功能权限的文字输入
- macOS 依赖（CPU/CoreML 的 onnxruntime），Windows 专属模块改为条件导入；macOS 上 30 个应用全部能加载
- 画面变体（按区域合并、批量替换模板、缩放后匹配）和模板变体（含 `_variant_only`）
- 约 25 个移动端画面变体、十几个移动端模板；截图归档在测试仓 `screens/<画面>/移动端*.webp`
- 通用角色状态的移动端模板和 `state_override`
- 实测跑通：邮件、兑换码、每日签到、录像店营业、咖啡店、丽都城募、丽都周纪、活跃度奖励、随便观、情报板（含委托战斗获胜）、体力刷本（电量不足分支）、恶名狩猎（次数已用完分支）
- 迷失之地：入口 → 矩阵行动编队 → 武备选择 → 对话 → 进入下层 → 战斗 → 鸣徽选择 → 失败结算 都已跑通

未完成（按优先级）：

1. **角色专属状态**：照、叶瞬光等角色的专属资源条还没有移动端模板，需要逐个角色用实战截图标定
2. **格挡破碎、两人队伍**的状态位置待实拍
3. **迷失之地寻路**：按检测目标直线前进时偶尔被障碍物挡住，「无法脱困」后整局失败（PC 也用同样的寻路逻辑）
4. **触控布局补全**：连携技、锁定、切换后援的位置
5. **启动游戏**：`OpenGame` 仍然是 Windows 的启动 exe 流程，目前需要手动先打开游戏
6. **设置界面**：平台和 MaaTools 端口还没有 GUI 设置项，需要手动改实例配置
