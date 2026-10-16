"""Persistent user data stays outside PyInstaller's temporary bundle."""
import os
import sys
from pathlib import Path


def data_dir():
    if getattr(sys, 'frozen', False):
        root = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ErrorLogBot'
    else:
        root = Path(__file__).resolve().parent.parent
    root.mkdir(parents=True, exist_ok=True)
    return root


def desktop_dir():
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                return Path(os.path.expandvars(winreg.QueryValueEx(key, 'Desktop')[0]))
        except OSError:
            pass
    return Path.home() / 'Desktop'
