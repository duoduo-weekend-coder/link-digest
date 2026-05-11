from __future__ import annotations

import json

import pytest
import httpx
from unittest.mock import patch

from app import app, _sse
