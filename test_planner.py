import json
from dotenv import load_dotenv

from agent.planner import create_monitoring_plan

load_dotenv()

result = create_monitoring_plan(
    r"D:\Nagios_agent"
)

print(json.dumps(result, indent=2))
