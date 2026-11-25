# LLM baseline for Yorùbá numerals: preregistration

Deposited before the first model call. `preregistration.json` holds the SHA-256 of every file that defines the
protocol, and `protocol_sha256` is the hash of that list (8898bd8b508ea01ebc97456a5a1032374474ec3f55b179320fecab122fb78571).

Public here: `preregistration.json`, `config.json`, `ANALYSIS_PLAN.md`, `prompts.json`, `items_generation.jsonl`
(the 300 numbers for the generation task) and the two scripts in `scripts/`. Each matches its hash in
`preregistration.json`.

Withheld: `items_recognition.jsonl` and `fewshot.json`. They contain verse text from sources whose licences do not
allow republication (the Biblica and Bible Society of Nigeria Bibles, the Yorùbá Book of Mormon, the Qur'an
translation, MENYO-20k: non-commercial). Their hashes are in `preregistration.json`, so the copies given to
examiners or placed in a restricted deposit can be checked against this record.

Check a file:  python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" FILE

Model: claude-sonnet-5-5 (Anthropic API), no temperature sent, up to 8,192 output tokens. Analysis: ANALYSIS_PLAN.md.
