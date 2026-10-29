/*
built by the build_libs fixture in conftest.py:
cc -fPIC -c test_lib.c -o test_lib.o
ar rcs libstatic.a test_lib.o
cc -shared test_lib.o -o libshared.so
*/
#include <stdint.h>

uint64_t fibonacci(uint64_t n) { return n < 2 ? n : fibonacci(n - 1) + fibonacci(n - 2); }

uint64_t lucas(uint64_t n) { return n < 2 ? 2 - n : lucas(n - 1) + lucas(n - 2); }
