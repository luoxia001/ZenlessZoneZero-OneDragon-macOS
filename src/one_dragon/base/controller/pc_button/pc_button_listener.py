import contextlib
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from pynput import keyboard, mouse

from one_dragon.utils import thread_utils
from one_dragon.utils.log_utils import log

_darwin_keycode_context_ready: bool = False


def _prepare_darwin_keycode_context() -> None:
    """
    macOS 下提前在主线程读取键盘布局 给 pynput 的键盘监听线程使用

    pynput 的键盘监听线程启动时会读取当前输入法的键盘布局。
    新版 macOS 要求这个接口只能在主线程调用 在其他线程调用会直接崩溃（SIGTRAP）。
    所以在主线程读取一次 再让监听线程直接使用读到的结果。
    """
    global _darwin_keycode_context_ready
    if _darwin_keycode_context_ready:
        return

    from pynput._util import darwin as pynput_darwin
    from pynput.keyboard import _darwin as pynput_keyboard_darwin

    result: dict[str, tuple] = {}
    done = threading.Event()

    def read_context() -> None:
        try:
            with pynput_darwin.keycode_context() as context:
                result['context'] = context
        finally:
            done.set()

    if threading.current_thread() is threading.main_thread():
        read_context()
    else:
        # GUI 里初始化在后台线程 主线程在跑 Qt 事件循环 可以把读取交给主线程
        from PyObjCTools import AppHelper
        AppHelper.callAfter(read_context)
        if not done.wait(timeout=5):
            log.warning('主线程没有及时读取键盘布局 不启动键盘监听')
            return

    if 'context' not in result:
        return
    cached_context = result['context']

    @contextlib.contextmanager
    def cached_keycode_context():
        yield cached_context

    pynput_keyboard_darwin.keycode_context = cached_keycode_context
    _darwin_keycode_context_ready = True


class PcButtonListener:

    def __init__(self,
                 on_button_tap: Callable[[str], None],
                 listen_keyboard: bool = False,
                 listen_mouse: bool = False,
                 listen_gamepad: bool = False,
                 ):
        self.keyboard_listener = keyboard.Listener(on_press=self._on_keyboard_press)
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self.gamepad_listener = None

        self.on_button_tap: Callable[[str], None] = on_button_tap

        self.listen_keyboard: bool = listen_keyboard
        self.listen_mouse: bool = listen_mouse
        self.listen_gamepad: bool = listen_gamepad

        self._executor = ThreadPoolExecutor(thread_name_prefix='od_key_mouse_btn_listener', max_workers=8)

    def _on_keyboard_press(self, event):
        if isinstance(event, keyboard.Key):
            k = event.name
        elif isinstance(event, keyboard.KeyCode):
            # 处理小键盘按键和特殊按键
            if event.char is not None:
                k = event.char
            elif hasattr(event, 'vk') and event.vk is not None:
                # 使用虚拟键码来识别小键盘按键
                k = self._get_numpad_key_name(event.vk)
            elif hasattr(event, 'vk'):
                k = f'vk_{event.vk}'  # vk 为 None 的情况
            else:
                k = 'unknown'  # 没有 vk 属性
        else:
            return

        # 确保按键名称不为空
        if k is None or k == '':
            return

        self._call_button_tap_callback(k)

    def _get_numpad_key_name(self, vk: int) -> str:
        """
        根据虚拟键码获取小键盘按键名称
        :param vk: 虚拟键码
        :return: 按键名称
        """
        # 小键盘数字键: vk 96-105 对应 numpad_0 到 numpad_9
        if 96 <= vk <= 105:
            return f'numpad_{vk - 96}'

        # 其他按键返回通用格式
        return f'vk_{vk}'

    def _on_mouse_click(self, x, y, button: mouse.Button, pressed):
        if pressed == 1:
            self._call_button_tap_callback('mouse_' + button.name)

    def _call_button_tap_callback(self, key: str) -> None:
        if self.on_button_tap is not None:
            future: Future = self._executor.submit(self.on_button_tap, key)
            future.add_done_callback(thread_utils.handle_future_result)

    def start(self):
        if sys.platform == 'darwin':
            # pynput 的键盘和鼠标监听线程会同时读取 PyObjC 懒加载的 AXIsProcessTrusted
            # 两个线程并发解析同一个符号时 PyObjC 会抛 KeyError 导致监听线程退出
            # 先在主线程解析一次 后面线程直接用缓存
            import HIServices
            _ = HIServices.AXIsProcessTrusted
        if self.listen_keyboard:
            if sys.platform == 'darwin':
                _prepare_darwin_keycode_context()
                if not _darwin_keycode_context_ready:
                    self.listen_keyboard = False
        if self.listen_keyboard:
            self.keyboard_listener.start()
        if self.listen_mouse:
            self.mouse_listener.start()

    def stop(self):
        self.keyboard_listener.stop()
        self.mouse_listener.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
