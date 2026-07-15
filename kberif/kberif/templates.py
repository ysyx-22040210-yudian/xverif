from __future__ import annotations

from copy import deepcopy
from pathlib import Path

KINDS = {
    "bt": "Block Test",
    "it": "IP Test",
    "st": "Subsystem Test",
    "soc": "SoC Test",
}

BT_TOPICS = [
    ("project", "Project Summary", "project.md", True),
    ("workflow", "Build and Run Workflow", "workflow.md", True),
    ("design_overview", "Block Design Overview", "design_overview.md", True),
    ("interfaces", "Block Interfaces", "interfaces.md", True),
    ("backpressure", "Backpressure Points", "backpressure.md", True),
    ("fifos", "FIFO / Queue / Storage Locations", "fifos.md", True),
    ("scheduling", "Scheduling Points", "scheduling.md", True),
    ("ordering", "Ordering Points", "ordering.md", True),
    ("credit", "Credit Mechanism", "credit.md", True),
    ("risks", "Overrun and Design Risks", "risks.md", True),
    ("test_env", "Block Test Environment", "test_env.md", True),
    ("test_creation", "How to Create Block Tests", "test_creation.md", True),
    ("sequence", "Block Sequence / Stimulus Structure", "sequence.md", True),
    ("checker", "Checker and Assertion Structure", "checker.md", True),
    ("rm", "Reference Model", "rm.md", False),
    ("debug", "Debug Entrypoints", "debug.md", True),
]

OTHER_TOPICS = {
    "it": [
        ("project", "Project Summary", "project.md", True),
        ("workflow", "Build, Run, and Regression Workflow", "workflow.md", True),
        ("env_overview", "IP Verification Environment Overview", "env_overview.md", True),
        ("test_creation", "How to Create IP Testcases", "test_creation.md", True),
        ("sequence", "Sequence and Virtual Sequence Structure", "sequence.md", True),
        ("item", "Sequence Item Structure", "item.md", True),
        ("agent", "Agent Structure", "agent.md", True),
        ("monitor", "Monitor Structure", "monitor.md", True),
        ("driver", "Driver Structure", "driver.md", True),
        ("rm", "Reference Model Structure", "rm.md", True),
        ("scoreboard", "Scoreboard Structure", "scoreboard.md", True),
        ("coverage", "Coverage Structure", "coverage.md", True),
        ("debug", "Debug Entrypoints", "debug.md", True),
    ],
    "st": [
        ("project", "Project Summary", "project.md", True),
        ("workflow", "Build, Run, and Regression Workflow", "workflow.md", True),
        ("subsystem_overview", "Subsystem Overview", "subsystem_overview.md", True),
        ("integration_flow", "Integration Flow", "integration_flow.md", True),
        ("interconnect", "Interconnect / Bus Structure", "interconnect.md", True),
        ("reset_clock", "Reset and Clock Structure", "reset_clock.md", True),
        ("interrupt", "Interrupt Structure", "interrupt.md", True),
        ("memory_map", "Memory Map", "memory_map.md", True),
        ("scenario", "Subsystem Scenario Structure", "scenario.md", True),
        ("scoreboard", "Integration Scoreboard / Checker", "scoreboard.md", True),
        ("debug", "Debug Entrypoints", "debug.md", True),
    ],
    "soc": [
        ("project", "Project Summary", "project.md", True),
        ("workflow", "Build, Run, and Regression Workflow", "workflow.md", True),
        ("system_overview", "SoC System Overview", "system_overview.md", True),
        ("boot_flow", "Boot Flow", "boot_flow.md", True),
        ("firmware", "Firmware / Baremetal Test Interface", "firmware.md", True),
        ("memory_map", "SoC Memory Map", "memory_map.md", True),
        ("interconnect", "SoC Interconnect / NoC", "interconnect.md", True),
        ("interrupt", "Interrupt Routing", "interrupt.md", True),
        ("reset_clock_power", "Reset, Clock, and Power Structure", "reset_clock_power.md", True),
        ("low_power", "Low Power Structure", "low_power.md", True),
        ("scenario", "SoC Scenario Structure", "scenario.md", True),
        ("test_env", "SoC Test Environment", "test_env.md", True),
        ("debug", "Debug Entrypoints", "debug.md", True),
    ],
}


def topics_for(kind: str) -> list[tuple[str, str, str, bool]]:
    if kind == "bt":
        return list(BT_TOPICS)
    return list(OTHER_TOPICS[kind])


def kind_config(kind: str) -> dict:
    cfg = {
        "schema_version": "kberif.kind_config.v1",
        "env_kind": kind,
        "display_name": KINDS[kind],
        "template": {"source": f"builtin.{kind}", "version": "0.3.0"},
        "agent": {
            "runner": "claudecode",
            "command": "claudecode -p",
            "init_only": True,
            "single_init_session": True,
            "thinking": {
                "enabled": False,
                "reasoning_effort": "none",
                "max_reasoning_tokens": 0,
            },
        },
        "query": {"engine": "topic", "runtime_ai": False, "allow_llm_query": False},
        "budgets": {
            "max_total_input_tokens": 350000,
            "max_total_output_tokens": 120000,
            "max_files_for_ai": 120,
            "max_bytes_per_file": 120000,
            "max_key_items_per_topic": 8,
            "max_evidence_per_item": 3,
            "max_repair_rounds": 2,
            "max_evidence_lines": 120,
        },
        "safety": {
            "redact_secrets": True,
            "deny_paths": [
                ".git/**",
                ".env",
                "**/*.pem",
                "**/*.key",
                "**/id_rsa",
                "build/**",
                "out/**",
                "*.vcd",
                "*.fsdb",
                "*.fst",
                "*.log",
            ],
        },
        "inputs": {
            "design": {
                "include": ["rtl/**/*.sv", "rtl/**/*.v", "src/**/*.sv", "design/**/*.sv"],
                "exclude": [],
                "role": "design",
            },
            "env": {
                "include": ["dv/**/*.sv", "tb/**/*.sv", "verif/**/*.sv"],
                "exclude": [],
                "role": "env",
            },
            "tests": {
                "include": ["tests/**/*.sv", "dv/tests/**/*.sv", "dv/test/**/*.sv"],
                "exclude": [],
                "role": "tests",
            },
            "docs": {
                "include": ["README*", "docs/**/*.md", "spec/**/*.md", "dv/docs/**/*.md", "dv/cfg/Makefile"],
                "exclude": [],
                "role": "docs",
            },
        },
    }
    return deepcopy(cfg)


def topics_config(kind: str) -> dict:
    return {
        "schema_version": "kberif.topics.v1",
        "env_kind": kind,
        "topics": {
            topic: {
                "card_id": f"{kind}.{topic}",
                "title": title,
                "prompt": f"kberif/prompts/{prompt}",
                "required": required,
            }
            for topic, title, prompt, required in topics_for(kind)
        },
    }


def template_prompt_path(kind: str, prompt: str) -> Path:
    return Path(__file__).parent / "config" / "templates" / kind / "prompts" / prompt


def default_views(kind: str) -> dict[str, dict]:
    if kind == "bt":
        views = {
            "onboard": ["project", "workflow", "design_overview", "interfaces", "test_env"],
            "debug": ["workflow", "backpressure", "fifos", "scheduling", "credit", "checker", "debug"],
            "add-test": ["workflow", "test_creation", "sequence", "checker", "debug"],
        }
    else:
        topics = [topic for topic, *_ in topics_for(kind)]
        views = {"onboard": topics[:5], "debug": ["workflow", "debug"], "add-test": topics[:4]}
    return {
        name: {"schema_version": "kberif.view.v1", "env_kind": kind, "mode": name, "topics": topics}
        for name, topics in views.items()
    }
