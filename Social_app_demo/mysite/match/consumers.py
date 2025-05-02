import json
import math
import uuid
from channels.generic.websocket import AsyncJsonWebsocketConsumer

# in-memory profile store: { channel_name: profile_dict }
PROFILES = {}
# persistent mapping: { room_id: [user_id, ...] }
ROOM_MEMBERS = {}

def haversine(a, b):
    R = 6371
    φ1, φ2 = math.radians(a['lat']), math.radians(b['lat'])
    Δφ = math.radians(b['lat'] - a['lat'])
    Δλ = math.radians(b['lon'] - a['lon'])
    h = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return 2 * R * math.atan2(math.sqrt(h), math.sqrt(1 - h))

class MatchConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        print(f"[{self.channel_name}] CONNECT")
        await self.accept()

    async def disconnect(self, code):
        print(f"[{self.channel_name}] DISCONNECT")
        PROFILES.pop(self.channel_name, None)

    async def receive_json(self, content):
        action = content.get('action')
        print(f"[{self.channel_name}] RECV_JSON: {content}")

        if action == 'register':
            profile = content['data']
            PROFILES[self.channel_name] = profile
            user_id = profile['user_id']
            # re-join any rooms the user belongs to
            for room_id, members in ROOM_MEMBERS.items():
                if user_id in members:
                    await self.channel_layer.group_add(room_id, self.channel_name)
                    print(f"[{self.channel_name}] re-joined room {room_id}")
            await self.send_json({'action':'registered'})

        elif action == 'broadcast':
            await self.handle_broadcast(content['data'])

        elif action == 'accept':
            await self.handle_accept(content['data'])

        elif action == 'chat':
            await self.handle_chat(content['data'])

    async def handle_broadcast(self, data):
        me = PROFILES.get(self.channel_name)
        if not me:
            return

        text = data.get('request_text','').lower()
        if 'tennis' not in text:
            await self.send_json({
                'action':'broadcast_closed',
                'request_id': None,
                'invited_count':0,
                'max_group': data.get('max_group')
            })
            return

        max_km    = data.get('max_km',5.0)
        threshold = data.get('threshold',0.5)
        max_group = data.get('max_group')
        invited   = 0
        # generate a single room id for this broadcast
        room_id   = str(uuid.uuid4())
        # initialize member list with broadcaster
        ROOM_MEMBERS[room_id] = [me['user_id']]

        for ch_name, prof in PROFILES.items():
            if prof['user_id'] == me['user_id']:
                continue
            dist = haversine(me, prof)
            if dist > max_km:
                continue
            match = 'tennis' in prof.get('interests',[])
            score = 1.0 if match else 0.0
            if score < threshold:
                continue
            # add invitee to persistent map
            ROOM_MEMBERS[room_id].append(prof['user_id'])
            # send invite event
            await self.channel_layer.send(ch_name, {
                'type':'invite.message',
                'from': me['user_id'],
                'request_id': room_id,
                'text': data['request_text'],
                'score': score,
                'distance': round(dist,2),
                'interests': me.get('interests',[])
            })
            invited += 1
            if max_group is not None and invited >= max_group:
                break

        # notify broadcaster
        await self.send_json({
            'action':'broadcast_closed',
            'request_id': room_id,
            'invited_count': invited,
            'max_group': max_group
        })

    async def invite_message(self, event):
        await self.send_json({
            'action':'invite',
            'from':event['from'],
            'request_id':event['request_id'],
            'text':event['text'],
            'score':event['score'],
            'distance':event['distance'],
            'interests':event['interests']
        })

    async def handle_accept(self, data):
        room_id       = data['request_id']
        broadcaster   = data['from']
        acceptor      = data['acceptor']
        # ensure persistent list exists and append if new
        members = ROOM_MEMBERS.setdefault(room_id, [])
        for uid in (broadcaster, acceptor):
            if uid not in members:
                members.append(uid)
        # add acceptor's channel
        await self.channel_layer.group_add(room_id, self.channel_name)
        # add broadcaster channel if online
        for ch_name, prof in PROFILES.items():
            if prof['user_id'] == broadcaster:
                await self.channel_layer.group_add(room_id, ch_name)
                break
        # broadcast the complete member list
        await self.channel_layer.group_send(room_id, {
            'type':'group.message',
            'room':room_id,
            'members':members
        })

    async def group_message(self, event):
        await self.send_json({
            'action':'group_update',
            'room':event['room'],
            'members':event['members']
        })

    async def handle_chat(self, data):
        await self.channel_layer.group_send(data['room'],{
            'type':'chat.message',
            **data
        })

    async def chat_message(self, event):
        await self.send_json({
            'action':'chat',
            'room':event['room'],
            'sender':event['sender'],
            'message':event['message']
        })