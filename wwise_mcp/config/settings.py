"""
WwiseMCP Server 配置
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class WwiseSettings:
    # WAAPI 连接参数
    host: str = "127.0.0.1"
    port: int = 8080
    timeout: float = 10.0          # 单次请求超时（秒）
    reconnect_interval: float = 3.0 # 断线重连间隔（秒）
    max_reconnect: int = 5          # 最大重连次数

    # execute_waapi 黑名单：禁止 Agent 直接调用的危险操作
    blacklisted_uris: List[str] = field(default_factory=lambda: [
        "ak.wwise.core.project.open",
        "ak.wwise.core.project.close",
        "ak.wwise.core.project.save",
        "ak.wwise.ui.project.open",
        "ak.wwise.core.undo.beginGroup",   # 不阻止单个 undo，但禁止批量 group 破坏历史
        "ak.wwise.core.remote.connect",
        "ak.wwise.core.remote.disconnect",
    ])

    @property
    def waapi_url(self) -> str:
        return f"ws://{self.host}:{self.port}/waapi"


# 全局单例配置，可在 server.py 启动时通过环境变量覆盖
settings = WwiseSettings()
