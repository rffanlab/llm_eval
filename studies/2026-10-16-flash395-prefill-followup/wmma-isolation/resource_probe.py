"""Two-second RAM/GPU samples. No model processes or credentials are logged."""
import ctypes,json,pathlib,sys,time,os
def snapshot():
 p=pathlib.Path;memory={line.split(':')[0]:int(line.split()[1])*1024 for line in p('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','SwapTotal:','SwapFree:'))}
 row={'epoch':time.time(),**memory,'loadavg':os.getloadavg(),'gpu':[]}
 for d in p('/sys/class/drm').glob('card*/device'):
  if '-' in d.parent.name or not (d/'mem_info_gtt_used').exists():continue
  vals={k:int((d/f).read_text()) for k,f in [('VRAM','mem_info_vram_used'),('GTT','mem_info_gtt_used'),('VRAM_total','mem_info_vram_total'),('GTT_total','mem_info_gtt_total')] if (d/f).exists()};row['gpu'].append({'backend':'amdgpu','pci':d.resolve().name,**vals})
 try:
  lib=ctypes.CDLL('libnvidia-ml.so.1');assert lib.nvmlInit_v2()==0;h=ctypes.c_void_p();uuid=os.environ.get('EVAL_GPU_UUID');assert uuid,'explicit benchmark GPU UUID required';lib.nvmlDeviceGetHandleByUUID.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p)];assert lib.nvmlDeviceGetHandleByUUID(uuid.encode(),ctypes.byref(h))==0
  class Mem(ctypes.Structure):_fields_=[('total',ctypes.c_ulonglong),('free',ctypes.c_ulonglong),('used',ctypes.c_ulonglong)]
  class Util(ctypes.Structure):_fields_=[('gpu',ctypes.c_uint),('memory',ctypes.c_uint)]
  m=Mem();u=Util();power=ctypes.c_uint();temp=ctypes.c_uint();assert lib.nvmlDeviceGetMemoryInfo(h,ctypes.byref(m))==0;lib.nvmlDeviceGetUtilizationRates(h,ctypes.byref(u));lib.nvmlDeviceGetPowerUsage(h,ctypes.byref(power));lib.nvmlDeviceGetTemperature(h,0,ctypes.byref(temp));row['gpu'].append({'backend':'NVML','VRAM':m.used,'VRAM_total':m.total,'gpu_util_pct':u.gpu,'memory_util_pct':u.memory,'power_mw':power.value,'temperature_c':temp.value,'role':'benchmark_gpu'});lib.nvmlShutdown()
 except (OSError,AssertionError,AttributeError) as e:
  if os.environ.get('EVAL_GPU_UUID'):row['gpu_probe_error']=type(e).__name__+': '+str(e)
 return row
def sampler(stop,path):
 if sys.platform=='win32':return
 with path.open('a',encoding='utf-8') as f:
  while not stop.is_set():
   f.write(json.dumps(snapshot())+'\n');f.flush();stop.wait(2)
