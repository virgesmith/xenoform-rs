from xenoform_rs import rust


@rust(imports=["pyo3::types::{PyList, PySlice}"])
def parse_slice(length: int, s: slice) -> list[int]:  # type: ignore[empty-body]
    """
    let idx = s.indices(length as isize)?;

    let mut indices: Vec<i32> = Vec::with_capacity(idx.slicelength);

    for i in 0..idx.slicelength {
        indices.push((idx.start + i as isize * idx.step) as i32);
    }

    Ok(indices)
    """


# @rust()
# def slice_shape(a: npt.NDArray[np.float64], *indices: int | slice | EllipsisType) -> list[int]:
#     """
#     py::array slice = a[indices];
#     return std::vector<int>(slice.shape(), slice.shape() + slice.ndim());
#     """


# @rust()
# def explicit_ellipsis(a: int | slice | EllipsisType) -> str:
#     """
#     if (std::get_if<int>(&a)) {
#         return "int";
#     } else if (std::get_if<py::slice>(&a)) {
#         return "slice";
#     } else if (std::get_if<py::ellipsis>(&a)) {
#         return "ellipsis";
#     }
#     throw py::type_error("invalid arg type");
#     """


def test_slice() -> None:
    assert parse_slice(10, slice(1, None, 2)) == [1, 3, 5, 7, 9]
    assert parse_slice(10, slice(None, None, -2)) == [9, 7, 5, 3, 1]
    assert parse_slice(10, slice(5, 1, -1)) == [5, 4, 3, 2]
    assert parse_slice(10, slice(None, 2, -2)) == [9, 7, 5, 3]


# def test_ellipsis() -> None:
#     assert slice_shape(np.ones((2, 3, 5, 7)), 1, ..., 2) == [3, 5]
#     assert slice_shape(np.ones((2, 3, 5, 7)), 1, ..., slice(2, 3)) == [3, 5, 1]
#     assert slice_shape(np.ones((2, 3, 5, 7)), ..., 1, slice(2, 4)) == [2, 3, 2]
#     assert slice_shape(np.ones((2, 3, 5, 7)), 1, 2, ...) == [5, 7]
#     assert slice_shape(np.ones((2, 3, 5, 7)), 1, 2, 3, slice(4, None, 2)) == [2]

#     assert explicit_ellipsis(1) == "int"
#     assert explicit_ellipsis(slice(1)) == "slice"
#     assert explicit_ellipsis(...) == "ellipsis"
#     with pytest.raises(TypeError):
#         explicit_ellipsis("abc")


if __name__ == "__main__":
    test_slice()
    # test_ellipsis()
