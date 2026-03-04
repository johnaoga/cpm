#!/usr/bin/env python
"""Backward-compatible wrapper — delegates to ``cpm.cli.main()``.

After ``pip install conf-program-manager`` the ``cpm`` console script is
available globally.  This file keeps ``python main.py …`` working for
existing shell scripts and development workflows.
"""
from cpm.cli import main

if __name__ == "__main__":
    main()
