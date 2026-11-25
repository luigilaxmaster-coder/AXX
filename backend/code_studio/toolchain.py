"""Discover an installed Python without requiring Python on the native launcher's PATH.

Uses the official PythonCore PEP 514 registry keys on Windows. No downloads,
project interpreters, executable arguments from models, or registry mutations.
"""
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
import sys


@lru_cache(maxsize=8)
def installed_python(module=None):
    if module not in (None,'pylsp','debugpy','pytest'):
        raise ValueError('Unsupported Python tool module')
    candidates=[]
    if not getattr(sys,'frozen',False):candidates.append(sys.executable)
    found=shutil.which('python')
    if found:candidates.append(found)
    if os.name=='nt':
        import winreg
        for scope in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(scope,r'Software\Python\PythonCore') as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            tag=winreg.EnumKey(key,i)
                            with winreg.OpenKey(key,tag+r'\InstallPath') as entry:
                                try:candidates.append(winreg.QueryValueEx(entry,'ExecutablePath')[0])
                                except OSError:candidates.append(str(Path(winreg.QueryValueEx(entry,'')[0])/'python.exe'))
                        except OSError:continue
            except OSError:continue
    seen=set()
    for candidate in candidates:
        path=Path(candidate).resolve()
        if path in seen or not path.is_file() or 'windowsapps' in str(path).lower():continue
        seen.add(path)
        from backend.actions.process_runner import ENV_NAMES
        env={k:v for k,v in os.environ.items() if k.lower() in ENV_NAMES}
        try:
            check=subprocess.run([str(path),'-I','-c',
                "import importlib.util,sys;sys.exit(0 if sys.version_info >= (3,11) and (not sys.argv[1] or importlib.util.find_spec(sys.argv[1])) else 1)",module or ''],
                cwd=str(path.parent),env=env,capture_output=True,timeout=10,check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if check.returncode==0:return str(path)
        except (OSError,subprocess.TimeoutExpired):continue
    return None
