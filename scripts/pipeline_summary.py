import json
from datetime import datetime

def main():
    print("## Pipeline Run Summary")
    print(f"- Date: {datetime.utcnow().isoformat()}")

    try:
        with open("logs/pipeline_runs.json") as f:
            runs = json.load(f)

        if isinstance(runs, list) and runs:
            r = runs[-1]
            print(f"- Posts succeeded: {r.get('posts_succeeded', 0)}/{r.get('posts_attempted', 0)}")
        else:
            print("- Result: No run data")

    except Exception as e:
        print(f"- Error reading summary: {e}")

if __name__ == "__main__":
    main()
