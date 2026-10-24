"""Tools for legacy galgame / visual-novel remastering research.

The package is deliberately split into three independent pieces:

* :mod:`vnremaster.pac` / :mod:`vnremaster.deflate` - archive analysis and
  exact-size stream replacement;
* :mod:`vnremaster.glyph` / :mod:`vnremaster.fontcmap` - CJK glyph mapping and
  font-coverage audits;
* :mod:`vnremaster.compare` - reproducible image A/B measurements.

No game assets, translations, or proprietary data are bundled.
"""

__version__ = "0.1.0"

from .compare import Metrics, compare_images  # noqa: F401
from .deflate import ExactSizeError, build_exact_size, compress_to_exact_size  # noqa: F401
from .glyph import GlyphCodec, GlyphPlan, load_map, plan_map  # noqa: F401
from .pac import (  # noqa: F401
    PacArchive,
    PacDiff,
    PacFormatError,
    PacStats,
    RepackError,
)

__all__ = [
    "ExactSizeError",
    "GlyphCodec",
    "GlyphPlan",
    "Metrics",
    "PacArchive",
    "PacDiff",
    "PacFormatError",
    "PacStats",
    "RepackError",
    "build_exact_size",
    "compare_images",
    "compress_to_exact_size",
    "load_map",
    "plan_map",
]
