import time
import json
from mcctp import SyncMCCTPClient, Actions

def inspect_state(state):
    # If the state is empty or just a timestamp, skip it
    if not state or len(state) <= 2:
        return

    print("-" * 40)
    print("NEW PACKET RECEIVED")
    # This prints every single attribute/key found in the telemetry
    print(json.dumps(state, indent=4))
    
    # Example of specific attribute access if you want to see them clearly:
    p_state = state.get('playerState', {})
    if p_state:
        print(f"--- Summary ---")
        print(f"Health: {p_state.get('health')}")
        print(f"Position: {p_state.get('x')}, {p_state.get('y')}, {p_state.get('z')}")

# Execution block
try:
    with SyncMCCTPClient("localhost", 8765) as client:
        print("Connected! Listening for attributes...")
        
        # Attach the inspector function
        client.on_state(inspect_state)
        
        # Keep the script alive so the background thread can print
        while True:
            time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping inspector.")
except Exception as e:
    print(f"Error: {e}")