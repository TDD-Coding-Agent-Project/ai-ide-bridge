import asyncio
import json
import sys

import websockets

TASK_ID = sys.argv[1]

async def main():
    uri = f"ws://127.0.0.1:27182/v1/tasks/{TASK_ID}/events"
    async with websockets.connect(uri) as ws:
        while True:
            msg = await ws.recv()
            print(json.dumps(json.loads(msg), ensure_ascii=False, indent=2))

asyncio.run(main())