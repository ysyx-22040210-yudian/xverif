from __future__ import annotations

import json
from pathlib import Path

from .io import read_text

RULES = """You are initializing kberif.

Rules:
1. Create or update summary cards by writing JSON files directly under .kberif/cards/.
2. Create topic details by writing Markdown files directly under .kberif/details/.
3. Do not invent files, modules, signals, tests, classes, commands, or directory structures.
4. Every concrete claim must include evidence.
5. Evidence path must exist in .kberif/manifest.json.
6. If unsure, use unknown or confidence: low.
7. Only create cards for topics defined in kberif/topics.toml.
8. Do not create topics from another env_kind.
9. Do not output prose as final result.
10. Do not run validation yourself; kberif hooks will validate card/detail files after Write/Edit and before stop.
11. A card summary must stay short and clear; do not expand full analysis into the card.
12. A detail must expand the card with paths, conditions, verification/debug guidance, and evidence.
13. Metadata is fixed by the Topics section: copy id, env_kind, topic, title, card_id, and detail path exactly; never translate, rename, or rephrase a title.
14. This initialization session may write .kberif/cards and .kberif/details as instructed; after initialization, ordinary Claude access to .kberif should go through the kberif skill/CLI instead of direct Read/Edit.
"""


def render_prompt(root: Path, kind_cfg: dict, topics_cfg: dict, manifest: dict) -> str:
    kind = kind_cfg["env_kind"]
    chunks = [
        RULES,
        f"\nCurrent env_kind: {kind}\n",
        "\nGenerated write targets:\n"
        f"- Write one JSON file per topic to .kberif/cards/{kind}.<topic>.json\n"
        f"- Write one Markdown file per topic to .kberif/details/{kind}.<topic>.md\n"
        "- Both filenames must exactly match the card id from kberif/topics.toml.\n"
        "- Do not create temporary generated files under /tmp.\n"
        "\n"
        "Allowed write/edit scope:\n"
        "- .kberif/cards/*.json\n"
        "- .kberif/details/*.md\n"
        "- Never edit kberif/*.toml, RTL, DV, docs, manifest.json, cards.json, kind.json, or lock.json.\n",
        "\nTopic card envelope schema: kberif.topic_card.v1\n"
        "Required card object keys are: schema_version, id, env_kind, topic, title, "
        "summary, confidence, key_items, detail, notes, unknowns, generated_by.\n"
        "The summary must be short and clear, summarizing the conclusion for this topic.\n"
        "Use up to 8 key_items; each key_item requires name, one_line, confidence, and evidence.\n"
        "Each key_item evidence entry must be an object with path, line_start, and line_end integer fields; "
        "do not use `path:line-line` strings in card JSON.\n"
        "Use key `id`, not `card_id`, inside the card JSON.\n",
        "\nExample .kberif/cards file content:\n"
        "{\n"
        "  \"schema_version\": \"kberif.topic_card.v1\",\n"
        f"  \"id\": \"{kind}.project\",\n"
        f"  \"env_kind\": \"{kind}\",\n"
        "  \"topic\": \"project\",\n"
        "  \"title\": \"Project Summary\",\n"
        "  \"summary\": \"Short, clear conclusion for this topic.\",\n"
        "  \"confidence\": \"medium\",\n"
        "  \"key_items\": [{\"name\": \"primary_mechanism\", \"one_line\": \"Concise explanation.\", "
        "\"confidence\": \"medium\", \"evidence\": [{\"path\": \"rtl/example.sv\", "
        "\"line_start\": 1, \"line_end\": 4}]}],\n"
        f"  \"detail\": {{\"available\": true, \"path\": \".kberif/details/{kind}.project.md\", "
        "\"format\": \"markdown\", \"token_estimate\": 0, \"section_count\": 0}},\n"
        "  \"notes\": [],\n"
        "  \"unknowns\": [],\n"
        "  \"generated_by\": {\"tool\": \"claudecode\", \"kberif_version\": \"0.3.0\"}\n"
        "}\n"
        "\n",
        "\nTopic detail schema: kberif.topic_detail.v1\n"
        "Begin each detail with YAML-style metadata keys: schema_version, env_kind, topic, card_id, title, confidence.\n"
        "Each detail must contain the following sections:\n"
        "- `## 结论摘要`: explain the main findings and conclusions in several concise paragraphs.\n"
        "- `## 关键路径`: show relevant data, control, or verification paths between modules, components, or signals.\n"
        "- `## 关键项详解`: expand key mechanisms, trigger/release conditions, and direct effects item by item.\n"
        "- `## 验证与 Debug 提示`: identify testcase, checker, waveform, or debug entrypoints worth examining.\n"
        "- `## 相关 Topic`: list directly related topics that may need follow-up reading.\n"
        "- `## 未确认信息`: list claims without sufficient evidence; do not guess.\n"
        "- `## Evidence`: collect source evidence supporting concrete conclusions.\n"
        "Write evidence entries as `- path:line_start-line_end - supported conclusion`.\n"
        "\nEvidence requires path, line_start, line_end and must reference manifest files.\n",
        "\nTopics:\n",
        json.dumps(topics_cfg, ensure_ascii=False, indent=2),
        "\nManifest:\n",
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "\nUser prompts by topic:\n",
    ]
    for topic, cfg in topics_cfg.get("topics", {}).items():
        prompt_path = root / cfg["prompt"]
        chunks.append(f"\n## {topic} / {cfg['title']}\n")
        chunks.append(read_text(prompt_path))
    chunks.append(
        "\nExecution plan:\n"
        "1. Read the manifest files needed for all required topics in one initialization session.\n"
        "2. Write an overview card and an in-depth detail for every required topic.\n"
        "3. If a hook reports a validation error, fix the named card/detail and write it again.\n"
        "4. Exit after all required card/detail pairs are written. kberif will rebuild cards.json and validate.\n"
    )
    return "\n".join(chunks)
