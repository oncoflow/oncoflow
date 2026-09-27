import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.domain.oncology.agents import Agents
import inspect

agents = Agents()
print("dir(Agents):", dir(Agents))
print("list keys:", list(agents.list.keys()))

for name in dir(Agents):
    attr = getattr(Agents, name)
    if inspect.isclass(attr):
        print(f"Class: {name}, Name: {attr.__name__}, bases: {attr.__bases__}")
