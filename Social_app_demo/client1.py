import asyncio
import json
import websockets
import os.path
import pickle

send_lock = asyncio.Lock()

# Profile storage
PROFILE_FILE = "client1_profile.pkl"

# Default profile (used only if no saved profile exists)
DEFAULT_PROFILE = {
    "user_id": "u1",
    "name": "Alice",
    "lat": 37.74,
    "lon": -122.41,
    "interests": ["tennis", "reading"],
    "hometown": "San Francisco",
    "major": "Computer Science"
}

SERVER = "ws://127.0.0.1:8000/ws/match/"

# track group membership locally
room_members = {}

# Global profile variable
PROFILE = None

def load_profile():
    """Load user profile from file or create default"""
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading profile: {e}")
            return setup_profile(DEFAULT_PROFILE)
    else:
        return setup_profile(DEFAULT_PROFILE)

def save_profile(profile):
    """Save profile to file"""
    try:
        with open(PROFILE_FILE, 'wb') as f:
            pickle.dump(profile, f)
        print("✅ Profile saved")
    except Exception as e:
        print(f"❌ Error saving profile: {e}")

def setup_profile(existing_profile=None):
    """Interactive profile setup"""
    profile = {} if existing_profile is None else existing_profile.copy()
    
    print("\n📝 Profile Setup")
    
    # User ID
    profile["user_id"] = input(f"User ID [{profile.get('user_id', 'u1')}]: ") or profile.get("user_id", "u1")
    
    # Name
    profile["name"] = input(f"Name [{profile.get('name', '')}]: ") or profile.get("name", "")
    
    # Hometown
    profile["hometown"] = input(f"Hometown [{profile.get('hometown', '')}]: ") or profile.get("hometown", "")
    
    # Major
    profile["major"] = input(f"Major/Field of Study [{profile.get('major', '')}]: ") or profile.get("major", "")
    
    # Location
    try:
        lat_input = input(f"Latitude [{profile.get('lat', 37.74)}]: ")
        profile["lat"] = float(lat_input) if lat_input else profile.get("lat", 37.74)
        
        lon_input = input(f"Longitude [{profile.get('lon', -122.41)}]: ")
        profile["lon"] = float(lon_input) if lon_input else profile.get("lon", -122.41)
    except ValueError:
        print("Invalid coordinates - using default values")
        profile["lat"] = profile.get("lat", 37.74)
        profile["lon"] = profile.get("lon", -122.41)
    
    # Interests
    interests_str = ', '.join(profile.get("interests", []))
    new_interests = input(f"Interests (comma-separated) [{interests_str}]: ")
    
    if new_interests:
        profile["interests"] = [i.strip() for i in new_interests.split(',')]
    elif "interests" not in profile:
        profile["interests"] = []
    
    save_profile(profile)
    return profile

async def send_loop(ws, profile):
    global PROFILE
    loop = asyncio.get_running_loop()
    while True:
        cmd = await loop.run_in_executor(None, input, "> ")
        
        if cmd.startswith("/profile"):
            # Update profile
            PROFILE = setup_profile(PROFILE)
            
            # Re-register with server
            async with send_lock:
                await ws.send(json.dumps({
                    "action": "register", 
                    "data": PROFILE
                }))
            continue
            
        elif cmd.startswith("/broadcast"):
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
        elif cmd == "/help":
            print("\n📚 Available Commands:")
            print("  /profile          - Update your user profile")
            print("  /broadcast <text> - Broadcast a message to nearby users")
            print("  /msg <room> <msg> - Send message to a room")
            print("  /leave <room>     - Leave a room")
            print("  /help             - Show this help message")
            continue
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
    global PROFILE
    PROFILE = load_profile()
    
    print("\n🌟 Welcome to the Social Match App!")
    print(f"Logged in as: {PROFILE['name']} ({PROFILE['user_id']})")
    print('Type "/help" for available commands')
    
    async with websockets.connect(SERVER) as ws:
        print("🔌 Connected to server")
        await ws.send(json.dumps({"action": "register", "data": PROFILE}))
        await asyncio.gather(
            send_loop(ws, PROFILE),
            recv_loop(ws)
        )

if __name__ == "__main__":
    asyncio.run(main())