"""No defensive view: completing the business task is the agent's responsibility."""
import copy
from redcommerce_v3.binding_driver import execute_actions


def build_observation(world, instruction):
    return {"instruction": instruction, **copy.deepcopy(world)}
