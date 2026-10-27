import subprocess
import time

from one_dragon.utils.log_utils import log, mask_text

# macOS 虚拟键码
_KEY_V: int = 9
_KEY_A: int = 0
_KEY_DELETE: int = 51


class MacosTextInput:
    """
    macOS 下给 PlayCover 游戏输入文字

    MaaTools 协议不支持文字输入。iOS 游戏和 macOS 共用剪贴板，所以先把文字写进剪贴板，再用下面任一方式粘贴：
    - 发送 Cmd+V：需要短暂把游戏切到前台，并且要在「系统设置 → 隐私与安全性 → 辅助功能」里给运行脚本的程序授权
    - 点游戏输入框自带的粘贴按钮：不需要授权 由调用方用触控完成
    """

    def __init__(self, bundle_id: str) -> None:
        self.bundle_id: str = bundle_id

    def _find_app(self):
        import AppKit
        apps = AppKit.NSRunningApplication.runningApplicationsWithBundleIdentifier_(self.bundle_id)
        return apps[0] if apps else None

    @staticmethod
    def _post_key(keycode: int, command: bool = False) -> None:
        import Quartz
        for down in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
            if command:
                Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(0.02)

    def _run_in_foreground(self, action) -> bool:
        import AppKit
        app = self._find_app()
        if app is None:
            log.error(f'未找到运行中的游戏 {self.bundle_id}')
            return False
        previous = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.3)
        try:
            action()
        finally:
            time.sleep(0.2)
            if previous is not None and previous.bundleIdentifier() != self.bundle_id:
                previous.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        return True

    @staticmethod
    def is_accessibility_trusted() -> bool:
        """运行脚本的程序是否有辅助功能权限 没有时发不出 Cmd+V"""
        import ApplicationServices
        return bool(ApplicationServices.AXIsProcessTrusted())

    @staticmethod
    def copy_to_clipboard(text: str) -> None:
        """把文字写进 macOS 剪贴板"""
        log.info(f'复制文字到剪贴板 {mask_text(text)}')
        subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=False)

    def paste_by_shortcut(self) -> bool:
        """
        把游戏切到前台 发送 Cmd+V 粘贴到当前选中的输入框

        Returns:
            是否成功发送
        """
        return self._run_in_foreground(lambda: self._post_key(_KEY_V, command=True))

    def delete_all_input(self) -> bool:
        """全选后删除当前输入框里的文字"""
        def action() -> None:
            self._post_key(_KEY_A, command=True)
            self._post_key(_KEY_DELETE)
        return self._run_in_foreground(action)
