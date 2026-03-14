from typing import Annotated

from xenoform_rs import rust
from xenoform_rs.extension_types import translate_type


def test_translate_compound_types() -> None:
    # assert str(translate_type(int | float)) == "std::variant<int, double>"
    assert str(translate_type(int | None)) == "Option<i32>", translate_type(int | None)  # type: ignore[arg-type]
    assert str(translate_type(Annotated[int | float, "f64"])) == "f64"  # type: ignore[arg-type]
    assert str(translate_type(Annotated[int | None, "&Bound<'_, PyAny>"])) == "&Bound<'_, PyAny>"  # type: ignore[arg-type]
    # assert str(translate_type(int | float | None)) == "std::optional<std::variant<int, double>>"


# @rust()
# def union_type(x: Annotated[int | str, "const std::variant<int, std::string>&"]) -> str:
#     """
#     return std::holds_alternative<int>(x) ? std::to_string(std::get<int>(x)) : std::get<std::string>(x);
#     """


# def test_union_type() -> None:
#     assert union_type(1) == "1"
#     assert union_type("42") == "42"


@rust(py=False)
def optional_type(x: int | None) -> int:  # type: ignore[empty-body]
    """
    Ok(x.unwrap_or(42))
    """


def test_optional_type() -> None:
    assert optional_type(1) == 1
    assert optional_type(None) == 42


# @rust()
# def compound_type(x: int | float | None) -> str:
#     """
#     if (x) {
#         if (std::holds_alternative<int>(x.value())) {
#             return "int";
#         }
#         return "float";
#     }
#     return "empty";
#     """


# def test_compound_type() -> None:
#     assert compound_type(1) == "int"
#     assert compound_type(1.0) == "float"
#     assert compound_type(None) == "empty"


if __name__ == "__main__":
    test_translate_compound_types()
    # test_union_type()
    test_optional_type()
    # test_compound_type()
