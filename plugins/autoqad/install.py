#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Safely install AutoQAD into a QGIS profile.

    python install.py                 # install to the default profile
    python install.py --profile foo   # install to a named profile
    python install.py --uninstall
    python install.py --dry-run

**Why this exists.** The obvious command is wrong::

    cp -r plugins/autoqad "$PROFILE/python/plugins/"

When the destination already exists, ``cp -r`` copies the source *into* it
rather than over it, producing ``plugins/autoqad/autoqad/`` — or worse, a whole
plugin tree nested inside one of its own subpackages. The symptom is a baffling
``ImportError`` naming something that is plainly defined in the repo, because
the file being imported is not the file you are looking at.

This installer always **removes the destination first**, then copies, so the
installed tree is always an exact mirror of the source. It is idempotent: run
it as often as you like.
"""

import argparse
import os
import shutil
import sys

PLUGIN_NAME = "autoqad"

#: Copied wholesale, preserving structure.
DIRECTORIES = ("core", "engine", "input", "geom", "style", "commands", "ui",
               "io")

#: Copied individually.
FILES = ("__init__.py", "main_plugin.py", "controller.py", "scripting.py",
         "metadata.txt", "icon.png", "LICENSE", "README.md")

#: Never installed — dev-only clutter.
EXCLUDE_DIRS = {"__pycache__", "test", ".git"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo")


def profile_root(profile="default"):
    """Return the QGIS profile directory for this platform, or ``None``."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if not base:
            return None
        return os.path.join(base, "QGIS", "QGIS3", "profiles", profile)

    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", "QGIS", "QGIS3",
                            "profiles", profile)

    return os.path.join(os.path.expanduser("~"), ".local", "share", "QGIS",
                        "QGIS3", "profiles", profile)


def _ignore(_directory, names):
    return {n for n in names
            if n in EXCLUDE_DIRS or n.endswith(EXCLUDE_SUFFIXES)}


def install(source, destination, dry_run=False):
    """Mirror *source* into *destination*. Returns the number of files copied."""
    if dry_run:
        print("[dry run] would remove and rewrite {0}".format(destination))
        return 0

    # The whole point: wipe first, so a stale or nested tree cannot survive.
    if os.path.isdir(destination):
        shutil.rmtree(destination, ignore_errors=True)
        if os.path.isdir(destination):
            raise RuntimeError(
                "Could not remove {0}.\nClose QGIS and try again — it holds "
                "locks on loaded plugin files.".format(destination))
    os.makedirs(destination)

    copied = 0
    for name in FILES:
        origin = os.path.join(source, name)
        if os.path.exists(origin):
            shutil.copy2(origin, os.path.join(destination, name))
            copied += 1

    for name in DIRECTORIES:
        origin = os.path.join(source, name)
        if not os.path.isdir(origin):
            continue
        target = os.path.join(destination, name)
        shutil.copytree(origin, target, ignore=_ignore)
        copied += sum(len(files) for _r, _d, files in os.walk(target))

    return copied


def verify(destination):
    """Sanity-check the installed tree. Returns a list of problems."""
    problems = []

    init = os.path.join(destination, "__init__.py")
    if not os.path.exists(init):
        problems.append("missing __init__.py")
    else:
        with open(init, encoding="utf-8") as handle:
            if "def classFactory" not in handle.read():
                problems.append("__init__.py has no classFactory")

    # The corruption signature: a plugin root nested inside a subpackage.
    roots = []
    for current, directories, files in os.walk(destination):
        directories[:] = [d for d in directories if d not in EXCLUDE_DIRS]
        if "main_plugin.py" in files:
            roots.append(os.path.relpath(current, destination))
    if len(roots) > 1:
        problems.append(
            "nested plugin copies found at: {0}".format(", ".join(roots)))

    commands_init = os.path.join(destination, "commands", "__init__.py")
    if os.path.exists(commands_init):
        with open(commands_init, encoding="utf-8") as handle:
            if "def build_registry" not in handle.read():
                problems.append("commands/__init__.py is not the right file")
    else:
        problems.append("missing commands/__init__.py")

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--profile", default="default",
                        help="QGIS profile name (default: 'default')")
    parser.add_argument("--dest", default=None,
                        help="explicit plugins directory, overriding --profile")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    source = os.path.dirname(os.path.abspath(__file__))

    if args.dest:
        plugins_dir = args.dest
    else:
        root = profile_root(args.profile)
        if root is None:
            print("Could not locate the QGIS profile directory. "
                  "Pass --dest explicitly.", file=sys.stderr)
            return 2
        plugins_dir = os.path.join(root, "python", "plugins")

    destination = os.path.join(plugins_dir, PLUGIN_NAME)

    if args.uninstall:
        if os.path.isdir(destination):
            if args.dry_run:
                print("[dry run] would remove {0}".format(destination))
            else:
                shutil.rmtree(destination, ignore_errors=True)
                print("Removed {0}".format(destination))
        else:
            print("Nothing installed at {0}".format(destination))
        return 0

    if not os.path.isdir(plugins_dir):
        if args.dry_run:
            print("[dry run] would create {0}".format(plugins_dir))
        else:
            os.makedirs(plugins_dir)

    print("source      : {0}".format(source))
    print("destination : {0}".format(destination))

    try:
        copied = install(source, destination, args.dry_run)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    if args.dry_run:
        return 0

    problems = verify(destination)
    if problems:
        print("\nInstalled, but the result looks wrong:", file=sys.stderr)
        for problem in problems:
            print("  - {0}".format(problem), file=sys.stderr)
        return 1

    print("Installed {0} files. Restart QGIS, then enable AutoQAD in "
          "Plugins > Manage and Install Plugins.".format(copied))
    return 0


if __name__ == "__main__":
    sys.exit(main())
