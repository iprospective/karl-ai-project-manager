#!/usr/bin/env python3
"""Tests RM3609 — PM lit la knowledge sans mmi-kb."""
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pm_knowledge import KnowledgeError, KnowledgeStore  # noqa: E402

fails = []


def check(label, cond):
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        fails.append(label)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        knowledge = root / "knowledge"
        (knowledge / "redmine").mkdir(parents=True)
        (knowledge / "redmine/api.md").write_text(
            "---\nid: doc:redmine/api\ntitle: Redmine API\nproduct: redmine\n---\n\n# Redmine API\n\nUtiliser X-Redmine-API-Key.\n",
            encoding="utf-8",
        )

        local = KnowledgeStore(mode="local", local=knowledge)
        info = local.info()
        check("mode local", info["mode"] == "local")
        doc = local.get("doc:redmine/api")
        check("get local", doc and "X-Redmine-API-Key" in doc.get("body", ""))
        check("search local", any(row["id"] == "doc:redmine/api" for row in local.search("API-Key")))
        view = local.view("docs")
        check("vue locale", any(item["id"] == "doc:redmine/api" for item in view["items"]))

        empty = KnowledgeStore(mode="local", local=root / "absent")
        check("PM sans KB ne crash pas", empty.get("doc:x") is None and empty.search("x") == [])

        snapshot = knowledge / "kb-snapshot"
        (snapshot / "views").mkdir(parents=True)
        (snapshot / "manifest.json").write_text(json.dumps({"schema": "mmi-kb.bundle/v1", "knowledge_commit": "abc1234"}), encoding="utf-8")
        (snapshot / "entities.jsonl").write_text(
            json.dumps({"id": "doc:zabbix/api", "title": "Zabbix API", "summary": "JSON-RPC", "body": "token"}) + "\n",
            encoding="utf-8",
        )
        (snapshot / "views" / "compat.json").write_text(json.dumps({"schema": "mmi-kb.view/v1", "view": "compat", "items": []}), encoding="utf-8")

        snap = KnowledgeStore(mode="snapshot", local=knowledge, snapshot=snapshot)
        check("mode snapshot", snap.info()["snapshot_commit"] == "abc1234")
        check("get snapshot", snap.get("doc:zabbix/api")["title"] == "Zabbix API")
        check("search snapshot", any(row["id"] == "doc:zabbix/api" for row in snap.search("JSON-RPC")))
        check("view snapshot", snap.view("compat")["view"] == "compat")

        remote = KnowledgeStore(mode="remote", local=knowledge, snapshot=snapshot, url="http://127.0.0.1:1")
        check("remote indisponible -> snapshot", remote.get("doc:zabbix/api")["title"] == "Zabbix API")

        try:
            KnowledgeStore(mode="nope", local=knowledge)
        except KnowledgeError:
            check("mode inconnu refuse", True)
        else:
            check("mode inconnu refuse", False)

    print()
    if fails:
        print(f"ECHEC : {len(fails)} assertion(s) — {fails}")
        return 1
    print("OK — knowledge PM autonome")
    return 0


if __name__ == "__main__":
    sys.exit(main())
