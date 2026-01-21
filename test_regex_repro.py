import re
import json

log_line_content = 'Objective Complete: Deliver 150/150 SCU of Processed Food to HDPC-Cassillo \n <2026-01-21T01:18:33.804Z> : "'

regex_pattern = r"(Deliver|Pickup|Dropoff|Transport|Collect)\s+(\d+)(?:[/\s]+(\d+))?\s+SCU\s+(?:of|de)?\s*([A-Za-z0-9\s\(\)\-\.]+?)\s+(?:to|at|for|towards|para|em|de)\s+([A-Za-z0-9\s\(\)\-\.]+?)(?::|\"|\[|<|\n)"

match = re.search(regex_pattern, log_line_content)

if match:
    print("Match found!")
    print(f"Action: '{match.group(1)}'")
    print(f"Amount 1: '{match.group(2)}'")
    print(f"Amount 2: '{match.group(3)}'")
    print(f"Material: '{match.group(4)}'")
    print(f"Location: '{match.group(5)}'")
else:
    print("No match found.")
