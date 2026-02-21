import asyncio
import sys

sys.path.insert(0, ".")
from core.database import expire_old_streaks, init_db

init_db()
print(asyncio.run(expire_old_streaks()))
