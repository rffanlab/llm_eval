"""Pinned 64MiB host<->GPU synchronous copy, 5 groups of 10, median GB/s."""
import ctypes as c,json,os,statistics,time
assert os.environ.get('ROCR_VISIBLE_DEVICES'),'bind the intended GPU explicitly'
h=c.CDLL('/opt/rocm/lib/libamdhip64.so')
def check(code):
    if code:raise RuntimeError('HIP error '+str(code))
count=c.c_int();check(h.hipGetDeviceCount(c.byref(count)));assert count.value==1
check(h.hipSetDevice(0));name=c.create_string_buffer(256);check(h.hipDeviceGetName(name,256,0))
assert '7900 XTX' in name.value.decode(),name.value
h.hipHostMalloc.argtypes=[c.POINTER(c.c_void_p),c.c_size_t,c.c_uint]
h.hipMalloc.argtypes=[c.POINTER(c.c_void_p),c.c_size_t]
h.hipMemcpy.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.c_int]
n=64*1024*1024;host=c.c_void_p();dev=c.c_void_p()
check(h.hipHostMalloc(c.byref(host),n,0));check(h.hipMalloc(c.byref(dev),n))
try:
    c.memset(host,90,n);check(h.hipMemcpy(dev,host,n,1));c.memset(host,0,n);check(h.hipMemcpy(host,dev,n,2))
    assert c.c_ubyte.from_address(host.value).value==90 and c.c_ubyte.from_address(host.value+n-1).value==90
    result={'gpu':name.value.decode(),'gpu_binding':os.environ['ROCR_VISIBLE_DEVICES'],'bytes_per_copy':n,'groups':5,'copies_per_group':10,'boundary':'synchronous hipMemcpy wall time; pinned host, warmed allocation','rates_gb_s':{}}
    for kind,label in [(1,'host_to_gpu'),(2,'gpu_to_host')]:
        rates=[]
        for _ in range(5):
            at=time.monotonic()
            for __ in range(10):check(h.hipMemcpy(dev if kind==1 else host,host if kind==1 else dev,n,kind))
            rates.append(n*10/(time.monotonic()-at)/1e9)
        result['rates_gb_s'][label]={'all':rates,'median':statistics.median(rates)}
    print(json.dumps(result,indent=2))
finally:
    check(h.hipFree(dev));check(h.hipHostFree(host))
