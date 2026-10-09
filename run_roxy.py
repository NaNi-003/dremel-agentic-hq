import roxy_workflow
import sys
import traceback

def main():
    try:
        result = roxy_workflow.coordinate_latest(publish=True)
        print("Workflow Result:")
        print(result)
        if result.get("status") == "published":
            print(f"Success! Dashboard published to: {result.get('site_url')}")
        else:
            print(f"Finished with status: {result.get('status')}")
    except Exception as e:
        print(f"Error running workflow: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
