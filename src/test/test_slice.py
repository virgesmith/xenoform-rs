from types import EllipsisType
from typing import Annotated

import pytest

from xenoform_rs import rust


@rust(imports=["pyo3::types::PySlice"])
def parse_slice(length: int, s: slice) -> list[int]:  # type: ignore[empty-body]
    """
    let idx = s.indices(length as isize)?;

    let mut indices: Vec<i32> = Vec::with_capacity(idx.slicelength);

    for i in 0..idx.slicelength {
        indices.push((idx.start + i as isize * idx.step) as i32);
    }

    Ok(indices)
    """


# this is likely to be far more tricky in rust...
# @rust()
# def slice_shape(a: npt.NDArray[np.float64], *indices: int | slice | EllipsisType) -> list[int]:
#     """
#     py::array slice = a[indices];
#     return std::vector<int>(slice.shape(), slice.shape() + slice.ndim());
#     """


@rust(
    imports=[
        "pyo3::types::{PyInt, PyEllipsis, PyString}",
        "pyo3::exceptions::PyTypeError",
        "pyo3::type_object::PyTypeInfo",
    ]
)
def explicit_ellipsis(
    a: Annotated[int | slice | EllipsisType, "Bound<'py, PyAny>"],
) -> str:  # ty:ignore[empty-body]
    """
    // Ok(a.get_type().name()?)
    let pytype = a.get_type().name()?.extract::<String>()?;
    match pytype.as_str() {
        "int" | "slice" | "ellipsis" => Ok(pytype),
        _ => Err(PyTypeError::new_err("invalid arg type"))
    }
    """


def test_slice() -> None:
    assert parse_slice(10, slice(1, None, 2)) == [1, 3, 5, 7, 9]
    assert parse_slice(10, slice(None, None, -2)) == [9, 7, 5, 3, 1]
    assert parse_slice(10, slice(5, 1, -1)) == [5, 4, 3, 2]
    assert parse_slice(10, slice(None, 2, -2)) == [9, 7, 5, 3]


def test_ellipsis() -> None:
    #     assert slice_shape(np.ones((2, 3, 5, 7)), 1, ..., 2) == [3, 5]
    #     assert slice_shape(np.ones((2, 3, 5, 7)), 1, ..., slice(2, 3)) == [3, 5, 1]
    #     assert slice_shape(np.ones((2, 3, 5, 7)), ..., 1, slice(2, 4)) == [2, 3, 2]
    #     assert slice_shape(np.ones((2, 3, 5, 7)), 1, 2, ...) == [5, 7]
    #     assert slice_shape(np.ones((2, 3, 5, 7)), 1, 2, 3, slice(4, None, 2)) == [2]

    assert explicit_ellipsis(1) == "int"
    assert explicit_ellipsis(slice(1)) == "slice"
    assert explicit_ellipsis(...) == "ellipsis"
    with pytest.raises(TypeError):
        explicit_ellipsis("abc")  # ty:ignore[invalid-argument-type]


if __name__ == "__main__":
    test_slice()
    test_ellipsis()
