# LLM baseline for Yorùbá numerals: preregistration, version 2 (amendment)

Deposited before the first model call of version 2. It replaces version 1 (`../llm_baseline_preregistration`,
commit fdeb34c), whose run was stopped for cost after 1,243 of 22,948 calls; `ANALYSIS_PLAN.md` gives the reasons
and what changed. `preregistration.json` holds the SHA-256 of every file that defines the protocol, and
`protocol_sha256` is the hash of that list (e9bbdc3e8c3c05e8f93ed8134ffb870736a8b164658fdd77f698bc6c08733278).

Public here: `preregistration.json`, `config.json`, `ANALYSIS_PLAN.md`, `prompts.json`, `items_generation.jsonl`
(the 100 numbers for the generation task) and the two scripts in `scripts/`. Each matches its hash in
`preregistration.json`.

Withheld: `items_recognition.jsonl` and `fewshot.json` (the five-shot examples; this version runs zero-shot only,
but the file is part of the protocol). They contain verse text from sources whose licences do not allow
republication (the Biblica and Bible Society of Nigeria Bibles, the Yorùbá Book of Mormon, the Qur'an translation,
MENYO-20k: non-commercial). Their hashes are in `preregistration.json`, so copies given to examiners or placed in
a restricted deposit can be checked against this record.

Check a file:  python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" FILE

Model: claude-sonnet-5-5 (Anthropic API), zero-shot, no temperature sent, up to 8,192 output tokens.
