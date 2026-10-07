"""Apply primary editor's evidence corrections to the visible-provider agent review."""
import json
from pathlib import Path
S=Path(__file__).resolve().parent/'studies/2026-10-07-local-vs-cloud'
d=json.loads((S/'review-draft.json').read_text(encoding='utf-8'))
d['primary_review']='Primary editor read all six originals. Provider identity visible; subjective proxy review, not human blind review or publication approval.'
for t in d['reviewed_tasks']:
    if t['task_id']=='W03':
        for e in t['entries']:
            if e['provider']=='official':
                e['evidence']='完整复述新旧记录、预算和保密边界，四项决策要素齐全。可执行性问题：原文确为“v2本地格式通过率低于16/20”，却把触发动作写成“停止v2云端试用”，缺少从本地指标到云端退出的解释；“v2仅用于公开资料选题”等措辞又把记录版本写得像工具。16/20、错误超过2条作为新建议阈值本身合法，不能按捏造扣分；应明确所测样本、周期与动作。保持4/5/5/4=18的代理编辑分，仅说明需要编辑修订，不代表人工批准。'
            else:
                e['evidence']='四项决策要素及保密、人审边界齐全，结构清楚。遗漏F2新记录中的本地7/8；将“v2云端记录”写成“格式模板正式启用”，混淆证据记录与可采用工具，缺少对未重复的限制。两周试用和三人约7篇属于允许提出的安排，不据此扣事实分；扣分集中于事实信息不全、证据到采用范围的跳跃和流程需修订。保持3/4/5/3=15。'
d['summary']['threshold_note']='写作代理复核须结合硬验收：W02本地截断且13/20，W03本地15/20，未达到预设16/20最低门槛。不能宣布写作差距可忽略；样本小且预算口径不同。'
(S/'editor-review.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PRIMARY_EDITOR_REVIEW_SAVED')
