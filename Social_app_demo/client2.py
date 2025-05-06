import asyncio
import json
import websockets

send_lock = asyncio.Lock()

PROFILE = {
    "user_id": "u2",
    "name": "Bob",
    "lat": 37.74,
    "lon": -122.41,
    "interests": ["tennis", "reading", "talktive"]
}
SERVER = "ws://127.0.0.1:8000/ws/match/"

# track group membership locally
room_members = {}

async def send_loop(ws):
    loop = asyncio.get_running_loop()
    while True:
        cmd = await loop.run_in_executor(None, input, "> ")
        if cmd.startswith("/broadcast"):
            _, text = cmd.split(" ", 1)
            max_km_str = await loop.run_in_executor(None, input, "Max distance (km)? ")
            max_group_str = await loop.run_in_executor(None, input, "Max group size? ")
            try:
                max_km = float(max_km_str)
            except ValueError:
                print("Invalid distance; using default 5 km")
                max_km = 5.0
            try:
                max_group = int(max_group_str)
            except ValueError:
                print("Invalid group size; using default 10")
                max_group = 10
            payload = {
                "action": "broadcast",
                "data": {
                    "user_id": PROFILE["user_id"],
                    "request_text": text,
                    "max_km": max_km,
                    "threshold": 0.1,
                    "max_group": max_group
                }
            }
        elif cmd.startswith("/msg"):
            _, rest = cmd.split(" ", 1)
            room, msg_text = rest.split(" ", 1)
            payload = {
                "action": "chat",
                "data": {
                    "room": room,
                    "sender": PROFILE["user_id"],
                    "message": msg_text
                }
            }


        elif cmd.startswith("/leave"):
            _, room = cmd.split(" ", 1)
            if room not in room_members or PROFILE["user_id"] not in room_members[room]:
                print(f"❌ You are not in room {room}")
                continue
            payload = {
                "action": "leave",
                "data": {
                    "room": room,
                    "user_id": PROFILE["user_id"]
                }
            }
            # Remove from local tracking
            room_members[room].remove(PROFILE["user_id"])
            if not room_members[room]:  # If room is empty, remove it
                del room_members[room]


                
        else:
            continue
        async with send_lock:
            await ws.send(json.dumps(payload))

async def recv_loop(ws):
    loop = asyncio.get_running_loop()
    async for message in ws:
        msg = json.loads(message)
        act = msg.get("action")
        if act == "registered":
            print("✅ Registration acknowledged")
        elif act == "broadcast_closed":
            print(f"⚡ Invites closed: sent {msg.get('invited_count')} of {msg.get('max_group')} requested")
        elif act == "invite":
            print(f"\n📨 Invite from {msg['from']}: {msg['text']} (score {msg.get('score',0):.2f})")
            print(f"   → Distance: {msg.get('distance',0):.2f} km; Interests: {', '.join(msg.get('interests', []))}")
            resp = await loop.run_in_executor(None, input, " Accept? (y/n) ")
            if resp.lower().startswith("y"):
                await ws.send(json.dumps({
                    "action": "accept",
                    "data": {
                        "request_id": msg["request_id"],
                        "from": msg["from"],
                        "acceptor": PROFILE["user_id"],
                        "members": [PROFILE["user_id"], msg["from"]]
                    }
                }))
        elif act == "group_update":
            room = msg.get("room")
            # accumulate members locally
            members_set = room_members.setdefault(room, set())
            members_set.update(msg.get("members", []))
            # display sorted list
            members_list = sorted(members_set)
            print(f"\n👥 Group {room} → members {members_list}")
        elif act == "chat":
            print(f"[{msg['sender']}] {msg['message']}")
        else:
            print("🔀 Unknown message:", msg)

async def main():
    async with websockets.connect(SERVER) as ws:
        print("🔌 Connected to server")
        await ws.send(json.dumps({"action": "register", "data": PROFILE}))
        await asyncio.gather(
            send_loop(ws),
            recv_loop(ws)
        )

if __name__ == "__main__":
    asyncio.run(main())