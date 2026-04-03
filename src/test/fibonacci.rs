pub struct Fib {
  ab: (u64, u64)
}

impl Fib {
  fn new() -> Self {
    Fib{ ab: (0, 1) }
  }
}

impl Iterator for Fib {
  type Item = u64;
  fn next(&mut self) -> Option<Self::Item> {
    let ret = self.ab.0;
    self.ab = (self.ab.1, self.ab.0 + self.ab.1);
    Some(ret)
  }
}

pub fn fib(n: u64) -> u64 {
  let mut fib = Fib::new();
  fib.nth(n as usize).unwrap()
}
