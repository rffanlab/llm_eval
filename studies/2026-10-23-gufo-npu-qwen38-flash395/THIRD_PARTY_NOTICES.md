# Third-party material

The evaluated Qwen3.8 Next Flash weights originate from Qwen and the pinned
Unsloth GGUF release. The upstream Qwen Community License 1.0 notice is retained
in [Qwen-LICENSE.txt](Qwen-LICENSE.txt). Weights and private voice references are
not redistributed in this study. Model identity and revisions are recorded in
`deployment-freeze.json`.

Gufo and the community NPU implementation are MIT-licensed:
https://github.com/mikealanni/gufo/tree/a1f5549fd56dbe46eef0c7baff5239b0f5d64142

The NPU firmware comes unmodified from the Linux firmware repository, under
AMD's redistributable binary firmware license (`LICENSES/LICENSE.amdnpu`). Its
source revision, exact file and hashes are in `deployment-freeze.json`; the
firmware binary is not included in this public study.

No standalone chat-template file is supplied here. Gufo's model-specific
formatting path is used consistently for all three conditions.
