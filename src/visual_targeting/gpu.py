"""GPU-only neural execution. Never silently selects CPU."""
import json

def require_gpu(device='0',torch_module=None):
    if torch_module is None:
        try:import torch as torch_module
        except ImportError:raise ValueError('GPU support is not installed. Click Install / repair GPU support.') from None
    value=str(device).removeprefix('cuda:')
    if not value.isdigit():raise ValueError('GPU-only mode: choose a CUDA GPU index (0 or 1), never cpu/auto.')
    index=int(value)
    if not torch_module.cuda.is_available() or index>=torch_module.cuda.device_count():
        raise ValueError('CUDA GPU '+value+' unavailable. Click Install / repair GPU support, then restart the app. CPU fallback is disabled.')
    return str(index)

def main():
    import torch
    require_gpu('0',torch)
    print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'gpus':[{'index':i,'name':torch.cuda.get_device_name(i),'memory_gb':round(torch.cuda.get_device_properties(i).total_memory/1024**3,1)} for i in range(torch.cuda.device_count())],'cpu_fallback':False}),flush=True)
if __name__=='__main__':main()
