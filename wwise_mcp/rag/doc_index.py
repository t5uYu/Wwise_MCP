"""
Layer 2 — WwiseDocIndex：WAAPI Schema + 知识库索引
预处理为 O(1) 查找的 dict 结构，供 set_property 类型验证使用
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("wwise_mcp.doc_index")

# doc 目录路径
_DOC_DIR = Path(__file__).parent.parent / "doc"


class WwiseDocIndex:
    """
    WAAPI Schema 和知识库的快速查找索引。
    """

    # 内建的常用属性名白名单（Wwise 通用属性）
    COMMON_PROPERTIES = {
        # 音量/音调
        "Volume", "Pitch", "MakeUpGain",
        # 滤波
        "LowPassFilter", "HighPassFilter",
        # 输出路由
        "OutputBus", "OutputBusVolume", "OutputBusMixerGain",
        # 空间定位
        "Positioning.EnablePositioning", "Positioning.SpeakerPanning",
        "Positioning.3D.AttenuationID",
        # 实例控制
        "MaxSoundInstances", "MaxSoundInstancesBehavior",
        "VirtualVoiceBehavior",
        # 随机化
        "Volume.Min", "Volume.Max", "Pitch.Min", "Pitch.Max",
        # Action 特有
        "ActionType", "Target", "Delay", "TransitionTime",
        # SoundBank
        "IncludeInSoundBank",
        # 游戏辅助 Send
        "UseGameDefinedAuxSends", "UserAuxSendVolume0",
        # Blend Container（2024.1 新增）
        "CrossfadeParameter", "BlendTrackName",
        # 通用
        "Notes", "Color",
    }

    # 常用 WAAPI URI 快速索引（内建，无需加载 JSON Schema 文件）
    WAAPI_FUNCTIONS: dict[str, dict] = {
        "ak.wwise.core.getInfo": {
            "description": "获取 Wwise 版本和项目基础信息",
            "required_args": [],
            "return_fields": ["version", "projectName", "projectPath"],
            "since": "2017.1",
        },
        "ak.wwise.core.object.get": {
            "description": "查询 Wwise 对象，支持 from/where/transform/return 灵活组合",
            "required_args": ["from"],
            "optional_args": ["where", "transform", "options"],
            "return_fields": ["@name", "@type", "@path", "@id", "@childrenCount"],
            "since": "2017.1",
        },
        "ak.wwise.core.object.create": {
            "description": "在指定父对象下创建新对象",
            "required_args": ["name", "type", "parent", "onNameConflict"],
            "optional_args": ["children", "notes"],
            "return_fields": ["id", "name", "path"],
            "since": "2017.1",
        },
        "ak.wwise.core.object.delete": {
            "description": "删除 Wwise 对象",
            "required_args": ["object"],
            "since": "2017.1",
        },
        "ak.wwise.core.object.move": {
            "description": "将对象移动到新父节点",
            "required_args": ["object", "parent"],
            "optional_args": ["onNameConflict"],
            "since": "2017.1",
        },
        "ak.wwise.core.object.setProperty": {
            "description": "设置对象属性值（数值/布尔型属性）",
            "required_args": ["object", "property", "value"],
            "optional_args": ["platform"],
            "since": "2017.1",
        },
        "ak.wwise.core.object.setReference": {
            "description": "设置对象的引用类属性（OutputBus/Target 等）",
            "required_args": ["object", "reference", "value"],
            "optional_args": ["platform"],
            "note": "2024.1 中 platform 字段默认值有调整，明确传入平台名以避免歧义",
            "since": "2017.1",
        },
        "ak.wwise.core.object.getPropertyAndReferenceNames": {
            "description": "获取对象支持的所有属性和引用名称列表",
            "required_args": ["object"],
            "since": "2019.1",
        },
        "ak.wwise.core.soundbank.generate": {
            "description": "生成 SoundBank（2024.1 Auto-Defined 模式下通常不需要手动调用）",
            "required_args": [],
            "optional_args": ["soundbanks", "platforms", "languages"],
            "note": "2024.1 Auto-Defined SoundBank 会自动管理，只在用户明确要求打包时调用",
            "since": "2017.1",
        },
        "ak.wwise.core.soundbank.getInclusions": {
            "description": "获取 SoundBank 的包含项",
            "required_args": ["soundbank"],
            "since": "2017.1",
        },
        "ak.wwise.ui.getSelectedObjects": {
            "description": "获取 Wwise 编辑器中当前选中的对象",
            "required_args": [],
            "since": "2018.1",
        },
        # 2024.1 新增：Blend Container 系列
        "ak.wwise.core.object.addChild": {
            "description": "向 Blend Container 添加子轨道（2024.1 新增）",
            "required_args": ["object", "type"],
            "since": "2024.1",
        },
    }

    def __init__(self):
        self._schema: dict = {}
        self._knowledge: list[str] = []
        self._loaded = False

    def load(self) -> None:
        """加载 WAAPI Schema JSON 和知识库文件（懒加载）"""
        if self._loaded:
            return

        # 尝试加载官方 WAAPI Schema
        schema_path = _DOC_DIR / "waapi_schema_2024.1.json"
        if schema_path.exists():
            try:
                with open(schema_path, encoding="utf-8") as f:
                    raw_schema = json.load(f)
                # 将 schema 列表转为 {uri: info} dict
                if isinstance(raw_schema, list):
                    for item in raw_schema:
                        uri = item.get("uri") or item.get("id")
                        if uri:
                            self._schema[uri] = item
                elif isinstance(raw_schema, dict):
                    self._schema = raw_schema
                logger.info("已加载 WAAPI Schema：%d 个函数", len(self._schema))
            except Exception as e:
                logger.warning("加载 WAAPI Schema 失败（将使用内建索引）：%s", e)
        else:
            logger.info("未找到 WAAPI Schema 文件，使用内建索引")

        # 加载知识库
        kb_path = _DOC_DIR / "knowledge_base.txt"
        if kb_path.exists():
            try:
                with open(kb_path, encoding="utf-8") as f:
                    self._knowledge = [
                        line.strip() for line in f if line.strip() and not line.startswith("#")
                    ]
                logger.info("已加载知识库：%d 条", len(self._knowledge))
            except Exception as e:
                logger.warning("加载知识库失败：%s", e)

        self._loaded = True

    def lookup_function(self, uri: str) -> Optional[dict]:
        """查找 WAAPI 函数信息，优先内建，次用 Schema 文件"""
        self.load()
        # 优先内建
        if uri in self.WAAPI_FUNCTIONS:
            return self.WAAPI_FUNCTIONS[uri]
        # 次用 schema 文件
        return self._schema.get(uri)

    def is_valid_property(self, prop_name: str) -> bool:
        """检查属性名是否合法（在常用属性白名单或 Schema 中存在）"""
        if prop_name in self.COMMON_PROPERTIES:
            return True
        # 模糊匹配（允许 'Volume.Min' 等派生属性）
        for known in self.COMMON_PROPERTIES:
            if prop_name.startswith(known.split(".")[0]):
                return True
        return False

    def get_similar_properties(self, prop_name: str, limit: int = 5) -> list[str]:
        """返回与 prop_name 相似的合法属性名（供错误提示）"""
        prop_lower = prop_name.lower()
        matches = [
            p for p in self.COMMON_PROPERTIES
            if prop_lower in p.lower() or p.lower() in prop_lower
        ]
        return matches[:limit]

    def search_knowledge(self, keyword: str, limit: int = 5) -> list[str]:
        """在知识库中搜索关键词，返回相关条目"""
        self.load()
        keyword_lower = keyword.lower()
        results = [
            line for line in self._knowledge
            if keyword_lower in line.lower()
        ]
        return results[:limit]


# 全局单例
doc_index = WwiseDocIndex()
