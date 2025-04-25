"""
This module provides a mixin class for the BEC class that allows the user to load and unload scripts from the `scripts` directory.
"""

from __future__ import annotations

import builtins
import glob
import importlib
import inspect
import os
import pathlib
import traceback
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from bec_lib.callback_handler import EventType
from bec_lib.logger import bec_logger
from bec_lib.utils.import_utils import lazy_import, lazy_import_from

if TYPE_CHECKING:  # pragma: no cover
    from pylint.message import Message

logger = bec_logger.logger
pylint = lazy_import("pylint")
CollectingReporter = lazy_import_from("pylint.reporters", ("CollectingReporter",))


class UserScriptsMixin:
    def __init__(self) -> None:
        super().__init__()
        self._scripts = {}

    def load_all_user_scripts(self) -> None:
        try:
            self._load_all_user_scripts()
        except Exception:
            content = traceback.format_exc()
            logger.error(f"Error while loading user scripts: \n {content}")

    def _load_all_user_scripts(self) -> None:
        """Load all scripts from the `scripts` directory.

        Runs a callback of type `EventType.NAMESPACE_UPDATE`
        to inform clients about added objects in the namesapce.
        """
        self.forget_all_user_scripts()

        # load all scripts from the scripts directory
        current_path = pathlib.Path(__file__).parent.resolve()
        script_files = glob.glob(os.path.abspath(os.path.join(current_path, "../scripts/*.py")))

        # load all scripts from the user's script directory in the home directory
        user_script_dir = os.path.join(os.path.expanduser("~"), "bec", "scripts")
        if os.path.exists(user_script_dir):
            script_files.extend(glob.glob(os.path.abspath(os.path.join(user_script_dir, "*.py"))))

        # load scripts from the plugins
        plugins = importlib.metadata.entry_points(group="bec")
        for plugin in plugins:
            if plugin.name == "plugin_bec":
                plugin = plugin.load()
                plugin_scripts_dir = os.path.join(plugin.__path__[0], "scripts")
                if os.path.exists(plugin_scripts_dir):
                    script_files.extend(
                        glob.glob(os.path.abspath(os.path.join(plugin_scripts_dir, "*.py")))
                    )

        for file in script_files:
            self.load_user_script(file)
        builtins.__dict__.update({name: v["cls"] for name, v in self._scripts.items()})

    def forget_all_user_scripts(self) -> None:
        """unload / remove loaded user scripts from builtins. Files will remain untouched.

        Runs a callback of type `EventType.NAMESPACE_UPDATE`
        to inform clients about removing objects from the namesapce.

        """
        for name, obj in self._scripts.items():
            builtins.__dict__.pop(name)
            self.callbacks.run(
                EventType.NAMESPACE_UPDATE, action="remove", ns_objects={name: obj["cls"]}
            )
        self._scripts.clear()

    def load_user_script(self, file: str) -> None:
        """load a user script file and import all its definitions

        Args:
            file (str): Full path to the script file.
        """
        # TODO: re-enable linter
        # self._run_linter_on_file(file)
        module_members = self._load_script_module(file)
        for name, cls in module_members:
            if not callable(cls):
                continue
            # ignore imported classes
            if cls.__module__ != "scripts":
                continue
            if name in self._scripts:
                logger.warning(f"Conflicting definitions for {name}.")
            logger.info(f"Importing {name}")
            self._scripts[name] = {"cls": cls, "fname": file}
            self.callbacks.run(EventType.NAMESPACE_UPDATE, action="add", ns_objects={name: cls})

    def forget_user_script(self, name: str) -> None:
        """unload / remove a user scripts. The file will remain on disk."""
        if name not in self._scripts:
            logger.error(f"{name} is not a known user script.")
            return
        self.callbacks.run(
            EventType.NAMESPACE_UPDATE,
            action="remove",
            ns_objects={name: self._scripts[name]["cls"]},
        )
        builtins.__dict__.pop(name)
        self._scripts.pop(name)

    def list_user_scripts(self):
        """display all currently loaded user functions"""
        console = Console()
        table = Table(title="User scripts")
        table.add_column("Name", justify="center")
        table.add_column("Location", justify="center", overflow="fold")

        for name, content in self._scripts.items():
            table.add_row(name, content.get("fname"))
        console.print(table)

    def _load_script_module(self, file) -> list:
        module_spec = importlib.util.spec_from_file_location("scripts", file)
        plugin_module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(plugin_module)
        module_members = inspect.getmembers(plugin_module)
        return module_members

    def _run_linter_on_file(self, file) -> None:
        accepted_vars = ",".join([key for key in builtins.__dict__ if not key.startswith("_")])
        reporter = CollectingReporter()
        print(f"{accepted_vars}")
        pylint.lint.Run(
            [file, "--errors-only", f"--additional-builtins={accepted_vars}"],
            exit=False,
            reporter=reporter,
        )
        if not reporter.messages:
            return

        def _format_pylint_output(msg: Message):
            return f"Line {msg.line}, column {msg.column}: {msg.msg}."

        for msg in reporter.messages:
            logger.error(
                f"During the import of {file}, the following error was detected: \n{_format_pylint_output(msg)}.\nThe script was imported but may not work as expected."
            )
