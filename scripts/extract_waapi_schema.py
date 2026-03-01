"""
提取官方 WAAPI 2024.1 Schema
读取 Wwise 安装目录的 WAAPI JSON 文件，合并为 wwise_mcp/doc/waapi_schema_2024.1.json
"""

import json
import os
from pathlib import Path


SCHEMA_DIR = Path(r"D:\Audiokinetic\Wwise2024.1.8.8898\Authoring\Data\Schemas\WAAPI")
OUTPUT_FILE = Path(__file__).parent.parent / "wwise_mcp" / "doc" / "waapi_schema_2024.1.json"


def extract_props(schema_obj: dict, max_depth: int = 2) -> dict:
    """从 JSON Schema object 提取属性摘要 {name: {type, description, required}}"""
    if not isinstance(schema_obj, dict):
        return {}

    properties = schema_obj.get("properties", {})
    required_list = schema_obj.get("required", [])
    result = {}

    for prop_name, prop_def in properties.items():
        if not isinstance(prop_def, dict):
            continue

        info = {}

        # 类型
        t = prop_def.get("type", "")
        if not t and "$ref" in prop_def:
            t = prop_def["$ref"].split("/")[-1]
        if not t and "anyOf" in prop_def:
            types = [x.get("type", "") for x in prop_def["anyOf"] if isinstance(x, dict)]
            t = " | ".join(filter(None, types))
        info["type"] = t or "any"

        # 描述
        desc = prop_def.get("description", "")
        if desc:
            info["description"] = desc[:200]  # 截断过长描述

        # 枚举值
        enum_vals = prop_def.get("enum", [])
        if enum_vals and len(enum_vals) <= 10:
            info["enum"] = enum_vals

        # 是否必填
        if prop_name in required_list:
            info["required"] = True

        # 嵌套属性（浅层）
        if max_depth > 1 and prop_def.get("type") == "object":
            nested = extract_props(prop_def, max_depth - 1)
            if nested:
                info["properties"] = nested

        result[prop_name] = info

    return result


def process_file(json_path: Path) -> list[dict]:
    """解析单个 WAAPI Schema 文件，返回精简后的条目列表（函数 + topic）"""
    try:
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"  [WARN] 读取失败 {json_path.name}: {e}")
        return []

    results = []

    # 处理 functions（可调用的 API）
    for func in raw.get("functions", []):
        func_id = func.get("id", "")
        if not func_id:
            continue

        entry: dict = {
            "id": func_id,
            "kind": "function",
            "description": func.get("description", ""),
        }

        restrict = func.get("restrict", [])
        if restrict:
            entry["restrict"] = restrict

        args_schema = func.get("argsSchema", {})
        if args_schema:
            args_props = extract_props(args_schema)
            if args_props:
                entry["args"] = args_props

        result_schema = func.get("resultSchema", {})
        if result_schema:
            result_props = extract_props(result_schema)
            if result_props:
                entry["returns"] = result_props

        examples = func.get("examples", [])
        if examples:
            entry["examples"] = [
                {"title": ex.get("title", ""), "description": ex.get("description", "")}
                for ex in examples
                if isinstance(ex, dict)
            ]

        results.append(entry)

    # 处理 topics（可订阅的通知事件）
    for topic in raw.get("topics", []):
        topic_id = topic.get("id", "")
        if not topic_id:
            continue

        entry = {
            "id": topic_id,
            "kind": "topic",
            "description": topic.get("description", ""),
        }

        restrict = topic.get("restrict", [])
        if restrict:
            entry["restrict"] = restrict

        see_also = topic.get("seeAlso", [])
        if see_also:
            entry["seeAlso"] = see_also

        # topic 的返回数据格式（通知内容）
        options_schema = topic.get("optionsSchema", {})
        if options_schema:
            opts_props = extract_props(options_schema)
            if opts_props:
                entry["options"] = opts_props

        results.append(entry)

    return results


def main():
    if not SCHEMA_DIR.exists():
        print(f"[ERROR] Schema 目录不存在: {SCHEMA_DIR}")
        return

    json_files = sorted(SCHEMA_DIR.glob("*.json"))
    print(f"找到 {len(json_files)} 个 JSON 文件")

    entries = []
    func_count = 0
    topic_count = 0

    for f in json_files:
        items = process_file(f)
        for item in items:
            entries.append(item)
            if item.get("kind") == "topic":
                topic_count += 1
            else:
                func_count += 1

    print(f"成功提取: {func_count} 个函数 + {topic_count} 个 topic，共 {len(entries)} 条")

    # 按函数 ID 排序
    entries.sort(key=lambda x: x["id"])

    # 统计各命名空间
    namespaces: dict[str, int] = {}
    for e in entries:
        ns = ".".join(e["id"].split(".")[:3])
        namespaces[ns] = namespaces.get(ns, 0) + 1
    print("\n命名空间统计:")
    for ns, count in sorted(namespaces.items()):
        print(f"  {ns}: {count} 个函数")

    # 写出
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    size_kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"\n已写出: {OUTPUT_FILE}")
    print(f"文件大小: {size_kb} KB，共 {len(entries)} 条（{func_count} 函数 + {topic_count} topic）")


if __name__ == "__main__":
    main()
