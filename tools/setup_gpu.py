"""Repair CUDA dependencies in the selected environment, then verify actual devices."""
import subprocess,sys
subprocess.run([sys.executable,'-m','pip','install','-r','requirements-gpu.txt'],check=True)
subprocess.run([sys.executable,'-m','pip','install','.[training,inference]'],check=True)
subprocess.run([sys.executable,'-m','visual_targeting.gpu'],check=True)
