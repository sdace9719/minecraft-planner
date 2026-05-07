import requests
import json
import time

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def send_action(action_type, **kwargs):
    config = load_config()
    url = f"http://localhost:{config['api_port']}/action"
    
    payload = {"type": action_type, **kwargs}
    print(f"Sending action: {payload}")
    
    try:
        response = requests.post(url, json=payload, timeout=300) # Long timeout for pathfinding
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    print("Python AI Connector starting...")
    
    # Action: Walk to 50, 50
    print("Instructing bot to walk to (60, -90)...")
    result = send_action("pathfind", x=60, z=-90)
    print(f"Result: {result}")

    # Action: Get Status
    print("Fetching bot status...")
    status = send_action("status")
    print(f"Bot Status: {status}")

if __name__ == "__main__":
    main()
