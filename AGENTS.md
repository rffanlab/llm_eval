# Evaluation rules

- Present every study in three stages: why evaluate, how evaluate (hardware, environment, prompts, settings, scoring), then results.
- Freeze prompts, reference answers and acceptance criteria before calls. Preserve failures, truncations and partial runs.
- Keep provider credentials, private addresses, SSH credentials and voice references out of Git.
- Never infer human approval, writing quality or equivalence from valid JSON or successful execution alone.
- Token Plan personal endpoints are for tool-integrated interactive use only. No unattended suite loops, load tests or scheduled batch calls through that channel. Each case is initiated and reviewed in the active agent conversation. Use a separately authorized channel for automation.
- A model alias does not prove that cloud and local weights are identical. Record the endpoint model ID, returned model, quantization, engine and dated environment snapshot.
- Article/video: explain why and how before the result section; in the result section pair each task with its actual outputs, differences and conclusion, then summarize. Do not turn these editorial instructions into spoken narration.
- Formal narration uses the owner's authorized voice. CosyVoice3 is permanently excluded. ASR and loudness checks do not replace listening review.
- Local-device comparisons run one inference model at a time. After boot inspect automatically started model services; before switching, stop the prior engine and wait for RAM/VRAM/GTT allocations to release. Check actual model processes and available memory before measured calls. Record host-specific admission thresholds in the study.
- After a runtime failure and reboot, diagnose retained kernel/service logs and driver readiness before resuming inference. Preserve original failed recordings; recovery does not replace them or establish an unverified root cause.
