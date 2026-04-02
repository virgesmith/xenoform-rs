from typing import Annotated

from xenoform_rs import rust

# Remember most python types are immutable, so they cannot be modified in-place
# numpy case is covered in test_numpy.py


@rust(py=False, imports=["pyo3::types::PyList"])
def modify_list(lst: Annotated[list[int], "Bound<'py, PyList>"]) -> None:
    """
    lst.append(0)?;
    lst.set_item(0, 5)?;
    Ok(())
    """


@rust(py=False, imports=["pyo3::types::PyDict"])
def modify_dict(d: Annotated[dict[int, int], "Bound<'py, PyDict>"]) -> None:
    """
    d.set_item(0, 4)?;
    d.set_item(1, 2)?;
    Ok(())
    """


@rust(py=False, imports=["pyo3::types::PySet"])
def modify_set(s: Annotated[set[int], "Bound<'py, PySet>"]) -> None:
    """
    s.add(0)?;
    s.add(1)?;
    Ok(())
    """


@rust(py=False, imports=["pyo3::types::PyByteArray"])
def modify_bytearray(b: bytearray) -> None:
    """
    if b.len() > 0 {
        unsafe {
            let raw = b.as_bytes_mut();
            raw[0] += 5;
        }
    }
    Ok(())
    """


def test_inplace_modification() -> None:
    lst = [1, 2, 3]
    modify_list(lst)
    assert lst == [5, 2, 3, 0]

    dct = {0: 0}
    modify_dict(dct)
    assert dct == {0: 4, 1: 2}

    st = {0}
    modify_set(st)
    assert st == {0, 1}

    b = bytearray(b"abcd")
    modify_bytearray(b)
    assert b[0] == ord("f")
    assert b[1] == ord("b")


if __name__ == "__main__":
    test_inplace_modification()
