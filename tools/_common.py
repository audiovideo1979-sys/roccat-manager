import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def say(msg=''):
    print(msg, flush=True)


def ask(prompt):
    return input(prompt).strip().lower()


def yes(prompt):
    while True:
        a = ask(prompt + ' [y/n] ')
        if a in ('y', 'yes'):
            return True
        if a in ('n', 'no'):
            return False
