#!/usr/bin/env python3
"""Phase 3 v3（feature-semantic 范式）数据层 interface-only 契约生成。

按 data-relations.csv 的语义对象（data_object 列）聚合，为每个语义数据
对象生成一个 interface-only 的 Repository 契约声明（JSON 契约，实现最简、
零 ArkTS 编译面），延续 capability registry 的接口-only 传统。

范式约束（用户修正）：数据契约是语义层（业务数据对象读写集），不规定
物理载体；Android 参考实现（persistence_kind/persistence_location）仅
作记录，鸿蒙侧实现自由选择 Preferences / RelationalStore 等。

data-relations.csv 真实 schema（HOME-FULL-RUN1 权威参照）：
    relation_id,feature_id,data_object,relation,persistence_kind,
    persistence_location,source_ref
其中方向列名为 relation（read/write），物理参考为 persistence_kind +
persistence_location。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _common import atomic_json, read_csv, sha256_file

# 方向合法值（relation 列）；其余值不参与 directions 聚合，计入 stats。
DIRECTIONS = ("read", "write")
# 契约 source_refs 采样上限（防大对象契约膨胀；relation_ids 保真全列）。
MAX_SOURCE_REFS = 8
CONTRACT_SCHEMA_VERSION = 1
CONTRACT_KIND = "data-repository-interface"


def normalize_object_id(data_object: str) -> str:
    """语义对象名 → 文件安全的 object_id（"mmkv:sort_option" → "mmkv_sort_option"）。"""
    lowered = data_object.strip().lower()
    normalized = re.sub(r"[^a-z0-9_]+", "_", lowered).strip("_")
    return normalized or "_unnamed_"


def repository_symbol(object_id: str) -> str:
    """object_id → 确定性 ArkTS 风格 Repository 符号名（仅用于契约声明，不编译）。"""
    parts = [part for part in re.split(r"_+", object_id) if part]
    name = "".join(part.capitalize() for part in parts) or "Unnamed"
    return f"{name}Repository"


def load_data_relations(path: Path) -> list[dict[str, str]]:
    return read_csv(path)


def semantic_objects(
    rows: list[dict[str, str]],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """聚合 data-relations 行 → 每个语义对象一份契约素材 + 统计。

    确定性规则：
    - data_object 为空的行（如 "<Insert>" 泛化 DAO 行）跳过并计数，
      不中断、不发明对象名；
    - directions 取 relation 列聚合（read/write）；未知 relation 值计入
      stats.invalid_relations，不进契约；
    - android 物理持久化（persistence_kind/persistence_location）仅作
      参考记录，(kind, location) 去重排序；
    - feature_id 非空时聚合（真实数据大多数行 feature_id 为空，属正常）。
    """
    objects: dict[str, dict[str, Any]] = {}
    stats = {
        "row_count": len(rows),
        "rows_skipped_empty_object": 0,
        "invalid_relations": 0,
    }
    for row in rows:
        data_object = str(row.get("data_object", "")).strip()
        if not data_object:
            stats["rows_skipped_empty_object"] += 1
            continue
        relation = str(row.get("relation", "")).strip().lower()
        if relation not in DIRECTIONS:
            stats["invalid_relations"] += 1
            continue
        object_id = normalize_object_id(data_object)
        entry = objects.setdefault(
            object_id,
            {
                "object_id": object_id,
                "raw_name": data_object,
                "repository_symbol": repository_symbol(object_id),
                "directions": set(),
                "android_persistence": set(),
                "feature_ids": set(),
                "relation_ids": [],
                "source_refs": [],
            },
        )
        entry["directions"].add(relation)
        kind = str(row.get("persistence_kind", "")).strip()
        location = str(row.get("persistence_location", "")).strip()
        if kind or location:
            entry["android_persistence"].add((kind, location))
        feature_id = str(row.get("feature_id", "")).strip()
        if feature_id:
            entry["feature_ids"].add(feature_id)
        relation_id = str(row.get("relation_id", "")).strip()
        if relation_id:
            entry["relation_ids"].append(relation_id)
        source_ref = str(row.get("source_ref", "")).strip()
        if source_ref and source_ref not in entry["source_refs"]:
            entry["source_refs"].append(source_ref)
    stats["object_count"] = len(objects)
    return objects, stats


def _finalize(entry: dict[str, Any]) -> dict[str, Any]:
    """聚合结构 → 可 JSON 序列化的确定序素材（sets → sorted lists）。"""
    return {
        **entry,
        "directions": sorted(entry["directions"]),
        "android_persistence": [
            {"kind": kind, "location": location}
            for kind, location in sorted(entry["android_persistence"])
        ],
        "feature_ids": sorted(entry["feature_ids"]),
        "relation_ids": sorted(entry["relation_ids"]),
        "source_refs": sorted(entry["source_refs"])[:MAX_SOURCE_REFS],
    }


def contract_document(
    entry: dict[str, Any], generated_at: str, source_sha256: str
) -> dict[str, Any]:
    """语义对象素材 → interface-only 契约文档（JSON 契约，无物理载体约束）。"""
    finalized = _finalize(entry)
    # 批次 3（#86）：required_operations 总是输出——entry 未挂载时（旧调用
    # 路径/单测直构素材）现场按无 BC 佐证派生，保证契约不缺操作集。
    required = finalized.get("required_operations") or derive_required_operations(
        finalized, None
    )
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_kind": CONTRACT_KIND,
        "interface_only": True,
        "paradigm": "feature-semantic",
        "object_id": finalized["object_id"],
        "raw_name": finalized["raw_name"],
        "repository_symbol": finalized["repository_symbol"],
        "semantics": {
            "directions": finalized["directions"],
            "note": (
                "语义层读写集契约：仅声明业务数据对象的读写方向，不规定物理"
                "载体；鸿蒙侧实现自由选择 Preferences/RelationalStore 等。"
            ),
        },
        "required_operations": required["operations"],
        "required_operations_evidence": required["evidence"],
        "android_reference_persistence": finalized["android_persistence"],
        "feature_ids": finalized["feature_ids"],
        "relation_ids": finalized["relation_ids"],
        "source_refs": finalized["source_refs"],
        "source": {"data_relations_sha256": source_sha256},
        "generated_at": generated_at,
    }


def contract_index(
    objects: dict[str, dict[str, Any]],
    contract_files: dict[str, str],
    source: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    """data-contracts/index.json：契约清单（object_id 排序，确定性）。"""
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_kind": CONTRACT_KIND,
        "interface_only": True,
        "paradigm": "feature-semantic",
        "source": source,
        "contracts": [
            {
                "object_id": object_id,
                "repository_symbol": objects[object_id]["repository_symbol"],
                "directions": sorted(objects[object_id]["directions"]),
                "feature_ids": sorted(objects[object_id]["feature_ids"]),
                "required_operations": (
                    objects[object_id].get("required_operations")
                    or derive_required_operations(objects[object_id], None)
                )["operations"],
                "contract_file": contract_files[object_id],
            }
            for object_id in sorted(objects)
        ],
        "generated_at": generated_at,
    }


def write_contracts(
    directory: Path,
    objects: dict[str, dict[str, Any]],
    generated_at: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    """写出 data-contracts/ 目录：<object>.json + index.json（原子写）。

    返回 {"index_file", "contract_files", "object_count"}；directory 由调用
    方保证位于 Phase 3 临时工作区内（随 rename 原子生效）。
    """
    source_sha256 = str(source.get("sha256", ""))
    directory.mkdir(parents=True, exist_ok=True)
    contract_files: dict[str, str] = {}
    for object_id in sorted(objects):
        document = contract_document(objects[object_id], generated_at, source_sha256)
        relative = f"{object_id}.json"
        atomic_json(directory / relative, document)
        contract_files[object_id] = relative
    index = contract_index(objects, contract_files, source, generated_at)
    atomic_json(directory / "index.json", index)
    return {
        "index_file": "index.json",
        "contract_files": contract_files,
        "object_count": len(objects),
    }


# ============================================================================
# required_operations（收敛式重构批次 3 #86）
#
# 目的：每个 data-contract 除读/写方向外，声明该语义对象必须提供的操作集
# （create/update/setCompleted/delete/restore/list/get/set/reset/rename/
# reorder），让 Phase 4 不再从 BC 文本临时推断数据面职责。
#
# 派生规则（确定性、无发明）：
# 1. 静态基表 OPERATIONS_BASE_TABLE：对象名（raw 语义名小写）→ 操作集
#    （来自 P2 行为证据的领域对象启发映射）；
# 2. mmkv: 前缀的键级对象（无基表命中）→ KV 缺省 [get, set]；
# 3. 其余未命中对象按 directions 退化推导（read→get/list、write→set）；
# 4. BC 佐证并集：behavior-contracts.csv 中 persistence_targets /
#    data_state_change / source_refs 提及该对象的行，从其 operation +
#    data_state_change 文本收集安全词表动词，并入操作集并登记 bc_ids。
# P3 仍不写业务逻辑——本段只是 interface-only 契约的操作面声明。
# ============================================================================

# 规范输出序（确定性）：操作集一律按此序输出。
OPERATIONS_CANONICAL_ORDER = (
    "create", "update", "setCompleted", "delete", "restore",
    "list", "get", "set", "reset", "rename", "reorder",
)
# 对象名 → 基线操作集（HOME-FULL-RUN1 行为证据的启发映射；P4 实施仍以
# BC 断言为准，本表只圈定 interface 形状，不写实现）。
OPERATIONS_BASE_TABLE: dict[str, tuple[str, ...]] = {
    "todo_items": ("create", "update", "setCompleted", "delete", "restore", "list"),
    "todo_groups": ("create", "update", "rename", "delete", "reorder", "list"),
    "settings": ("get", "set", "reset"),
    "repeat_rules": ("create", "update", "delete", "list", "get"),
    "sub_todo_items": ("create", "update", "delete", "list"),
}
# BC 文本动词 → 安全词表操作（保守集合：不含 rename/reorder 等需对象
# 上下文消歧的动词——它们只来自静态基表）。
BC_OPERATION_VERBS: tuple[tuple[str, str], ...] = (
    ("创建", "create"), ("新建", "create"), ("插入", "create"), ("添加", "create"),
    ("更新", "update"), ("修改", "update"), ("编辑", "update"),
    ("完成", "setCompleted"), ("勾选", "setCompleted"),
    ("删除", "delete"),
    ("恢复", "restore"), ("撤销", "restore"),
    ("列表", "list"), ("查询", "list"),
    ("获取", "get"), ("读取", "get"),
    ("保存", "set"), ("写入", "set"), ("设置", "set"),
    ("重置", "reset"),
)


def _bc_mentions_object(row: dict[str, str], raw_name: str) -> bool:
    """BC 行是否提及该语义对象（persistence_targets / data_state_change /
    source_refs 任一字段含 raw 语义名，大小写不敏感）。"""
    needle = raw_name.strip().lower()
    if not needle:
        return False
    fields = (
        str(row.get("persistence_targets", "")),
        str(row.get("data_state_change", "")),
        str(row.get("source_refs", "")),
    )
    return any(needle in field.lower() for field in fields)


def derive_required_operations(
    entry: dict[str, Any], behavior_contracts: list[dict[str, str]] | None
) -> dict[str, Any]:
    """语义对象素材 → {"operations": [...], "evidence": {...}}（纯函数）。

    evidence 记录派生来源：base_rule（static-table / mmkv-kv-default /
    directions-fallback）、bc_ids（佐证并集的 BC 引用）、bc_derived_ops
    （仅由 BC 动词并入的操作）。
    """
    raw_name = str(entry.get("raw_name", "")).strip()
    key = raw_name.lower()
    base: list[str] = []
    base_rule = ""
    if key in OPERATIONS_BASE_TABLE:
        base = list(OPERATIONS_BASE_TABLE[key])
        base_rule = "static-table"
    elif key.startswith("mmkv"):
        base = ["get", "set"]
        base_rule = "mmkv-kv-default"
    else:
        directions = set(entry.get("directions") or [])
        if "read" in directions:
            base.append("get")
            base.append("list")
        if "write" in directions:
            base.append("set")
        base_rule = "directions-fallback"

    operations = list(base)
    bc_ids: list[str] = []
    bc_derived: list[str] = []
    for row in behavior_contracts or []:
        if not _bc_mentions_object(row, raw_name):
            continue
        bc_id = str(row.get("bc_id", "")).strip()
        if bc_id and bc_id not in bc_ids:
            bc_ids.append(bc_id)
        text = (
            str(row.get("operation", "")) + " " + str(row.get("data_state_change", ""))
        )
        for verb, operation in BC_OPERATION_VERBS:
            if verb in text and operation not in operations:
                operations.append(operation)
                if operation not in base and operation not in bc_derived:
                    bc_derived.append(operation)
    ordered = [op for op in OPERATIONS_CANONICAL_ORDER if op in operations]
    return {
        "operations": ordered,
        "evidence": {
            "base_rule": base_rule,
            "bc_ids": sorted(bc_ids),
            "bc_derived_ops": sorted(bc_derived),
        },
    }


def attach_required_operations(
    objects: dict[str, dict[str, Any]],
    behavior_contracts: list[dict[str, str]] | None,
) -> dict[str, int]:
    """为全部语义对象挂载 required_operations（原地，确定性）。"""
    for object_id in objects:
        objects[object_id]["required_operations"] = derive_required_operations(
            objects[object_id], behavior_contracts
        )
    return {"attached_object_count": len(objects)}


def capability_seed(
    entry: dict[str, Any], contract_relative: str
) -> dict[str, Any]:
    """语义对象 → capability registry 能力种子（接口-only 传统延续）。"""
    finalized = _finalize(entry)
    return {
        "capability_id": f"CAP-DATA-{finalized['repository_symbol'].upper()}",
        "kind": CONTRACT_KIND,
        "interface_only": True,
        "contract_file": contract_relative,
        "repository_symbol": finalized["repository_symbol"],
        "directions": finalized["directions"],
        "feature_ids": finalized["feature_ids"],
    }


def load_and_build(
    data_relations_path: Path,
    behavior_contracts_path: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """一步式读取 + 聚合（供 init_scaffold v3 与测试复用）。

    behavior_contracts_path（可选）：Phase 2 behavior-contracts.csv 存在时
    读入作为 required_operations 的 BC 佐证并集来源；缺失时不阻塞，
    操作集退化为静态基表 / KV 缺省 / directions 推导。
    """
    rows = load_data_relations(data_relations_path)
    objects, stats = semantic_objects(rows)
    behavior_contracts: list[dict[str, str]] | None = None
    if behavior_contracts_path is not None and Path(behavior_contracts_path).is_file():
        behavior_contracts = read_csv(Path(behavior_contracts_path))
    attached = attach_required_operations(objects, behavior_contracts)
    stats["required_operations_attached"] = attached["attached_object_count"]
    return objects, {
        **stats,
        "path": str(data_relations_path),
        "sha256": sha256_file(data_relations_path),
    }


# ============================================================================
# DebugSemanticProbe 独立探针（收敛式重构批次 2 #85）
#
# 目的：Phase 4 data 断言的数据出口不再信任应用侧自报的 replay-data.json
# （自答可伪造）。改由本钩子在 scaffold 阶段生成常驻探针：
#   - DebugSemanticProbe.ets（本钩子生成，Phase 3 冻结，P4 实施者禁改——
#     Phase 4 工单携带 expected sha256，Gate 4 校验一致性）；
#   - SemanticProbeRegistry.ets（注册表，Phase 4 实施者在自己代码里接线
#     registerProbe(key, provider)——接线行在实施者文件里，不碰探针本体）。
# 探针周期采样全部 data-contract 语义对象（未注册 → null），双通道输出：
#   A) 沙箱文件 <filesDir>/semantic-probe.json（replayer hdc file recv 主通道）
#   B) hilog tag SemanticProbe 的 SNAPSHOT 行（退化通道）
# ============================================================================

PROBE_DIR_RELATIVE = "entry/src/main/ets/probe"
PROBE_RELATIVE_PATH = f"{PROBE_DIR_RELATIVE}/DebugSemanticProbe.ets"
PROBE_REGISTRY_RELATIVE_PATH = f"{PROBE_DIR_RELATIVE}/SemanticProbeRegistry.ets"
PROBE_SNAPSHOT_FILENAME = "semantic-probe.json"
PROBE_HILOG_TAG = "SemanticProbe"
PROBE_INTERVAL_MS = 2000


def _probe_registry_source(object_ids: list[str]) -> str:
    """SemanticProbeRegistry.ets 源码（Phase 4 可改的接线注册表）。

    PROBE_KEYS 为 scaffold 冻结的 key 全集；collectProbeSnapshot() 输出
    全集（未注册对象 → null，replayer data 断言对 null 按 fail-closed
    判 FAIL——未接线=实施缺陷）。
    """
    keys_literal = ", ".join(f"'{key}'" for key in object_ids) or "'__none__'"
    return (
        "// SemanticProbeRegistry - Phase 4 wiring registry (NOT hash-frozen;\n"
        "// implementation agents register real Repository/Preferences/\n"
        "// RelationalStore providers from their own source files).\n"
        "// Generated by init_scaffold (batch 2 #85); keys set is frozen.\n"
        "export type ProbeProvider = () => object | null;\n"
        "\n"
        "interface Entry {\n"
        "  key: string;\n"
        "  provider: ProbeProvider;\n"
        "}\n"
        "\n"
        f"export const PROBE_KEYS: string[] = [{keys_literal}];\n"
        "\n"
        "const entries: Entry[] = [];\n"
        "\n"
        "export function registerProbe(key: string, provider: ProbeProvider): void {\n"
        "  for (let i = 0; i < entries.length; i++) {\n"
        "    if (entries[i].key === key) {\n"
        "      entries[i].provider = provider;\n"
        "      return;\n"
        "    }\n"
        "  }\n"
        "  entries.push({ key: key, provider: provider });\n"
        "}\n"
        "\n"
        "export function collectProbeSnapshot(): Record<string, object | null> {\n"
        "  const out: Record<string, object | null> = {};\n"
        "  for (const key of PROBE_KEYS) {\n"
        "    let hit = false;\n"
        "    for (const entry of entries) {\n"
        "      if (entry.key === key) {\n"
        "        hit = true;\n"
        "        try {\n"
        "          out[key] = entry.provider();\n"
        "        } catch (e) {\n"
        "          out[key] = null;\n"
        "        }\n"
        "        break;\n"
        "      }\n"
        "    }\n"
        "    if (!hit) {\n"
        "      out[key] = null;\n"
        "    }\n"
        "  }\n"
        "  return out;\n"
        "}\n"
    )


def _debug_semantic_probe_source() -> str:
    """DebugSemanticProbe.ets 源码（哈希冻结本体；不含业务，不依赖具体
    data-contract 内容——key 全集在 registry，保持本文件对任意 run 确定
    同一源码，便于跨 run 哈希一致性）。"""
    return (
        "// DebugSemanticProbe - semantic data snapshot probe (batch 2 #85).\n"
        "// HASH-FROZEN after Phase 3: Phase 4 implementers must NOT modify\n"
        "// this file (work order carries the expected sha256; Gate 4 checks).\n"
        "// Wire real providers from your own files via SemanticProbeRegistry\n"
        "// .registerProbe(key, provider) instead.\n"
        "//\n"
        "// Channels: A) sandbox file files/" + PROBE_SNAPSHOT_FILENAME + "\n"
        "//           B) hilog tag '" + PROBE_HILOG_TAG + "' SNAPSHOT lines\n"
        "import fs from '@ohos.file.fs';\n"
        "import hilog from '@ohos.hilog';\n"
        "import { collectProbeSnapshot } from './SemanticProbeRegistry';\n"
        "\n"
        "const TAG = '" + PROBE_HILOG_TAG + "';\n"
        "const INTERVAL_MS = " + str(PROBE_INTERVAL_MS) + ";\n"
        "let timerId: number = -1;\n"
        "\n"
        "function snapshotJson(): string {\n"
        "  const snapshot = collectProbeSnapshot();\n"
        "  return JSON.stringify(snapshot);\n"
        "}\n"
        "\n"
        "export function startSemanticProbe(filesDir: string): void {\n"
        "  if (timerId >= 0) {\n"
        "    return;\n"
        "  }\n"
        "  const target = filesDir + '/" + PROBE_SNAPSHOT_FILENAME + "';\n"
        "  timerId = setInterval(() => {\n"
        "    const json = snapshotJson();\n"
        "    hilog.info(0x0000, TAG, 'SNAPSHOT %{public}s', json);\n"
        "    try {\n"
        "      const exists = fs.accessSync(target);\n"
        "      const file = fs.openSync(\n"
        "        target,\n"
        "        fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE\n"
        "          | (exists ? fs.OpenMode.TRUNC : 0));\n"
        "      fs.writeSync(file.fd, json);\n"
        "      fs.closeSync(file);\n"
        "    } catch (e) {\n"
        "      hilog.error(0x0000, TAG, 'snapshot write failed: %{public}s',\n"
        "        JSON.stringify(e));\n"
        "    }\n"
        "  }, INTERVAL_MS);\n"
        "}\n"
    )


def wire_probe_into_ability(ability_path: Path) -> bool:
    """把探针启动行幂等接线进 EntryAbility.ets（不改动 arkui 模板本体，
    scaffold 生成物层面追加；标记注释防重复）。

    返回 True = 本次写入；False = 已接线（幂等跳过）。
    """
    marker = "startSemanticProbe"
    text = ability_path.read_text(encoding="utf-8")
    if marker in text:
        return False
    import_line = ("import { startSemanticProbe } from "
                   "'../probe/DebugSemanticProbe';\n")
    start_line = ("    // batch-2 #85: frozen semantic probe autostart\n"
                  "    startSemanticProbe(this.context.filesDir);\n")
    if "onCreate(want: Want" not in text:
        raise ValueError(
            f"EntryAbility lacks expected onCreate hook: {ability_path}")
    text = import_line + text
    hook = "onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {"
    index = text.index(hook) + len(hook)
    text = text[:index] + "\n" + start_line + text[index:]
    ability_path.write_text(text, encoding="utf-8")
    return True


def write_semantic_probe(
    project_root: Path,
    objects: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """生成探针两文件 + EntryAbility 接线（init_scaffold 调用钩子）。

    返回 {"probe_relative_path", "probe_sha256", "registry_relative_path",
          "registry_sha256", "probe_keys", "ability_wired"}；probe_sha256
    是 Phase 4 工单/Gate 4 的 expected hash 来源（registry 不冻结）。
    """
    probe_dir = project_root / PROBE_DIR_RELATIVE
    probe_dir.mkdir(parents=True, exist_ok=True)
    object_ids = sorted(objects)
    probe_text = _debug_semantic_probe_source()
    registry_text = _probe_registry_source(object_ids)
    probe_path = project_root / PROBE_RELATIVE_PATH
    registry_path = project_root / PROBE_REGISTRY_RELATIVE_PATH
    probe_path.write_text(probe_text, encoding="utf-8")
    registry_path.write_text(registry_text, encoding="utf-8")
    ability_path = (project_root
                    / "entry/src/main/ets/entryability/EntryAbility.ets")
    if not ability_path.is_file():
        raise ValueError(
            f"EntryAbility not found for probe wiring: {ability_path}")
    wired = wire_probe_into_ability(ability_path)
    return {
        "probe_relative_path": PROBE_RELATIVE_PATH,
        "probe_sha256": sha256_file(probe_path),
        "registry_relative_path": PROBE_REGISTRY_RELATIVE_PATH,
        "registry_sha256": sha256_file(registry_path),
        "probe_keys": object_ids,
        "ability_wired": wired,
    }