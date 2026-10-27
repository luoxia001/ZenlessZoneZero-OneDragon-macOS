from pathlib import Path

import yaml

from one_dragon.base.screen.screen_area import ScreenArea
from one_dragon.base.screen.screen_info import ScreenInfo
from one_dragon.utils import os_utils, yaml_utils
from one_dragon.utils.log_utils import log


class ScreenRouteNode:

    def __init__(self, from_screen: str, from_area: str, to_screen: str):
        """
        记录一个画面跳转的节点
        :param from_screen: 从某个画面出发
        :param from_area: 点击某个区域
        :param to_screen: 可以前往某个目标画面
        """
        self.from_screen: str = from_screen
        self.from_area: str = from_area
        self.to_screen: str = to_screen


class ScreenRoute:

    def __init__(self, from_screen: str, to_screen: str):
        """
        记录两个画面质检跳转的路径
        :param from_screen:
        :param to_screen:
        """
        self.from_screen: str = from_screen
        self.to_screen: str = to_screen
        self.node_list: list[ScreenRouteNode] = []

    @property
    def can_go(self) -> bool:
        """
        :return: 可到达
        """
        return self.node_list is not None and len(self.node_list) > 0


class ScreenContext:

    def __init__(self):
        self.screen_info_list: list[ScreenInfo] = []
        self.screen_info_map: dict[str, ScreenInfo] = {}
        self._screen_area_map: dict[str, ScreenArea] = {}
        self._id_2_screen: dict[str, ScreenInfo] = {}
        self._extra_screen_ids: set[str] = set()
        self._extra_screen_file_path_map: dict[str, Path] = {}
        self.screen_route_map: dict[str, dict[str, ScreenRoute]] = {}

        # 画面变体 例如 'mobile' 表示移动端
        # 设置后会在基础画面上叠加 assets/game_data/{变体}/screen_info/ 里的配置
        self.screen_variant: str | None = None
        self._variant_screen_ids: set[str] = set()  # 被变体修改或新增的画面ID
        self._variant_base_data: dict[str, dict | None] = {}  # 画面ID -> 叠加变体前的基础配置 新增画面为 None

        self.last_screen_name: str | None = None  # 上一个画面名字
        self.current_screen_name: str | None = None  # 当前的画面名字

        # 屏幕作用域管理
        self._global_screen_names: set[str] = set()
        self._local_screen_names: set[str] = set()
        self._scoped: bool = False

    @property
    def yml_file_dir(self) -> Path:
        return Path(os_utils.get_path_under_work_dir('assets', 'game_data', 'screen_info'))

    @property
    def merge_yml_file_path(self) -> Path:
        return self.yml_file_dir / '_od_merged.yml'

    def get_yml_file_path(self, screen_id: str) -> Path:
        return self.yml_file_dir / f'{screen_id}.yml'

    @property
    def variant_yml_file_dir(self) -> Path | None:
        if not self.screen_variant:
            return None
        return Path(os_utils.get_path_under_work_dir('assets', 'game_data', self.screen_variant, 'screen_info'))

    def set_screen_variant(self, variant: str | None) -> bool:
        """
        设置画面变体 设置后需要调用 reload() 才会生效

        Args:
            variant: 变体名称 例如 'mobile' 为空时只使用基础画面

        Returns:
            变体是否发生了变化
        """
        variant = variant or None
        if variant == self.screen_variant:
            return False
        self.screen_variant = variant
        return True

    def reload(self, from_memory: bool = False, from_separated_files: bool = False) -> None:
        """
        重新加载配置文件

        Args:
            from_memory: 是否从内存中加载 管理画面修改的是 self._id_2_screen 修改后从这里更新其它内存值
            from_separated_files: 是否从单独文件加载
        """
        self.screen_info_list.clear()
        self.screen_info_map.clear()
        self._screen_area_map.clear()
        if not from_memory:
            self._extra_screen_ids.clear()
            self._extra_screen_file_path_map.clear()

        if from_memory:
            for screen_info in self._id_2_screen.values():
                self.screen_info_list.append(screen_info)
                self.screen_info_map[screen_info.screen_name] = screen_info

                for screen_area in screen_info.area_list:
                    self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area
        elif from_separated_files:
            self._id_2_screen.clear()
            for file_path in self.yml_file_dir.iterdir():
                if file_path.suffix != '.yml':
                    continue
                if file_path.name == '_od_merged.yml':
                    continue
                with file_path.open(encoding='utf-8') as file:
                    log.debug(f"加载yaml: {file_path}")
                    data = yaml_utils.safe_load(file)
                if not isinstance(data, dict):
                    log.warning(f"画面配置格式错误，已跳过: {file_path}")
                    continue

                screen_info = ScreenInfo(data)
                if screen_info.screen_name in self.screen_info_map:
                    log.warning(f"画面名称冲突，已跳过: {screen_info.screen_name}")
                    continue
                if screen_info.screen_id in self._id_2_screen:
                    log.warning(f"画面ID冲突，已跳过: {screen_info.screen_id}")
                    continue

                self.screen_info_list.append(screen_info)
                self.screen_info_map[screen_info.screen_name] = screen_info
                self._id_2_screen[screen_info.screen_id] = screen_info

                for screen_area in screen_info.area_list:
                    self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area
        else:
            self._id_2_screen.clear()
            file_path = self.merge_yml_file_path
            if file_path.exists():
                with file_path.open(encoding='utf-8') as file:
                    log.debug(f"加载yaml: {file_path}")
                    yaml_data = yaml_utils.safe_load(file)
            else:
                log.info(f"合并画面配置文件不存在，按空配置加载: {file_path}")
                yaml_data = []
            if not isinstance(yaml_data, list):
                if yaml_data is not None:
                    log.warning(f"合并画面配置格式错误，已忽略: {file_path}")
                yaml_data = []
            for data in yaml_data:
                if not isinstance(data, dict):
                    log.warning(f"合并画面配置中存在非字典条目，已跳过: {file_path}")
                    continue
                screen_info = ScreenInfo(data)
                if screen_info.screen_name in self.screen_info_map:
                    log.warning(f"画面名称冲突，已跳过: {screen_info.screen_name}")
                    continue
                if screen_info.screen_id in self._id_2_screen:
                    log.warning(f"画面ID冲突，已跳过: {screen_info.screen_id}")
                    continue

                self.screen_info_list.append(screen_info)
                self.screen_info_map[screen_info.screen_name] = screen_info
                self._id_2_screen[screen_info.screen_id] = screen_info

                for screen_area in screen_info.area_list:
                    self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area

        if not from_memory:
            self._apply_screen_variant()

        self.init_screen_route()

        # 自动计算全局 screen：没有 app_id 的 screen 为全局
        self._global_screen_names = {
            s.screen_name for s in self.screen_info_list if not s.app_id
        }

    def _apply_screen_variant(self) -> None:
        """
        在已加载的基础画面上叠加变体画面

        合并规则（按画面ID对应）：
        - 画面的其它字段：变体里写了就覆盖
        - area_list：按 area_name 对应 变体里写了的字段覆盖基础区域；基础里没有的区域会新增；
          区域写 `remove: true` 表示在变体里删除这个区域
        - 基础里没有的画面ID：作为变体专属的新画面加入

        合并画面之前 先按变体目录上一级的 template_replace.yml 批量替换模板 见 _apply_template_replace
        """
        self._variant_screen_ids.clear()
        self._variant_base_data.clear()
        variant_dir = self.variant_yml_file_dir
        if variant_dir is None:
            return

        self._apply_template_replace(variant_dir.parent / 'template_replace.yml')
        if not variant_dir.is_dir():
            self._rebuild_screen_index()
            return

        for file_path in sorted(variant_dir.iterdir()):
            if file_path.suffix != '.yml':
                continue
            with file_path.open(encoding='utf-8') as file:
                log.debug(f"加载变体画面: {file_path}")
                data = yaml_utils.safe_load(file)
            if not isinstance(data, dict) or not data.get('screen_id'):
                log.warning(f"变体画面配置格式错误，已跳过: {file_path}")
                continue

            screen_id = data['screen_id']
            base_screen = self._id_2_screen.get(screen_id)
            base_data = None if base_screen is None else base_screen.to_dict()
            merged = ScreenContext.merge_screen_data(base_data, data)
            self._id_2_screen[screen_id] = ScreenInfo(merged)
            self._variant_screen_ids.add(screen_id)
            # 已被模板替换改过的画面 保留最初的基础配置
            self._variant_base_data.setdefault(screen_id, base_data)

        self._rebuild_screen_index()

    def _apply_template_replace(self, file_path: Path) -> None:
        """
        按规则批量替换所有画面里使用某个模板的区域 用于变体里大量画面共用的按钮（如左上角返回）

        文件格式：列表 每项包含
        - template: 原模板 格式为 `template_sub_dir/template_id`
        - replace_template: 替换后的模板 格式同上
        - pc_rect: 可选 替换后的区域范围

        Args:
            file_path: 规则文件路径 不存在时什么也不做
        """
        if not file_path.exists():
            return
        with file_path.open(encoding='utf-8') as file:
            rule_list = yaml_utils.safe_load(file) or []

        rule_map: dict[str, dict] = {}
        for rule in rule_list:
            if isinstance(rule, dict) and rule.get('template') and rule.get('replace_template'):
                rule_map[rule['template']] = rule

        for screen_id, screen_info in list(self._id_2_screen.items()):
            data = screen_info.to_dict()
            changed = False
            for area in data.get('area_list', []):
                rule = rule_map.get(f"{area.get('template_sub_dir', '')}/{area.get('template_id', '')}")
                if rule is None:
                    continue
                area['template_sub_dir'], area['template_id'] = rule['replace_template'].split('/', 1)
                if rule.get('pc_rect'):
                    area['pc_rect'] = list(rule['pc_rect'])
                changed = True
            if changed:
                self._variant_base_data[screen_id] = screen_info.to_dict()
                self._variant_screen_ids.add(screen_id)
                self._id_2_screen[screen_id] = ScreenInfo(data)

    def _rebuild_screen_index(self) -> None:
        """变体处理后 按 _id_2_screen 重建画面和区域索引 保持原有画面顺序"""
        if not self._variant_screen_ids:
            return

        self.screen_info_list.clear()
        self.screen_info_map.clear()
        self._screen_area_map.clear()
        for screen_info in self._id_2_screen.values():
            if screen_info.screen_name in self.screen_info_map:
                log.warning(f"变体画面名称冲突，已跳过: {screen_info.screen_name}")
                continue
            self.screen_info_list.append(screen_info)
            self.screen_info_map[screen_info.screen_name] = screen_info
            for screen_area in screen_info.area_list:
                self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area
        log.info(f"已叠加 {self.screen_variant} 画面变体 共 {len(self._variant_screen_ids)} 个画面")

    @staticmethod
    def merge_screen_data(base_data: dict | None, variant_data: dict) -> dict:
        """
        合并基础画面和变体画面的配置 规则见 _apply_screen_variant

        Args:
            base_data: 基础画面配置 没有时为 None
            variant_data: 变体画面配置

        Returns:
            合并后的画面配置
        """
        merged = dict(base_data) if base_data is not None else {}
        for key, value in variant_data.items():
            if key != 'area_list':
                merged[key] = value

        area_list: list[dict] = [dict(area) for area in merged.get('area_list', [])]
        area_idx = {area.get('area_name'): idx for idx, area in enumerate(area_list)}
        removed: set[str] = set()
        for variant_area in variant_data.get('area_list', []) or []:
            area_name = variant_area.get('area_name')
            if variant_area.get('remove', False):
                removed.add(area_name)
                continue
            if area_name in area_idx:
                area_list[area_idx[area_name]].update(variant_area)
            else:
                area_idx[area_name] = len(area_list)
                area_list.append(dict(variant_area))
        merged['area_list'] = [area for area in area_list if area.get('area_name') not in removed]
        return merged

    def load_extra_screen_dir(self, dir_path: str, default_app_id: str = '') -> None:
        """从额外目录加载 screen YAML 并注册（用于插件 screen 注入）

        加载后会重新计算路由和全局 screen 集合。

        Args:
            dir_path: 包含 screen YAML 文件的目录路径
            default_app_id: 如果 YAML 中未设置 app_id，使用此默认值
        """
        screen_dir = Path(dir_path)
        if not screen_dir.is_dir():
            return

        added = False
        for file_path in screen_dir.iterdir():
            if file_path.suffix != '.yml':
                continue
            with file_path.open(encoding='utf-8') as file:
                log.debug(f"加载插件画面: {file_path}")
                data = yaml_utils.safe_load(file)
            if not isinstance(data, dict):
                log.warning(f"插件画面配置格式错误，已跳过: {file_path}")
                continue

            if default_app_id and not data.get('app_id'):
                data['app_id'] = default_app_id

            screen_info = ScreenInfo(data)
            if screen_info.screen_name in self.screen_info_map:
                log.warning(f"插件画面名称冲突，已跳过: {screen_info.screen_name}")
                continue
            if screen_info.screen_id in self._id_2_screen:
                log.warning(f"插件画面ID冲突，已跳过: {screen_info.screen_id}")
                continue

            self.screen_info_list.append(screen_info)
            self.screen_info_map[screen_info.screen_name] = screen_info
            self._id_2_screen[screen_info.screen_id] = screen_info
            self._extra_screen_ids.add(screen_info.screen_id)
            self._extra_screen_file_path_map[screen_info.screen_id] = file_path

            for screen_area in screen_info.area_list:
                self._screen_area_map[f'{screen_info.screen_name}.{screen_area.area_name}'] = screen_area
            added = True

        if added:
            self.init_screen_route()
            self._global_screen_names = {
                s.screen_name for s in self.screen_info_list if not s.app_id
            }

    def get_screen(self, screen_name: str, copy: bool = False) -> ScreenInfo:
        """
        获取某个画面

        Args:
            screen_name: 画面名称
            copy: 是否复制 用于管理界面临时修改使用

        Returns:
            ScreenInfo 画面信息
        """
        key = screen_name
        screen = self.screen_info_map.get(key, None)
        if screen is None:
            raise Exception(f"未找到画面: {screen_name}")
        if copy:
            return ScreenInfo(screen.to_dict())
        else:
            return screen

    def get_area(self, screen_name: str, area_name: str) -> ScreenArea:
        """
        获取某个区域的信息
        :return:
        """
        key = f'{screen_name}.{area_name}'
        return self._screen_area_map.get(key, None)

    def save_screen(self, screen_info: ScreenInfo) -> None:
        """
        保存画面

        Args:
            screen_info: 画面信息
        """
        if screen_info.old_screen_id in self._extra_screen_file_path_map:
            self._save_extra_screen(screen_info)
            return

        if screen_info.old_screen_id and screen_info.old_screen_id != screen_info.screen_id:
            self.delete_screen(screen_info.old_screen_id, save=False)
        self._id_2_screen[screen_info.screen_id] = screen_info
        self.save(screen_id=screen_info.screen_id)
        screen_info.old_screen_id = screen_info.screen_id

    def delete_screen(self, screen_id: str, save: bool = True) -> None:
        """
        删除一个画面
        Args:
            screen_id: 画面ID
            save: 是否触发保存
        """
        extra_file_path = self._extra_screen_file_path_map.get(screen_id)
        if screen_id in self._id_2_screen:
            del self._id_2_screen[screen_id]
            self._extra_screen_ids.discard(screen_id)
            self._extra_screen_file_path_map.pop(screen_id, None)

            if extra_file_path is not None:
                if extra_file_path.exists():
                    extra_file_path.unlink()
            else:
                file_path = self.get_yml_file_path(screen_id)
                if file_path.exists():
                    file_path.unlink()

        if save and extra_file_path is None:
            self.save(screen_id=screen_id)
        else:
            self.reload(from_memory=True)

    def _save_extra_screen(self, screen_info: ScreenInfo) -> None:
        """保存插件 screen 到原插件目录的独立 YAML。"""
        old_screen_id = screen_info.old_screen_id
        old_file_path = self._extra_screen_file_path_map[old_screen_id]
        file_path = old_file_path

        if old_screen_id != screen_info.screen_id:
            self._id_2_screen.pop(old_screen_id, None)
            self._extra_screen_ids.discard(old_screen_id)
            self._extra_screen_file_path_map.pop(old_screen_id, None)
            if old_file_path.exists():
                old_file_path.unlink()
            file_path = old_file_path.with_name(f'{screen_info.screen_id}.yml')

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open('w', encoding='utf-8') as file:
            yaml.safe_dump(screen_info.to_dict(), file, allow_unicode=True, default_flow_style=False, sort_keys=False)

        screen_info.old_screen_id = screen_info.screen_id
        self._id_2_screen[screen_info.screen_id] = screen_info
        self._extra_screen_ids.add(screen_info.screen_id)
        self._extra_screen_file_path_map[screen_info.screen_id] = file_path
        self.reload(from_memory=True)

    def save(self, screen_id: str | None = None, reload_after_save: bool = True) -> None:
        """
        保存到文件

        Args:
            screen_id: 画面ID
            reload_after_save: 保存后是否重新加载
        """
        all_data = []

        # 保存到单个文件
        target_screen_id = screen_id
        for current_screen_id, screen_info in self._id_2_screen.items():
            if current_screen_id in self._extra_screen_ids:
                continue

            data = screen_info.to_dict()
            if current_screen_id in self._variant_screen_ids:
                # 变体画面不写进基础配置 合并文件里保留原来的基础配置
                base_data = self._variant_base_data.get(current_screen_id)
                if base_data is not None:
                    all_data.append(base_data)
                if target_screen_id == current_screen_id:
                    variant_dir = self.variant_yml_file_dir
                    variant_dir.mkdir(parents=True, exist_ok=True)
                    with (variant_dir / f'{current_screen_id}.yml').open('w', encoding='utf-8') as file:
                        yaml.safe_dump(data, file, allow_unicode=True, default_flow_style=False, sort_keys=False)
                continue

            all_data.append(data)

            if target_screen_id is not None and target_screen_id == screen_info.screen_id:
                with self.get_yml_file_path(target_screen_id).open('w', encoding='utf-8') as file:
                    yaml.safe_dump(data, file, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # 保存到合并文件
        with self.merge_yml_file_path.open('w', encoding='utf-8') as file:
            yaml.safe_dump(all_data, file, allow_unicode=True, default_flow_style=False, sort_keys=False)

        if reload_after_save:
            self.reload(from_memory=True)

    def init_screen_route(self) -> None:
        """
        初始化画面间的跳转路径
        :return:
        """
        self.screen_route_map.clear()

        # 先对任意两个画面之间做初始化
        for screen_1 in self.screen_info_list:
            self.screen_route_map[screen_1.screen_name] = {}
            for screen_2 in self.screen_info_list:
                self.screen_route_map[screen_1.screen_name][screen_2.screen_name] = ScreenRoute(
                    from_screen=screen_1.screen_name,
                    to_screen=screen_2.screen_name
                )

        # 根据画面的goto_list来初始化边
        for screen_info in self.screen_info_list:
            for area in screen_info.area_list:
                if area.goto_list is None or len(area.goto_list) == 0:
                    continue
                from_screen_route = self.screen_route_map[screen_info.screen_name]
                if from_screen_route is None:
                    log.error('画面路径没有初始化 %s', screen_info.screen_name)
                    continue
                for goto_screen_name in area.goto_list:
                    if goto_screen_name not in from_screen_route:
                        log.error('画面路径 %s -> %s 无法找到目标画面', screen_info.screen_name, goto_screen_name)
                        continue
                    from_screen_route[goto_screen_name].node_list.append(
                        ScreenRouteNode(
                            from_screen=screen_info.screen_name,
                            from_area=area.area_name,
                            to_screen=goto_screen_name
                        )
                    )

        # Floyd算出任意两个画面之间的路径
        screen_len = len(self.screen_info_list)
        for k in range(screen_len):
            screen_k = self.screen_info_list[k]
            for i in range(screen_len):
                if i == k:
                    continue
                screen_i = self.screen_info_list[i]

                route_ik: ScreenRoute = self.screen_route_map[screen_i.screen_name][screen_k.screen_name]
                if not route_ik.can_go:  # 无法从 i 到 k
                    continue

                for j in range(screen_len):
                    if k == j or i == j:
                        continue
                    screen_j = self.screen_info_list[j]

                    route_kj: ScreenRoute = self.screen_route_map[screen_k.screen_name][screen_j.screen_name]
                    if not route_kj.can_go:  # 无法从 k 到 j
                        continue

                    route_ij: ScreenRoute = self.screen_route_map[screen_i.screen_name][screen_j.screen_name]

                    if (not route_ij.can_go  # 当前无法从 i 到 j
                        or len(route_ik.node_list) + len(route_kj.node_list) < len(route_ij.node_list)  # 新的更短
                    ):
                        route_ij.node_list = []
                        for node_ik in route_ik.node_list:
                            route_ij.node_list.append(node_ik)
                        for node_kj in route_kj.node_list:
                            route_ij.node_list.append(node_kj)

    def get_screen_route(self, from_screen: str, to_screen: str) -> ScreenRoute | None:
        """
        获取两个画面之间的路径
        :param from_screen:
        :param to_screen:
        :return:
        """
        from_route = self.screen_route_map.get(from_screen, None)
        if from_route is None:
            return None
        return from_route.get(to_screen, None)

    def update_current_screen_name(self, screen_name: str) -> None:
        """
        更新当前的画面名字
        """
        self.last_screen_name = self.current_screen_name
        self.current_screen_name = screen_name

    # ---- Screen Scope 管理 ----
    # 通过 ScreenInfo.app_id 自动区分全局/局部 screen：
    #   - app_id 为空 → 全局 screen，始终参与匹配
    #   - app_id 非空 → 局部 screen，仅在对应应用 scope 内参与匹配
    # reload() 后自动计算全局集合，Application 启动/停止时自动 enter/exit scope

    def enter_scope(self, app_id: str) -> None:
        """进入应用 scope，活跃范围 = 全局 screen + 该 app_id 的局部 screen

        仅当 YAML 中存在 app_id 匹配的 screen 时才真正启用 scope，否则保持全量匹配。

        Args:
            app_id: 当前应用的唯一标识符（与 ScreenInfo.app_id 对应）
        """
        self.exit_scope()

        if not self._global_screen_names:
            return  # 所有 screen 都没有 app_id，不启用 scope

        local_names = {s.screen_name for s in self.screen_info_list if s.app_id == app_id}
        if not local_names:
            return  # 该应用没有专属 screen，不启用 scope

        self._local_screen_names = local_names
        self._scoped = True

    def exit_scope(self) -> None:
        """退出应用 scope，恢复全量 screen 匹配"""
        self._local_screen_names.clear()
        self._scoped = False

    @property
    def active_screen_names(self) -> set[str] | None:
        """当前活跃的 screen 名称集合。None 表示全部活跃（未启用 scope）。"""
        if not self._scoped:
            return None
        return self._global_screen_names | self._local_screen_names

    @property
    def active_screen_info_list(self) -> list[ScreenInfo]:
        """当前活跃的 ScreenInfo 列表"""
        names = self.active_screen_names
        if names is None:
            return self.screen_info_list
        return [s for s in self.screen_info_list if s.screen_name in names]

    def is_screen_active(self, screen_name: str) -> bool:
        """判断某个 screen 是否在当前活跃范围内"""
        names = self.active_screen_names
        if names is None:
            return True
        return screen_name in names
