# -*- coding: utf-8 -*-
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_module("decisiones", run_name="__main__")
