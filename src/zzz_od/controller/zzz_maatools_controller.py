import math
import threading
import time
from pathlib import Path

from cv2.typing import MatLike

from one_dragon.base.controller.maatools.maatools_controller_base import (
    MaaToolsControllerBase,
)
from one_dragon.base.controller.maatools.macos_text_input import MacosTextInput
from one_dragon.base.geometry.point import Point
from one_dragon.utils import cv2_utils, os_utils, yaml_utils
from one_dragon.utils.log_utils import log
from zzz_od.config.game_config import GameConfig
from zzz_od.const import game_const


class MobileTouchLayout:
    """移动端触控布局 来自 assets/game_data/mobile/touch_layout.yml"""

    def __init__(self, data: dict) -> None:
        uid = data.get('uid_rect') or [0, 0, 0, 0]
        self.uid_rect: tuple[int, int, int, int] = (int(uid[0]), int(uid[1]), int(uid[2]), int(uid[3]))

        joystick = data.get('joystick') or {}
        center = joystick.get('center') or [424, 780]
        self.joystick_center: Point = Point(center[0], center[1])
        self.joystick_radius: float = float(joystick.get('radius', 90))

        camera = data.get('camera') or {}
        rect = camera.get('rect') or [640, 150, 1400, 650]
        self.camera_rect: tuple[int, int, int, int] = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
        self.camera_scale: float = float(camera.get('scale', 0.5))
        self.camera_slop: float = float(camera.get('slop', 0))
        self.camera_max_stroke: float = float(camera.get('max_stroke', 200))

        paste = data.get('text_paste_button')
        self.text_paste_button: Point | None = None if paste is None else Point(paste[0], paste[1])

        self.buttons: dict[str, Point | None] = {}
        # 写成 [x, y, dx, dy] 的按键不是点按 而是从 (x, y) 滑动 (dx, dy) 例如切到上一个角色
        self.button_swipes: dict[str, Point] = {}
        for action, pos in (data.get('buttons') or {}).items():
            self.buttons[action] = None if pos is None else Point(pos[0], pos[1])
            if pos is not None and len(pos) >= 4:
                self.button_swipes[action] = Point(pos[2], pos[3])

    @staticmethod
    def default_file_path() -> Path:
        return Path(os_utils.get_path_under_work_dir('assets', 'game_data', 'mobile')) / 'touch_layout.yml'

    @classmethod
    def load(cls, file_path: Path | None = None) -> 'MobileTouchLayout':
        file_path = file_path or cls.default_file_path()
        data: dict = {}
        if file_path.exists():
            with file_path.open(encoding='utf-8') as file:
                data = yaml_utils.safe_load(file) or {}
        else:
            log.warning(f'移动端触控布局文件不存在 使用默认值 {file_path}')
        return cls(data)


class MaaToolsKeyShim:
    """
    按键控制器的兼容对象

    少数业务代码直接调用 controller.btn_controller / controller.keyboard_controller 按某个 PC 按键。
    这里按游戏按键配置把 PC 按键反查成动作（例如 'space' → dodge），再转成触控。
    """

    def __init__(self, controller: 'ZMaaToolsController') -> None:
        self.controller: ZMaaToolsController = controller
        self.keyboard: MaaToolsKeyShim = self  # 兼容 keyboard_controller.keyboard.type(...)

    def _to_action(self, key: str) -> str | None:
        key_to_action = {v: k for k, v in self.controller.action_keys.items()}
        action = key_to_action.get(key)
        if action is None:
            log.warning(f'触屏模式下无法模拟按键 {key}')
        return action

    def tap(self, key: str) -> None:
        action = self._to_action(key)
        if action is not None:
            self.controller.do_action(action)

    def press(self, key: str, press_time: float | None = None) -> None:
        action = self._to_action(key)
        if action is not None:
            self.controller.do_action(action, press=True, press_time=press_time)

    def release(self, key: str) -> None:
        action = self._to_action(key)
        if action is not None:
            self.controller.do_action(action, release=True)

    def reset(self) -> None:
        self.controller.release_all_touches()

    def set_key_press_time(self, press_time: float) -> None:
        pass

    def type(self, text: str) -> None:
        self.controller.input_str(text)


class ZMaaToolsController(MaaToolsControllerBase):
    """
    绝区零 iOS 版（PlayCover + MaaTools）的控制器

    对外提供和 ZPcController 相同的动作接口（move_w / dodge / turn_by_distance 等），
    内部把 PC 的「按住 / 松开」语义转成多指触控：
    - 手指 0：左下摇杆 按住不放就一直移动
    - 手指 1：拖动镜头
    - 手指 9：普通点击和拖拽
    - 手指 10 起：每个战斗按键一根手指 可以和移动同时按
    """

    JOYSTICK_CONTACT: int = 0
    # 战斗按键点按时按住的时长 实测切换角色按住 0.03 秒就能生效
    # 比菜单点击的 TAP_PRESS_TIME 短很多 黄光切人这类连按几个按键的操作要靠它赶上时间窗口
    BATTLE_TAP_TIME: float = 0.05
    # 这些动作在大世界里用 按菜单按钮的时长点按
    LONG_TAP_ACTIONS: set[str] = {'interact'}
    # 这些动作要双击 例如取消连携技（游戏提示「双击空白区域取消」）
    DOUBLE_TAP_ACTIONS: set[str] = {'chain_cancel'}
    BUTTON_SWIPE_TIME: float = 0.1  # 按键配置成滑动时 滑动用的时长
    CAMERA_DRAG_SPEED: float = 600  # 拖镜头的速度 像素/秒 游戏的镜头转动和滑动速度有关 用固定的慢速让转向角度和距离成正比
    CAMERA_CONTACT: int = 1

    MOVE_DIRECTIONS: dict[str, tuple[int, int]] = {
        'move_w': (0, -1),
        'move_s': (0, 1),
        'move_a': (-1, 0),
        'move_d': (1, 0),
    }

    def __init__(
            self,
            game_config: GameConfig,
            win_title: str,
            standard_width: int = 1920,
            standard_height: int = 1080,
            layout: MobileTouchLayout | None = None,
    ) -> None:
        MaaToolsControllerBase.__init__(
            self,
            host=game_config.maatools_host,
            port=game_config.maatools_port,
            win_title=win_title,
            standard_width=standard_width,
            standard_height=standard_height,
        )
        self.game_config: GameConfig = game_config
        self.action_keys: dict[str, str] = game_config.get_action_keys('keyboard')
        self.layout: MobileTouchLayout = layout or MobileTouchLayout.load()
        self.text_input: MacosTextInput = MacosTextInput(game_config.playcover_bundle_id)

        self.btn_controller: MaaToolsKeyShim = MaaToolsKeyShim(self)
        self.keyboard_controller: MaaToolsKeyShim = self.btn_controller

        self.is_moving: bool = False  # 是否正在向前移动
        self._move_lock: threading.Lock = threading.Lock()
        self._pressed_moves: set[str] = set()  # 当前按住的方向键
        self._button_contacts: dict[str, int] = {}  # 动作 -> 手指编号
        self._warned_actions: set[str] = set()

    def sync_game_config(self, game_config: GameConfig) -> None:
        """切换实例后同步控制器持有的账号级配置"""
        self.game_config = game_config
        self.action_keys = game_config.get_action_keys('keyboard')
        self.text_input = MacosTextInput(game_config.playcover_bundle_id)
        self.client.host = game_config.maatools_host
        self.client.port = game_config.maatools_port

    def fill_uid_black(self, screen: MatLike) -> MatLike:
        """遮挡右下角 UID"""
        x1, y1, x2, y2 = self.layout.uid_rect
        if x2 <= x1 or y2 <= y1:
            return screen
        return cv2_utils.mark_area_as_color(
            screen,
            pos=[x1, y1, x2 - x1, y2 - y1],
            color=game_const.YOLO_DEFAULT_COLOR,
            new_image=True
        )

    # ------------------- 文字输入 -------------------

    def input_str(self, to_input: str, interval: float = 0.1) -> None:
        """
        在当前选中的输入框里输入文字
        先写进剪贴板 有辅助功能权限时发 Cmd+V 否则点输入框自带的粘贴按钮
        """
        self.text_input.copy_to_clipboard(to_input)
        if self.text_input.is_accessibility_trusted():
            self.text_input.paste_by_shortcut()
        elif self.layout.text_paste_button is not None:
            time.sleep(0.2)
            self.click(self.layout.text_paste_button)
        else:
            log.error('没有辅助功能权限 触控布局里也没有配置粘贴按钮 无法输入文字')

    def delete_all_input(self) -> None:
        self.text_input.delete_all_input()

    # ------------------- 战斗按键 -------------------

    def _get_button_contact(self, action: str) -> int:
        if action not in self._button_contacts:
            self._button_contacts[action] = MaaToolsControllerBase.BUTTON_CONTACT_START + len(self._button_contacts)
        return self._button_contacts[action]

    def do_action(self, action: str, press: bool = False, press_time: float | None = None,
                  release: bool = False) -> None:
        """
        执行一个游戏动作 语义和 ZPcController._action_btn 一致

        Args:
            action: 动作名 例如 dodge / move_w
            press: 按下 有 press_time 时按住这么久后松开 没有时一直按住
            press_time: 按住时长
            release: 松开
        """
        if action in ZMaaToolsController.MOVE_DIRECTIONS:
            self._move_action(action, press, press_time, release)
            return

        pos = self.layout.buttons.get(action)
        if pos is None:
            # 停止时会松开所有按键 没配置的按键本来就没按下 不用提示
            if not release and action not in self._warned_actions:
                self._warned_actions.add(action)
                log.warning(f'触控布局里没有配置按键位置 {action}')
            return

        contact = self._get_button_contact(action)
        swipe = self.layout.button_swipes.get(action)
        if swipe is not None:
            # 滑动没有按住的说法 按下和点按都滑一次 松开时什么也不做
            if not release:
                self.touch_swipe(contact, pos, pos + swipe, press_wait=0.02,
                                 move_duration=ZMaaToolsController.BUTTON_SWIPE_TIME, release_wait=0.02)
        elif action in ZMaaToolsController.DOUBLE_TAP_ACTIONS:
            # 双击没有按住的说法 按下和点按都双击一次 松开时什么也不做
            if not release:
                self.touch_tap(contact, pos, press_time=ZMaaToolsController.BATTLE_TAP_TIME)
                time.sleep(0.08)
                self.touch_tap(contact, pos, press_time=ZMaaToolsController.BATTLE_TAP_TIME)
        elif press:
            # 和 PC 键盘一样 已经按住的键再按下不会松开重按
            # 战斗配置常用「按下 等待 按下 等待 ... 松开」表示一直按住 例如蕾米埃尔长按强化特殊技
            # 如果每次按下都先抬起再按 游戏收到的是一串短按 长按技能放不出来
            if not self.is_touching(contact):
                self.touch_down(contact, pos)
            if press_time is not None:
                time.sleep(press_time)
                self.touch_up(contact)
        elif release:
            self.touch_up(contact)
        else:
            press_time = None if action in ZMaaToolsController.LONG_TAP_ACTIONS else ZMaaToolsController.BATTLE_TAP_TIME
            self.touch_tap(contact, pos, press_time=press_time)

    def dodge(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """闪避"""
        self.do_action('dodge', press, press_time, release)

    def switch_next(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """切换角色-下一个"""
        self.do_action('switch_next', press, press_time, release)

    def switch_prev(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """切换角色-上一个"""
        self.do_action('switch_prev', press, press_time, release)

    def switch_backup(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """切换后援"""
        self.do_action('switch_backup', press, press_time, release)

    def normal_attack(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """普通攻击"""
        self.do_action('normal_attack', press, press_time, release)

    def special_attack(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """特殊攻击"""
        self.do_action('special_attack', press, press_time, release)

    def ultimate(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """终结技"""
        self.do_action('ultimate', press, press_time, release)

    def chain_left(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """连携技-左"""
        self.do_action('chain_left', press, press_time, release)

    def chain_right(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """连携技-右"""
        self.do_action('chain_right', press, press_time, release)

    def interact(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """交互"""
        self.do_action('interact', press, press_time, release)

    def lock(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """锁定敌人"""
        self.do_action('lock', press, press_time, release)

    def chain_cancel(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """取消连携"""
        self.do_action('chain_cancel', press, press_time, release)

    def btn_tap(self, key: str) -> None:
        """按一下 PC 按键 兼容 PcControllerBase.btn_tap"""
        self.btn_controller.tap(key)

    # ------------------- 移动 -------------------

    def _move_action(self, action: str, press: bool, press_time: float | None, release: bool) -> None:
        if press:
            self._set_move_pressed(action, True)
            if press_time is not None:
                time.sleep(press_time)
                self._set_move_pressed(action, False)
        elif release:
            self._set_move_pressed(action, False)
        else:  # 点按 和键盘按一下的效果接近
            self._set_move_pressed(action, True)
            time.sleep(0.1)
            self._set_move_pressed(action, False)

    def _set_move_pressed(self, action: str, pressed: bool) -> None:
        """更新按住的方向 再把摇杆推到对应方向"""
        with self._move_lock:
            if pressed:
                self._pressed_moves.add(action)
            else:
                self._pressed_moves.discard(action)

            dx = sum(ZMaaToolsController.MOVE_DIRECTIONS[a][0] for a in self._pressed_moves)
            dy = sum(ZMaaToolsController.MOVE_DIRECTIONS[a][1] for a in self._pressed_moves)
            center = self.layout.joystick_center
            if dx == 0 and dy == 0:
                self.touch_up(ZMaaToolsController.JOYSTICK_CONTACT, center)
                return

            length = math.hypot(dx, dy)
            radius = self.layout.joystick_radius
            target = Point(center.x + dx / length * radius, center.y + dy / length * radius)
            if self.is_touching(ZMaaToolsController.JOYSTICK_CONTACT):
                self.touch_move(ZMaaToolsController.JOYSTICK_CONTACT, target)
                return

            # 先在摇杆中心按下 再分几步推出去 一下子跳到边缘时游戏可能不认
            self.touch_down(ZMaaToolsController.JOYSTICK_CONTACT, center)
            for i in range(1, 4):
                time.sleep(0.016)
                t = i / 3
                self.touch_move(ZMaaToolsController.JOYSTICK_CONTACT,
                                Point(center.x + (target.x - center.x) * t, center.y + (target.y - center.y) * t))

    def move_w(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向前移动"""
        self.do_action('move_w', press, press_time, release)

    def move_s(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向后移动"""
        self.do_action('move_s', press, press_time, release)

    def move_a(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向左移动"""
        self.do_action('move_a', press, press_time, release)

    def move_d(self, press: bool = False, press_time: float | None = None, release: bool = False) -> None:
        """向右移动"""
        self.do_action('move_d', press, press_time, release)

    def start_moving_forward(self) -> None:
        """开始向前移动"""
        if self.is_moving:
            return
        self.is_moving = True
        self.move_w(press=True)

    def stop_moving_forward(self) -> None:
        """停止向前移动"""
        self.is_moving = False
        self.move_w(release=True)

    def release_all_touches(self) -> None:
        with self._move_lock:
            self._pressed_moves.clear()
        self.is_moving = False
        MaaToolsControllerBase.release_all_touches(self)

    # ------------------- 镜头 -------------------

    def turn_by_distance(self, d: float) -> None:
        """
        横向转向 按距离转

        Args:
            d: PC 鼠标的像素距离 正数往右转 负数往左转
        """
        self.move_mouse_relative(d, 0)

    def turn_vertical_by_distance(self, d: float) -> None:
        """
        纵向转向 按距离转

        Args:
            d: PC 鼠标的像素距离 正数往下转 负数往上转
        """
        self.move_mouse_relative(0, d)

    def turn_by_angle_diff(self, angle_diff: float) -> None:
        """
        按照给定角度偏移进行转向

        Args:
            angle_diff: 角度偏移 逆时针为正
        """
        self.turn_by_distance(self.game_config.turn_dx * angle_diff)

    def move_mouse_relative(self, dx: float, dy: float) -> None:
        """
        模拟 PC 鼠标相对移动 用手指 1 在镜头区域里拖动

        游戏的触屏镜头有两个特点 实测得出：
        - 手指移动不到 camera.slop 像素时镜头不转（触摸死区）；超过后整段移动都算数。
          所以短距离拖动时先越过死区再退回目标位置 净移动量就是想要的距离
        - 松手时手指还在动会有惯性 长距离快速拖动转得更多 所以匀速慢拖 停住后再松手 并把长距离拆成多次

        Args:
            dx: PC 鼠标横向像素 正数向右
            dy: PC 鼠标纵向像素 正数向下
        """
        if dx == 0 and dy == 0:
            return
        layout = self.layout
        remain_x = dx * layout.camera_scale
        remain_y = dy * layout.camera_scale
        while abs(remain_x) >= 1 or abs(remain_y) >= 1:
            length = math.hypot(remain_x, remain_y)
            ratio = min(1.0, layout.camera_max_stroke / length)
            step_x, step_y = remain_x * ratio, remain_y * ratio
            self._camera_stroke(step_x, step_y)
            remain_x -= step_x
            remain_y -= step_y

    def _camera_stroke(self, step_x: float, step_y: float) -> None:
        """
        一次拖镜头：按下 → 匀速拖动 step（太短时先越过死区再退回） → 停住 → 松手

        Args:
            step_x: 需要生效的横向拖动像素
            step_y: 需要生效的纵向拖动像素
        """
        layout = self.layout
        length = math.hypot(step_x, step_y)
        if length < 1:
            return
        ux, uy = step_x / length, step_y / length
        x1, y1, x2, y2 = layout.camera_rect
        center = Point((x1 + x2) / 2, (y1 + y2) / 2)
        # 起点放在反方向一侧 让整段拖动都留在镜头区域里
        reach = max(length, layout.camera_slop)
        start = Point(center.x - ux * reach / 2, center.y - uy * reach / 2)

        # 手指依次经过的距离 短于死区时先走到死区外再退回
        path = [reach] if length >= layout.camera_slop else [layout.camera_slop, length]

        contact = ZMaaToolsController.CAMERA_CONTACT
        self.touch_down(contact, start)
        time.sleep(0.03)
        current = 0.0
        for target in path:
            distance = abs(target - current)
            steps = max(int(distance / 10), 1)
            step_time = distance / ZMaaToolsController.CAMERA_DRAG_SPEED / steps
            for i in range(1, steps + 1):
                d = current + (target - current) * i / steps
                self.touch_move(contact, Point(start.x + ux * d, start.y + uy * d))
                time.sleep(step_time)
            current = target
        # 停住再松手 避免惯性
        time.sleep(0.1)
        self.touch_up(contact)
