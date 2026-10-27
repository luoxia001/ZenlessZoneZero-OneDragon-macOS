from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import cv2
from cv2.typing import MatLike

from one_dragon.base.controller.controller_base import ControllerBase
from one_dragon.base.controller.maatools.maatools_client import (
    MaaToolsClient,
    TouchPhase,
)
from one_dragon.base.geometry.point import Point
from one_dragon.base.geometry.rectangle import Rect
from one_dragon.utils.log_utils import log

if TYPE_CHECKING:
    from one_dragon.base.controller.drag_timing import DragTiming


class MaaToolsGameWindow:
    """
    游戏窗口的兼容对象

    MaaTools 直接和游戏进程通信，没有 Windows 的窗口句柄。
    业务代码会读取 controller.game_win 的少数属性（标题、是否激活等），这里给出等价的值。
    """

    def __init__(self, client: MaaToolsClient, win_title: str, standard_width: int, standard_height: int) -> None:
        self.client: MaaToolsClient = client
        self.win_title: str = win_title
        self.standard_width: int = standard_width
        self.standard_height: int = standard_height

    @property
    def is_win_valid(self) -> bool:
        return self.client.is_connected or self.client.connect()

    @property
    def is_win_active(self) -> bool:
        """MaaTools 不需要游戏在前台 一律视为激活"""
        return self.is_win_valid

    @property
    def is_win_scale(self) -> bool:
        return False

    def init_win(self) -> None:
        self.client.connect()

    def active(self) -> bool:
        """不需要激活窗口"""
        return self.is_win_valid

    def get_win(self) -> MaaToolsGameWindow | None:
        return self if self.is_win_valid else None

    @property
    def win_rect(self) -> Rect:
        return Rect(0, 0, self.standard_width, self.standard_height)

    def get_win_rect(self) -> Rect:
        return self.win_rect


class MaaToolsScreenshotController:
    """截图控制器的兼容对象 MaaTools 只有一种截图方式 切换截图方法时什么也不做"""

    def init_screenshot(self, method: str) -> str:
        return method


class MaaToolsControllerBase(ControllerBase):
    """
    基于 MaaTools 协议的触屏控制器基类

    适用于通过 PlayCover 分支版运行的 iOS 游戏。
    - 截图：在游戏进程内截图 游戏窗口可以在后台
    - 输入：多指触控 每个 contact 编号是一根独立的手指
    - 坐标：对外统一使用标准分辨率（默认 1920x1080）的游戏坐标 内部再换算到触控坐标空间
    """

    SCREENSHOT_METHOD: str = 'maatools'

    # 手指编号的分配 子类的按键手指从 BUTTON_CONTACT_START 开始
    CLICK_CONTACT: int = 9  # 普通点击和拖拽 一次只做一件事
    BUTTON_CONTACT_START: int = 10

    # 点按时手指按住的时长 实测绝区零 iOS 版 0.05 秒的点按不会被识别 0.15 秒稳定
    TAP_PRESS_TIME: float = 0.15

    SCREENSHOT_RETRY_TIMES: int = 3  # 截图返回空图时的重试次数

    def __init__(
            self,
            host: str,
            port: int,
            win_title: str,
            standard_width: int = 1920,
            standard_height: int = 1080,
    ) -> None:
        ControllerBase.__init__(self)
        self.standard_width: int = standard_width
        self.standard_height: int = standard_height
        self.client: MaaToolsClient = MaaToolsClient(host=host, port=port)
        self.game_win: MaaToolsGameWindow = MaaToolsGameWindow(
            self.client, win_title, standard_width, standard_height)
        self.screenshot_controller: MaaToolsScreenshotController = MaaToolsScreenshotController()
        self.screenshot_method: str = MaaToolsControllerBase.SCREENSHOT_METHOD
        self.background_mode: bool = False  # 兼容 PC 控制器的属性 MaaTools 没有手柄模式

        self._contact_lock: threading.Lock = threading.Lock()
        self._contact_pos: dict[int, Point] = {}  # 当前按下的手指 -> 标准坐标

    # ------------------- 连接与窗口 -------------------

    def init_game_win(self) -> bool:
        return self.client.connect()

    def init_before_context_run(self) -> bool:
        return self.client.connect()

    @property
    def is_game_window_ready(self) -> bool:
        return self.client.is_connected or self.client.connect()

    def active_window(self) -> None:
        """MaaTools 不需要激活窗口"""
        pass

    def set_window_title(self, new_title: str) -> None:
        self.game_win.win_title = new_title

    def enable_foreground_mode(self) -> None:
        pass

    def enable_background_mode(self, gamepad_type: str = 'xbox') -> None:
        log.info('MaaTools 本身就可以在后台运行 忽略后台模式设置')

    def cleanup_after_app_shutdown(self) -> None:
        self.release_all_touches()
        self.client.close()

    def close_game(self) -> None:
        self.release_all_touches()
        self.client.terminate()

    @property
    def center_point(self) -> Point:
        return Point(self.standard_width // 2, self.standard_height // 2)

    # ------------------- 截图 -------------------

    def get_screenshot(self, independent: bool = False) -> MatLike | None:
        """
        截图 并缩放到标准分辨率

        Args:
            independent: 兼容参数 MaaTools 截图本身就不影响游戏

        Returns:
            标准分辨率的 RGB 图像 失败时返回 None
        """
        screen = self.client.screenshot()
        for _ in range(MaaToolsControllerBase.SCREENSHOT_RETRY_TIMES):
            # 游戏切换画面的瞬间偶尔会返回空图 稍等再截一次
            if screen is not None:
                break
            time.sleep(0.02)
            screen = self.client.screenshot()
        if screen is None:
            return None
        screen = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)  # 项目内的图片统一是 RGB
        if screen.shape[1] != self.standard_width or screen.shape[0] != self.standard_height:
            screen = cv2.resize(screen, (self.standard_width, self.standard_height), interpolation=cv2.INTER_AREA)
        return screen

    # ------------------- 触控基础 -------------------

    def _to_touch(self, pos: Point) -> tuple[int, int]:
        """标准坐标 -> 触控坐标空间"""
        if not self.client.is_connected:  # 连接后才知道触控坐标空间的大小
            self.client.connect()
        width = self.client.touch_width or self.standard_width
        height = self.client.touch_height or self.standard_height
        return (round(pos.x * width / self.standard_width),
                round(pos.y * height / self.standard_height))

    def touch_down(self, contact: int, pos: Point) -> bool:
        """
        按下一根手指

        Args:
            contact: 手指编号
            pos: 标准坐标

        Returns:
            是否成功
        """
        with self._contact_lock:
            if contact in self._contact_pos:  # 同一根手指重复按下 先松开旧的
                old = self._contact_pos.pop(contact)
                self.client.touch(TouchPhase.ENDED, *self._to_touch(old), contact=contact)
            ok = self.client.touch(TouchPhase.BEGAN, *self._to_touch(pos), contact=contact)
            if ok:
                self._contact_pos[contact] = pos
            return ok

    def touch_move(self, contact: int, pos: Point) -> bool:
        """移动一根已经按下的手指"""
        with self._contact_lock:
            if contact not in self._contact_pos:
                return False
            ok = self.client.touch(TouchPhase.MOVED, *self._to_touch(pos), contact=contact)
            if ok:
                self._contact_pos[contact] = pos
            return ok

    def touch_up(self, contact: int, pos: Point | None = None) -> bool:
        """
        抬起一根手指

        Args:
            contact: 手指编号
            pos: 抬起的位置 为空时在当前位置抬起
        """
        with self._contact_lock:
            last = self._contact_pos.pop(contact, None)
            if last is None:
                return False
            return self.client.touch(TouchPhase.ENDED, *self._to_touch(pos or last), contact=contact)

    def is_touching(self, contact: int) -> bool:
        with self._contact_lock:
            return contact in self._contact_pos

    def release_all_touches(self) -> None:
        """抬起所有手指 用于停止运行时防止手指卡住"""
        with self._contact_lock:
            contacts = list(self._contact_pos.items())
            self._contact_pos.clear()
        for contact, pos in contacts:
            self.client.touch(TouchPhase.ENDED, *self._to_touch(pos), contact=contact)

    def touch_tap(self, contact: int, pos: Point, press_time: float | None = None) -> bool:
        """
        在某个位置点按

        Args:
            contact: 手指编号
            pos: 标准坐标
            press_time: 按住时长 为空时使用 TAP_PRESS_TIME
        """
        if not self.touch_down(contact, pos):
            return False
        time.sleep(press_time if press_time is not None else MaaToolsControllerBase.TAP_PRESS_TIME)
        return self.touch_up(contact, pos)

    def touch_swipe(self, contact: int, start: Point, end: Point,
                    press_wait: float = 0.05, move_duration: float = 0.3, release_wait: float = 0.05) -> bool:
        """
        一根手指从起点滑到终点

        Args:
            contact: 手指编号
            start: 起点 标准坐标
            end: 终点 标准坐标
            press_wait: 按下后等待多久再开始移动
            move_duration: 移动耗时
            release_wait: 到达终点后等待多久再抬起
        """
        if not self.touch_down(contact, start):
            return False
        time.sleep(press_wait)
        steps = max(int(move_duration / 0.016), 2)  # 大约 60 帧每秒
        for i in range(1, steps + 1):
            t = i / steps
            self.touch_move(contact, Point(start.x + (end.x - start.x) * t, start.y + (end.y - start.y) * t))
            time.sleep(move_duration / steps)
        time.sleep(release_wait)
        return self.touch_up(contact, end)

    # ------------------- ControllerBase 接口 -------------------

    def click(self, pos: Point = None, press_time: float = 0, pc_alt: bool = False,
              gamepad_key: str | None = None) -> bool:
        """
        点击位置

        Args:
            pos: 标准坐标 为空时点击画面中心
            press_time: 大于0时长按若干秒
            pc_alt: 只在 PC 端有用 这里忽略
            gamepad_key: 只在手柄后台模式有用 这里忽略
        """
        if pos is None:
            pos = self.center_point
        if not (0 <= pos.x < self.standard_width and 0 <= pos.y < self.standard_height):
            log.error(f'点击位置不在游戏画面内 {pos}')
            return False
        return self.touch_tap(MaaToolsControllerBase.CLICK_CONTACT, pos, press_time if press_time > 0 else None)

    def mouse_move(self, pos: Point) -> None:
        """触屏没有鼠标悬停 移开鼠标的操作直接忽略"""
        pass

    def drag_to(
        self, end: Point, start: Point | None = None, duration: float = 0.5,
        *, timing: DragTiming | None = None,
    ) -> None:
        """按住拖拽 参数含义和 ControllerBase.drag_to 一致"""
        if start is None:
            start = self.center_point
        if timing is None:
            self.touch_swipe(MaaToolsControllerBase.CLICK_CONTACT, start, end,
                             press_wait=0.05, move_duration=max(duration - 0.1, 0.1), release_wait=0.05)
        else:
            self.touch_swipe(MaaToolsControllerBase.CLICK_CONTACT, start, end,
                             press_wait=timing.press_wait, move_duration=max(timing.move_duration, 0.05),
                             release_wait=timing.release_wait)

    def scroll(self, down: int, pos: Point | None = None) -> None:
        """
        滚动 触屏上用竖向滑动代替 每格滚轮约等于滑动 100 像素

        Args:
            down: 正数向下滚动（手指向上滑） 负数向上滚动
            pos: 滚动位置
        """
        if down == 0:
            return
        if pos is None:
            pos = self.center_point
        # 终点限制在画面内
        dy = min(max(-down * 100, 1 - pos.y), self.standard_height - 1 - pos.y)
        self.touch_swipe(MaaToolsControllerBase.CLICK_CONTACT, pos, Point(pos.x, pos.y + dy),
                         press_wait=0.05, move_duration=0.3, release_wait=0.15)
