"""
This module contains functions to serialize and deserialize function signatures.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import operator
import sys
import types
from collections.abc import Callable
from typing import Any, Literal, Union

import numpy as np

from bec_lib.device import DeviceBase
from bec_lib.scan_items import ScanItem


def serialize_dtype(dtype: type) -> Any:
    """
    Convert a dtype to a string.

    Args:
        dtype (type): Data type

    Returns:
        str: String representation of the data type
    """
    if hasattr(dtype, "__name__"):
        name = dtype.__name__
        # changed in python 3.10. Refactor this when we upgrade
        if name not in ["Literal", "Union"]:
            return name
    if hasattr(dtype, "__module__"):
        if dtype.__module__ == "typing":
            if dtype.__class__.__name__ == "_UnionGenericAlias":
                return " | ".join([serialize_dtype(x) for x in dtype.__args__])
            if dtype.__class__.__name__ == "_LiteralGenericAlias":
                return {"Literal": dtype.__args__}
        elif dtype.__module__ == "types":
            if dtype.__class__ == types.UnionType:
                return " | ".join([serialize_dtype(x) for x in dtype.__args__])
    if isinstance(dtype, str):
        if sys.version_info[:3] >= (3, 10):
            return dtype
        # remove this when we upgrade to python 3.10
        ####
        if dtype.startswith("typing.Literal["):
            return {"Literal": ast.literal_eval(dtype[15:-1])}
        if dtype.startswith("Literal["):
            return {"Literal": ast.literal_eval(dtype[8:-1])}
        return dtype
        ####
    raise ValueError(f"Unknown dtype {dtype}")


def deserialize_dtype(dtype: Any) -> type:
    """
    Convert a serialized dtype to a type.

    Args:
        dtype (str): String representation of the data type

    Returns:
        type: Data type
    """
    if dtype == "_empty":
        # pylint: disable=protected-access
        return inspect._empty
    if isinstance(dtype, dict):
        if "Literal" in dtype:
            # remove this when we upgrade to python 3.11

            #### remove this section
            literal = Literal[str(dtype)]
            literal.__args__ = dtype["Literal"]
            return literal
            #### remove this section

            #### add this section when we upgrade to python 3.11
            # return Literal[*dtype["Literal"]]
            #### add this section when we upgrade to python 3.11

        raise ValueError(f"Unknown dtype {dtype}")
    if isinstance(dtype, str) and "|" in dtype:
        entries = [deserialize_dtype(x.strip()) for x in dtype.split("|")]
        return Union[tuple(entries)]

    if dtype == "NoneType":
        return None
    builtin_type = builtins.__dict__.get(dtype)
    if builtin_type:
        return builtin_type
    if dtype == "DeviceBase":
        return DeviceBase
    if dtype == "ScanItem":
        return ScanItem
    if hasattr(np, dtype):
        return getattr(np, dtype)
    return None


def signature_to_dict(func: Callable, include_class_obj=False) -> list[dict]:
    """
    Convert a function signature to a dictionary.
    The dictionary can be used to reconstruct the signature using dict_to_signature.

    Args:
        func (Callable): Function to be converted

    Returns:
        list[dict]: List of dictionaries representing the function signature
    """
    out = []
    params = inspect.signature(func).parameters
    for param_name, param in params.items():
        if not include_class_obj and param_name == "self" or param_name == "cls":
            continue
        # pylint: disable=protected-access
        out.append(
            {
                "name": param_name,
                "kind": param.kind.name,
                "default": param.default if param.default != inspect._empty else "_empty",
                "annotation": serialize_dtype(param.annotation),
            }
        )
    return out


def dict_to_signature(params: list[dict]) -> inspect.Signature:
    """
    Convert a dictionary representation of a function signature to a signature object.

    Args:
        params (list[dict]): List of dictionaries representing the function signature

    Returns:
        inspect.Signature: Signature object
    """
    out = []
    for param in params:
        # pylint: disable=protected-access
        out.append(
            inspect.Parameter(
                name=param["name"],
                kind=getattr(inspect.Parameter, param["kind"]),
                default=param["default"] if param["default"] != "_empty" else inspect._empty,
                annotation=deserialize_dtype(param["annotation"]),
            )
        )
    return inspect.Signature(out)
