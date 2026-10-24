# Reproduction

Use a Linux native AMD gfx1151 host with128GB unified memory and SSD copies of the named weights. Verify the complete weight SHA256 list, engine version/image identity and all freeze.json source hashes first. No weights or engine image are included here.

Run ONE server at a time using deployment-freeze.json settings. Point EVAL_BASE_URL at its OpenAI-compatible /v1 endpoint; set EVAL_API_KEY only if the existing server requires one, EVAL_MODEL to Qwen/Qwen3.8-Flash-Next, and EVAL_PROFILE to the condition label. Set EVAL_GUARD_COMMAND to a JSON argv array for a local command that verifies the actual single model, RAM/GPU release and resource isolation. It must print one JSON object. Keep that command and any machine-specific credentials outside the public study.

Invoke short_runner.py for each tasks.json task in rounds1/2. Run D01 with --variant depth for the separate thinking-off diagnostic. Invoke long-horizon/runner.py with --provider local --profile LABEL --round1/2 --output DIRECTORY, and long-context/runner.py with --provider local --task LC01 --round1/2 --output DIRECTORY. speed_runner.py accepts --profile LABEL --kind short512/prompt4k/prompt32k --round1/2/3 --output DIRECTORY. All arguments use spaces between option and value. Existing output directories must remain untouched; never overwrite a failed attempt.

Keep all streamed event files, call payloads, tool traces, stage snapshots, result files, actual API token counts and resource samples. aggregate.py is read-only and needs actual primary editorial reviews, tied to exact response hashes, to turn writing format results into quality results. Unreviewed metrics are not final grades. Missing native timing remains unknown.

The private machine controller restores the original service after the comparison; it is not a portable inference dependency. Its SHA256 identifies the experiment's isolation code. See protocol.md for every fixed budget, quality gate and the prospective recovery-wording amendment.
