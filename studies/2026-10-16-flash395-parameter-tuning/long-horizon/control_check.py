"""Grader controls only, no model calls and no credentials."""
import json,tempfile
from pathlib import Path
from runner import Workspace
from grade import isolated

def main():
 here=Path(__file__).resolve().parent
 reference=(here/'reference.py').read_text(encoding='utf-8')
 checks=[]
 with tempfile.TemporaryDirectory(prefix='lh-control-') as folder:
  w=Workspace(Path(folder))
  for stage in range(1,5):
   w.advance(stage)
   if stage==1:
    bad=isolated(w.data['workflow.py'],stage=1)
    checks.append({'name':'initial_bad_implementation_rejected','pass':not bad.get('pass',False)})
   w.data['workflow.py']=reference;w.persist('workflow.py',reference)
   actual=isolated(reference,stage=stage)
   checks.append({'name':'reference_functional_stage_'+str(stage),'pass':actual.get('pass',False),'detail':actual})
   if stage>=3:
    ds='v2' if stage==3 else 'final'
    result=w.act('publish',{'dataset':ds});w.events.append({'tool':'publish','result':result})
    if stage==3:
     checks.append({'name':'injected_fault_retains_previous','pass':result.get('error')=='ENOSPC_INJECTED' and result.get('previous_release_unchanged') is True})
     result=w.act('publish',{'dataset':ds});w.events.append({'tool':'publish','result':result})
    checks.append({'name':'reference_publication_stage_'+str(stage),'pass':result.get('published',False)})
   if stage==4:
    w.events.append({'tool':'run_tests','result':actual})
    w.data['delivery.md']='''# 最终对账交付说明
本次采用v2规则，截止时间2026-10-04T23:59:59Z。当前已发布data/final，已付金额40.21元、退款5.51元、净额34.70元；客户A净额24.80元，客户B净额9.90元。数据引用data/final/refunds.csv，当前发布金额引用release/summary.json。已逐项核对当前发布文件与清单，金额计算采用十进制定点并逐条四舍五入至整数分。
迟到成功退款R04为3.40元，已经加入最终发布，订单本金保持不变，净额较此前v2发布减少3.40元。O05订单创建时间晚于截止时间，因此排除；R02为pending退款，因此排除；R03退款发生在截止时间之后，因此排除。重复行保持去重，冲突标识仍会报错。
执行了公开测试和v1兼容性回归，当前纯函数测试通过。首次发布注入ENOSPC，旧发布未损；根据真实工具反馈重试成功。最终再次发布，并对账data/final汇总，当前文件包含订单、客户和汇总三个结果以及摘要清单。没有把独立隐藏验收当作已执行的公开测试。
业务风险包括迟到退款继续到达、订单状态后续变化，以及源数据日期不符合规范。金额依赖输入完整性，超过本次截止时间的数据不在此次汇总范围；后续如补充数据，应重新对账并生成新发布，不能手工修改当前汇总文件。'''
    result=w.grade();checks.append({'name':'reference_final_report_and_delivery','pass':result['pass'],'detail':result})
 return {'pass':all(x['pass'] for x in checks),'checks':checks}
if __name__=='__main__':
 result=main();print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['pass'] else 1)
