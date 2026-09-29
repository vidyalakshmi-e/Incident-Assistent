"""Shared taxonomies and lexicons.

These are documented, rule-based mappings. Every value produced from them carries provenance
"derived" (or "synthetic" when the input text itself was synthetic).
"""
from __future__ import annotations

import re

# Unified domain categories. Source A's own labels are a subset of this list.
CATEGORIES = [
    "Application", "Database", "Storage", "Network", "Hardware", "Security",
    "Infrastructure", "Performance",
]

# Source B CI_Subcat → CI group (used for sampling, routing, and the derived category).
CI_SUBCAT_GROUP: dict[str, str] = {
    "Server Based Application": "app_server",
    "Web Based Application": "app_web",
    "Desktop Application": "app_desktop",
    "Client Based Application": "app_desktop",
    "Standard Application": "app_desktop",
    "SAP": "sap",
    "Citrix": "citrix_vdi",
    "VDI": "citrix_vdi",
    "Exchange": "collab",
    "SharePoint Farm": "collab",
    "Laptop": "enduser_hw",
    "Desktop": "enduser_hw",
    "Monitor": "enduser_hw",
    "Keyboard": "enduser_hw",
    "Printer": "enduser_hw",
    "Scanner": "enduser_hw",
    "KVM Switches": "enduser_hw",
    "Banking Device": "banking_device",
    "SAN": "storage",
    "Database": "database",
    "Windows Server": "server",
    "Linux Server": "server",
    "Unix Server": "server",
    "X86 Server": "server",
    "ESX Cluster": "server",
    "zOS Cluster": "server",
    "NonStop Server": "server",
    "DataCenterEquipment": "server",
    "Network Component": "network",
    "Switch": "network",
    "Router": "network",
    "Lines": "network",
    "Net Device": "network",
    "Controller": "network",
    "Encryption": "security_sw",
    "System Software": "security_sw",
    "Automation Software": "security_sw",
}

CI_GROUP_CATEGORY: dict[str, str] = {
    "app_server": "Application", "app_web": "Application", "app_desktop": "Application",
    "sap": "Application", "citrix_vdi": "Application", "collab": "Application",
    "enduser_hw": "Hardware", "banking_device": "Hardware", "storage": "Storage",
    "database": "Database", "server": "Infrastructure", "network": "Network",
    "security_sw": "Security",
}

# Rule-based routing: which (derived) support team owns a CI group. There is no assignment-group
# column in either source, so this is a documented *derived* mapping, never an observed one.
CI_GROUP_TEAM: dict[str, str] = {
    "app_server": "Application Support", "app_web": "Application Support",
    "app_desktop": "Workplace Applications", "sap": "SAP Competence Center",
    "citrix_vdi": "Workplace Virtualization", "collab": "Messaging & Collaboration",
    "enduser_hw": "Workplace Hardware", "banking_device": "Branch Devices",
    "storage": "Storage Engineering", "database": "Database Administration",
    "server": "Server Operations", "network": "Network Operations",
    "security_sw": "Security Operations",
}

CATEGORY_TEAM: dict[str, str] = {
    "Application": "Application Support", "Database": "Database Administration",
    "Storage": "Storage Engineering", "Network": "Network Operations",
    "Hardware": "Workplace Hardware", "Security": "Security Operations",
    "Infrastructure": "Server Operations", "Performance": "Application Support",
}

# Keyword lexicon used to infer a category from text (category correction + contradiction checks).
CATEGORY_LEXICON: dict[str, list[str]] = {
    "Storage": ["disk space", "storage", "volume", "lun", "san", "capacity", "quota", "archive",
                "filesystem", "file system", "disk full"],
    "Database": ["database", "db ", "query", "queries", "sql", "tablespace", "index", "deadlock",
                 "lock contention", "transaction log"],
    "Security": ["unauthorized", "login attempts", "failed login", "brute force", "certificate",
                 "multi-factor", "mfa", "locked out", "lockout", "malware", "encryption",
                 "block ip", "intrusion"],
    "Network": ["network", "stream", "vpn", "dns", "packet", "switch", "router", "bandwidth",
                "connectivity", "tunnel", "interface", "broadcast"],
    "Performance": ["slow", "slowly", "cpu", "memory", "latency", "performance", "sluggish",
                    "excessive", "high usage", "degradation"],
    "Application": ["application", "encoder", "codec", "crash", "crashed", "bug", "software",
                    "release", "conversion", "service"],
    "Hardware": ["hardware", "fan", "power supply", "laptop", "printer", "device", "card reader",
                 "motherboard", "disk failure", "hba"],
    "Infrastructure": ["server", "reboot", "patch", "host", "cluster", "virtual machine", "vm "],
}


def infer_category(text: str) -> tuple[str | None, dict[str, int]]:
    """Return (best category, hit counts). None when no keyword matched."""
    t = f" {text.lower()} "
    scores = {cat: sum(1 for kw in kws if kw in t) for cat, kws in CATEGORY_LEXICON.items()}
    best = max(scores, key=scores.get)
    return (best if scores[best] > 0 else None), scores


# Documented rule used only where no Priority exists (Source A): severity from description wording.
SEVERITY_LEXICON: list[tuple[str, list[str]]] = [
    ("high", ["unauthorized", "stopped responding", "crash", "crashed", "timing out", "failure",
              "down", "outage", "cannot log in", "not available"]),
    ("medium", ["slow", "slowly", "exceeded threshold", "excessive", "degraded", "intermittent"]),
]


def infer_severity(text: str) -> str | None:
    t = text.lower()
    for label, kws in SEVERITY_LEXICON:
        if any(k in t for k in kws):
            return label
    return None


_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())
