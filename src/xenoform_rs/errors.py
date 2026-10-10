from collections.abc import Sequence
from dataclasses import dataclass


class XenoformRsError(RuntimeError):
    pass


class AnnotationError(XenoformRsError):
    pass


@dataclass(frozen=True)
class RustDiagnostic:
    """A single rustc diagnostic, as reported by `cargo build --message-format=json`"""

    level: str
    code: str | None
    message: str
    rendered: str
    file: str | None = None
    line: int | None = None
    has_suggestion: bool = False


class CompilationError(XenoformRsError):
    def __init__(self, message: str, diagnostics: Sequence[RustDiagnostic] = ()) -> None:
        super().__init__(message)
        self.diagnostics = list(diagnostics)


class RustConfigError(XenoformRsError):
    pass


class RustTypeError(XenoformRsError):
    pass


class RustModuleError(XenoformRsError):
    pass
