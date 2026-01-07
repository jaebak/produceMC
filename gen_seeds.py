#!/usr/bin/env python3
import sys, secrets
n = int(sys.argv[1])
for _ in range(n): print(secrets.randbelow(2_147_483_646) + 1)
