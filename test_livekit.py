import asyncio
import sys
from livekit import rtc

async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 test_livekit.py <livekit_url> <token>")
        sys.exit(1)
        
    url = sys.argv[1]
    token = sys.argv[2]
    
    print(f"Connecting to: {url}")
    print(f"Token (first 20 chars): {token[:20]}...")
    
    room = rtc.Room()
    try:
        await room.connect(url, token)
        print("SUCCESS! Connected to LiveKit Room!")
        await room.disconnect()
    except Exception as e:
        print("\n--- CONNECTION ERROR DETAILS ---")
        import traceback
        traceback.print_exc()
        print("---------------------------------")

if __name__ == "__main__":
    asyncio.run(main())
