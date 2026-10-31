"""Prompt and task-table checks (plan step 3), run in the pixi env (needs robocasa and the PaliGemma tokenizer).

  pixi run python stl_prompt/test_prompts.py [recordings_dir]   (default eval_logs_stl/idle)

- the 18 tasks are RoboCasa's atomic_seen group, with RoboCasa's horizons;
- every prompt of every recorded episode (3 per episode; the idle check records all 180 scenes) matches the
  templates in the doc, uses RoboCasa's own words, is ASCII, and fits π0.5's 200-token text budget together
  with the state string and the `Action:` suffix (otherwise it would be cut without warning);
- the episode-0 prompts equal the example table in docs/2026-10-31-robocasa-experiment.md.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stl_spec import TASKS, make_prompts, prompt_names, stl_nl_suffix  # noqa: E402

WS = HERE.parent
DOC = WS.parent / "docs" / "2026-10-31-robocasa-experiment.md"
MAX_TOKENS = 200  # π0.5 tokenizer_max_length
STATE_WORST = " ".join(["128"] * 16)  # 16 state numbers in 0..255; 3 digits each is the longest


def check_registry():
    from robocasa.utils.dataset_registry import TARGET_TASKS
    from robocasa.utils.dataset_registry_utils import get_task_horizon

    assert list(TARGET_TASKS["atomic_seen"]) == list(TASKS), "task list differs from RoboCasa's atomic_seen"
    for task, info in TASKS.items():
        assert int(get_task_horizon(task)) == info.horizon, (task, get_task_horizon(task), info.horizon)
        assert info.horizon % 50 == 0, f"{task}: limit not a multiple of n_action_steps=50"
    print("PASS registry: 18 atomic_seen tasks, horizons match, all multiples of 50")


def load_episodes(d: Path) -> list[dict]:
    eps = []
    for p in sorted(d.rglob("*.json.gz")):
        with gzip.open(p, "rt") as f:
            t = json.load(f)
        eps.append({k: t[k] for k in ("task", "seed", "orig_prompt", "names", "prompts")} | {"file": p.name})
    return eps


def check_templates(eps: list[dict]):
    rx = {
        "P": r" Finish within (\d+) seconds, then let go and leave it there until the end\. Do not move any other object\.",
        "F": r" Finish within (\d+) seconds, then let go and leave (it|them) (closed|open|in|out|off|on) until the end\."
             r" Do not move any other object\.",
        "N": r" Arrive within (\d+) seconds and stay there until the end\. Do not move any other object\.",
    }
    stl_rx = {
        "P": r"F\[0,(\d+)\] G resting_(in|on|under)\((\w+), (\w+)\) & G !moved\(other_objects\)",
        "F": r"F\[0,(\d+)\] G \((closed|open|slid_in|slid_out|off|on)\((\w+)\) & released\((\w+)\)\) & G !moved\(other_objects\)",
        "N": r"F\[0,(\d+)\] G \(at\((\w+)\) & stopped\(robot\)\) & G !moved\(other_objects\)",
    }
    for e in eps:
        task, info = e["task"], TASKS[e["task"]]
        p, lang = e["prompts"], e["orig_prompt"]
        assert p["nl"] == lang, e
        assert p["stl_nl"].startswith(lang) and lang.endswith("."), e
        m = re.fullmatch(rx[info.kind], p["stl_nl"][len(lang):])
        assert m and int(m.group(1)) == info.deadline_s, (e["file"], p["stl_nl"])
        m = re.fullmatch(stl_rx[info.kind], p["stl"])
        assert m and int(m.group(1)) == info.deadline_s, (e["file"], p["stl"])
        # the names are RoboCasa's own words from the instruction
        n = e["names"]
        words = {"P": [n.get("obj"), n.get("target")], "F": [n.get("part")], "N": [n.get("fixture")]}[info.kind]
        for w in words:
            if task == "CoffeeSetupMug" and w == "coffee dispenser":
                continue  # the instruction says "coffee machine dispenser"
            if task == "TurnOnElectricKettle" or (task == "CloseBlenderLid" and w == "lid"):
                assert w in lang.lower(), (w, lang)
                continue
            assert w in lang, (task, w, lang)
        if info.kind == "F":
            assert (n["pronoun"] == "them") == (" doors" in lang), e
        # the prompts are reproducible from the recorded names
        cur = make_prompts(task, lang, n.get("obj") if info.kind == "P" else None,
                           n.get("target") if task in ("PickPlaceCounterToStove", "PickPlaceSinkToCounter") else None)
        assert cur == p, (e["file"], cur, p)
        for v in p.values():
            assert v.isascii(), v
    print(f"PASS templates: {3 * len(eps)} prompts from {len(eps)} episodes match the templates")


def check_tokens(eps: list[dict]):
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("google/paligemma-3b-pt-224")
    worst = {}
    for e in eps:
        for v, prompt in e["prompts"].items():
            cleaned = prompt.strip().replace("_", " ").replace("\n", " ")  # as in π0.5's processor
            full = f"Task: {cleaned}, State: {STATE_WORST};\nAction: "
            n = len(tok(full)["input_ids"])
            if n > worst.get(v, (0, ""))[0]:
                worst[v] = (n, prompt)
            assert n <= MAX_TOKENS, (n, prompt)
    for v, (n, p) in worst.items():
        print(f"  longest {v}: {n} tokens  {p!r}")
    print(f"PASS tokens: every full π0.5 prompt fits in {MAX_TOKENS} tokens")


def check_doc_table(eps: list[dict]):
    rows = {}
    text = DOC.read_text()
    sec = text.split("Example prompts for episode 0", 1)[1].split("## Metrics", 1)[0]
    for line in sec.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[1] in TASKS:
            rows[cells[1]] = {"nl": cells[2], "stl_nl": cells[3], "stl": cells[4].strip("`")}
    got = {e["task"]: e["prompts"] for e in eps if e["seed"] == 1000}
    missing = [t for t in TASKS if t not in got]
    bad = [t for t in rows if t in got and rows[t] != got[t]]
    for t in bad:
        print(f"  DOC MISMATCH {t}:\n    doc {rows[t]}\n    got {got[t]}")
    assert not bad, bad
    assert len(rows) == 18, f"found {len(rows)} example rows in the doc"
    print(f"PASS doc table: {sum(t in got for t in rows)} of {len(rows)} example rows checked, all equal" +
          (f" (no recording for {missing})" if missing else ""))


def check_names_unit():
    assert prompt_names("CloseFridge", "Close the fridge doors.")["pronoun"] == "them"
    assert prompt_names("TurnOffStove", "Turn off the rear right burner of the stove.")["part"] == "rear right burner"
    n = prompt_names("SlideDishwasherRack", "Fully slide the top dishwasher rack out.")
    assert n["pred"] == "slid_out" and n["state"] == "out" and n["part"] == "top dishwasher rack"
    assert stl_nl_suffix("OpenCabinet", prompt_names("OpenCabinet", "Open the cabinet door.")).startswith(
        " Finish within 21 seconds, then let go and leave it open")
    p = make_prompts("PickPlaceCounterToStove", "Pick the cream cheese stick from the plate and place it in the pan.",
                     "cream cheese stick", "pan")
    assert p["stl"] == "F[0,12] G resting_in(cream_cheese_stick, pan) & G !moved(other_objects)"
    print("PASS name parsing")


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else WS / "eval_logs_stl" / "idle"
    check_names_unit()
    check_registry()
    eps = load_episodes(d)
    print(f"{len(eps)} recorded episodes in {d}")
    if eps:
        check_templates(eps)
        check_tokens(eps)
        check_doc_table(eps)
