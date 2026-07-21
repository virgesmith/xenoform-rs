"""Example of DP/string workload performance - python vs inline rust (issue #16 item 3)"""

import random
from time import perf_counter
from typing import Annotated

from xenoform_rs import rust

SEED = 19937
QUERY = "algorithm"
WORD_LEN_RANGE = (3, 12)
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def levenshtein_py(a: str, b: str) -> int:
    """Wagner-Fischer edit distance: O(len(a) * len(b)) time, O(min(len(a), len(b))) space via a rolling row"""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def levenshtein_distances_py(query: str, wordlist: list[str]) -> list[int]:
    """Edit distance from query to every word in wordlist"""
    return [levenshtein_py(query, w) for w in wordlist]


@rust(py=False, profile={"strip": "symbols"})
def levenshtein_distances_rust(query: Annotated[str, "&str"], wordlist: list[str]) -> list[int]:  # ty: ignore[empty-body]
    """
    let qb = query.as_bytes();
    Ok(wordlist
        .iter()
        .map(|w| {
            let wb = w.as_bytes();
            let (long, short) = if qb.len() >= wb.len() { (qb, wb) } else { (wb, qb) };
            let mut prev: Vec<usize> = (0..=short.len()).collect();
            for (i, &lc) in long.iter().enumerate() {
                let mut curr = vec![0usize; short.len() + 1];
                curr[0] = i + 1;
                for (j, &sc) in short.iter().enumerate() {
                    let cost = usize::from(lc != sc);
                    curr[j + 1] = (curr[j] + 1).min(prev[j + 1] + 1).min(prev[j] + cost);
                }
                prev = curr;
            }
            prev[short.len()] as i32
        })
        .collect())
    """


def main() -> None:
    """Run a performance comparison for varying wordlist sizes"""
    rng = random.Random(SEED)

    # exclude the one-off module import and compile-check cost from the timings
    levenshtein_distances_rust(QUERY, ["warmup"])

    print("N | py (ms) | rust (ms) | speedup")
    print("-:|--------:|----------:|-----------:")
    for n in [1000, 10000, 100000, 1000000]:
        wordlist = ["".join(rng.choices(LETTERS, k=rng.randint(*WORD_LEN_RANGE))) for _ in range(n)]

        start = perf_counter()
        py_result = levenshtein_distances_py(QUERY, wordlist)
        py_time = perf_counter() - start

        start = perf_counter()
        rust_result = levenshtein_distances_rust(QUERY, wordlist)
        # windows perf_counter() is inaccurate
        rust_time = (perf_counter() - start) or 1.0

        print(f"{n} | {py_time * 1000:.1f} | {rust_time * 1000:.1f} | {(py_time / rust_time - 1.0):.0%}")
        assert py_result == rust_result


if __name__ == "__main__":
    main()
