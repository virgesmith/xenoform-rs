import inspect
import logging
import re
import subprocess
from collections import defaultdict
from collections.abc import Callable
from operator import add
from typing import Any

from itrx import Itr

from xenoform_rs.extension_types import translate_type

logger = logging.getLogger(__name__)


def _splitargs(signature: str) -> tuple[str, ...]:
    """
    Need to deal with commas in types, e.g. dict[str, int]. Replace the non-nested commas ONLY with $ then split
    """
    # extract the part in between ()
    base = Itr(signature).skip_while(lambda c: c != "(").skip(1).take_while(lambda c: c != ")")
    # mark the level of [] nesting
    mark = base.copy().map_dict(defaultdict(int, {"[": 1, "]": -1})).accumulate(add)
    # combine, replace level-0 commas with $, split and strip
    return (
        Itr(base.zip(mark).map(lambda cn: "$" if cn == (",", 0) else cn[0]).fold("", add).split("$"))
        .map(str.strip)
        .collect()
    )


def get_function_scope(func: Callable[..., Any]) -> tuple[str, ...]:
    """
    Returns the snake-case name of the class for class and instance methods
    NB Does not work for static methods
    """
    return tuple(
        re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()
        for s in func.__qualname__.split(".")[:-1]  # ty:ignore[unresolved-attribute]
        if s != "<locals>"
    )


def _translate_value(value: Any) -> str:
    translations = {"False": "false", "True": "true"}
    return translations.get(str(value), str(value))


def translate_function_signature(func: Callable[..., Any], *, py: bool) -> tuple[str, list[str]]:
    """
    Map python signature to rust equivalent
    If py=True, arguments will prepended with the python context `py: Python<'py>`
    """
    arg_spec = inspect.getfullargspec(func)

    # python context as first arg, if requested
    arg_defs = ["py: Python<'py>"] if py else []
    arg_annotations = []

    # parse signature - get defaults and positions of pos-only and kw-only
    sig = inspect.signature(func)
    raw_sig = _splitargs(str(sig))
    pos_only = raw_sig.index("/") if "/" in raw_sig else None
    kw_only = raw_sig.index("*") if "*" in raw_sig else None
    defaults = {k: v.default for k, v in sig.parameters.items() if v.default is not inspect.Parameter.empty}

    ret: str | None = None
    for var_name, type_ in arg_spec.annotations.items():
        rusttype = translate_type(type_)
        # can't use self to refer to a python object in rust
        if var_name == "return":
            ret = str(rusttype)
        else:
            if arg_spec.varargs == var_name:
                arg_def = f"{var_name}: &Bound<'_, PyTuple>"
                arg_annotation = f"*{var_name}"
            elif arg_spec.varkw == var_name:
                arg_def = f"{var_name}: Option<&Bound<'_, PyDict>>"
                arg_annotation = f"**{var_name}"
            else:
                arg_def = f"{var_name}: {rusttype}"
                arg_annotation = f"{var_name}"
            if var_name in defaults:
                # arg_def += f"={_translate_value(defaults[var_name])}"
                arg_annotation += f"={_translate_value(defaults[var_name])}"
            if "tuple_placeholder" in arg_def:
                arg_def = _replace_tuple_angle_brackets(arg_def)
            arg_defs.append(arg_def)
            # dont create an annotation for var(kw)args
            # if arg_spec.varargs != var_name and arg_spec.varkw != var_name:
            arg_annotations.append(arg_annotation)
    if pos_only is not None:
        arg_annotations.insert(pos_only, "/")
    if kw_only is not None:
        arg_annotations.insert(kw_only, "*")

    return f"({', '.join(arg_defs)})" + (f" -> PyResult<{ret}>" if ret else ""), arg_annotations


def rustfmt(code: str) -> str:
    """Use rustfmt to prettify code"""
    try:
        result = subprocess.run(["rustfmt"], input=code, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.warning(f"rustfmt failed: {e}. lib.rs will be unformatted")
        return code
    if result.returncode != 0:
        logger.warning(f"rustfmt failed with stderr: {result.stderr}. lib.rs will be unformatted")
        return code
    return result.stdout


def rust_dependency(*args: str, **kwargs: Any) -> str:
    """Make a valid dependency entry for Cargo.toml"""

    match len(args), len(kwargs):
        case 2, 0:
            return f'{args[0]} = "{args[1]}"'
        case 1, n if n > 0:
            params = []
            for k, v in kwargs.items():
                params.append(f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}")
            return f"{args[0]} = {{ {', '.join(params)} }}"
        case _:
            raise ValueError("rust_dependency requires a name and either a version string or a keyword parameters")


def _replace_tuple_angle_brackets(arg_def: str) -> str:

    arg_def = arg_def.replace("tuple_placeholder", "")
    i = 0
    result = []
    option_depth = 0  # how many Option<...> levels we're inside

    while i < len(arg_def):
        # Check if we're at the start of "Option<"
        if arg_def[i : i + 7] == "Option<":
            result.append("Option<")
            i += 6
            option_depth += 1

        elif arg_def[i] == "<":
            result.append("<" if option_depth > 0 else "(")
            # i += 1

        elif arg_def[i] == ">":
            if option_depth > 0:
                option_depth -= 1
                result.append(">")
            else:
                result.append(")")
            # i += 1

        else:
            result.append(arg_def[i])
        i += 1

    return "".join(result)
