from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from one_dragon.base.config.config_item import ConfigItem
from one_dragon_qt.utils.config_utils import get_prop_adapter
from one_dragon_qt.widgets.app_setting.app_setting_flyout import AppSettingFlyout
from one_dragon_qt.widgets.setting_card.combo_box_setting_card import (
    ComboBoxSettingCard,
)
from one_dragon_qt.widgets.setting_card.editable_combo_box_setting_card import (
    EditableComboBoxSettingCard,
)
from one_dragon_qt.widgets.setting_card.switch_setting_card import SwitchSettingCard
from zzz_od.application.coffee import coffee_app_const
from zzz_od.application.coffee.coffee_config import CoffeeTransportPoint


class CoffeeSettingFlyout(AppSettingFlyout):
    """咖啡店配置弹出框"""

    def _setup_ui(self, layout: QVBoxLayout) -> None:
        self.transport_point_opt = ComboBoxSettingCard(
            icon='',
            title='传送地点',
            content='选择前往的咖啡店',
            options_enum=CoffeeTransportPoint,
            margins=self.card_margins,
        )
        layout.addWidget(self.transport_point_opt)

        self.coffee_name_opt = EditableComboBoxSettingCard(
            icon='',
            title='点单咖啡',
            content='额外咖啡喝完后点的咖啡 不同咖啡店菜单不同 可直接输入名字',
            options_list=[ConfigItem(name, name) for name in ['汀曼特调', '新艾利都特调', '鲜萃红茶']],
            margins=self.card_margins,
        )
        layout.addWidget(self.coffee_name_opt)

        self.run_charge_plan_afterwards_opt = SwitchSettingCard(
            icon='',
            title='结束后运行体力计划',
            content='咖啡店在体力计划后运行可开启',
            margins=self.card_margins,
        )
        layout.addWidget(self.run_charge_plan_afterwards_opt)

    def init_config(self) -> None:
        config = self.ctx.run_context.get_config(
            app_id=coffee_app_const.APP_ID,
            instance_idx=self.ctx.current_instance_idx,
            group_id=self.group_id,
        )
        self.transport_point_opt.init_with_adapter(get_prop_adapter(config, 'transport_point'))
        self.coffee_name_opt.init_with_adapter(get_prop_adapter(config, 'coffee_name'))
        self.run_charge_plan_afterwards_opt.init_with_adapter(
            get_prop_adapter(config, 'run_charge_plan_afterwards')
        )
