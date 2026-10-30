"""Manual LiveKit connectivity check. Pass a short-lived token; it is never printed."""
import asyncio
import sys
from livekit import rtc


async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 test_livekit.py <livekit_url> <short_lived_token>")
        raise SystemExit(2)

    url, token = sys.argv[1], sys.argv[2]
    room = rtc.Room()
    try:
        await room.connect(url, token)
        print("Connected to LiveKit room successfully.")
        await room.disconnect()
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
