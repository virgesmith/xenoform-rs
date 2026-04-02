class XenoformRsError(RuntimeError):
    pass


class AnnotationError(XenoformRsError):
    pass


class CompilationError(XenoformRsError):
    pass


class RustConfigError(XenoformRsError):
    pass


class RustTypeError(XenoformRsError):
    pass
