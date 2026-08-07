"""Unit tests run against the in-process backends, never the network.

A token on the developer's machine would otherwise rewire every test to the
real service — slower, non-deterministic, and a different system than the one
the assertions describe. Integration against the real backend is a separate
suite.
"""

import os

os.environ["ELEVATE_FORCE_MOCK"] = "1"
