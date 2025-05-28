import json
import math
import uuid
import sys
import openai
from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
sys.path.append('/Users/jdxiang/Desktop/Social_app_demo/mysite/match/')
from  .AI_recommendation_system import extract_keywords
import random

# in-memory profile store: { channel_name: profile_dict }
PROFILES = {}
# persistent mapping: { room_id: [user_id, ...] }
ROOM_MEMBERS = {}

# Store online users: {username: channel_name}
ONLINE_USERS = {}

BOT_USERS = [
    {"user_id": "bot1", "name": "Bot 1"},
    {"user_id": "bot2", "name": "Bot 2"}
]
BOT_MESSAGES = [
    "Welcome to the general announcement group!",
    "Remember to be kind to each other!",
    "Bot here: Stay hydrated!",
    "Bot tip: Try finding a match using your interests!",
    "Bot says: Have a great chat!"
]
GENERAL_GROUP = "general_announcement"

def haversine(a, b):
    R = 6371
    φ1, φ2 = math.radians(a['lat']), math.radians(b['lat'])
    Δφ = math.radians(b['lat'] - a['lat'])
    Δλ = math.radians(b['lon'] - a['lon'])
    h = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return 2 * R * math.atan2(math.sqrt(h), math.sqrt(1 - h))

# class MatchConsumer(AsyncJsonWebsocketConsumer):
#     async def connect(self):
#         print(f"[{self.channel_name}] CONNECT")
#         await self.accept()

#     async def disconnect(self, code):
#         print(f"[{self.channel_name}] DISCONNECT")
#         PROFILES.pop(self.channel_name, None)

#     async def receive_json(self, content):
#         action = content.get('action')
#         print(f"[{self.channel_name}] RECV_JSON: {content}")

#         if action == 'register':
#             profile = content['data']
#             PROFILES[self.channel_name] = profile
#             user_id = profile['user_id']
#             # re-join any rooms the user belongs to
#             for room_id, members in ROOM_MEMBERS.items():
#                 if user_id in members:
#                     await self.channel_layer.group_add(room_id, self.channel_name)
#                     print(f"[{self.channel_name}] re-joined room {room_id}")
#             await self.send_json({'action':'registered'})

#         elif action == 'broadcast':
#             await self.handle_broadcast(content['data'])

#         elif action == 'accept':
#             await self.handle_accept(content['data'])

#         elif action == 'chat':
#             await self.handle_chat(content['data'])

#     async def handle_broadcast(self, data):
#         me = PROFILES.get(self.channel_name)
#         if not me:
#             return

#         text = data.get('request_text','').lower()
#         if 'tennis' not in text:
#             await self.send_json({
#                 'action':'broadcast_closed',
#                 'request_id': None,
#                 'invited_count':0,
#                 'max_group': data.get('max_group')
#             })
#             return

#         max_km    = data.get('max_km',5.0)
#         threshold = data.get('threshold',0.5)
#         max_group = data.get('max_group')
#         invited   = 0
#         # generate a single room id for this broadcast
#         room_id   = str(uuid.uuid4())
#         # initialize member list with broadcaster
#         ROOM_MEMBERS[room_id] = [me['user_id']]

#         for ch_name, prof in PROFILES.items():
#             if prof['user_id'] == me['user_id']:
#                 continue
#             dist = haversine(me, prof)
#             if dist > max_km:
#                 continue
#             match = 'tennis' in prof.get('interests',[])
#             score = 1.0 if match else 0.0
#             if score < threshold:
#                 continue
#             # add invitee to persistent map
#             ROOM_MEMBERS[room_id].append(prof['user_id'])
#             # send invite event
#             await self.channel_layer.send(ch_name, {
#                 'type':'invite.message',
#                 'from': me['user_id'],
#                 'request_id': room_id,
#                 'text': data['request_text'],
#                 'score': score,
#                 'distance': round(dist,2),
#                 'interests': me.get('interests',[])
#             })
#             invited += 1
#             if max_group is not None and invited >= max_group:
#                 break

#         # notify broadcaster
#         await self.send_json({
#             'action':'broadcast_closed',
#             'request_id': room_id,
#             'invited_count': invited,
#             'max_group': max_group
#         })




class MatchConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        print(f"[{self.channel_name}] CONNECT")
        await self.accept()
        # Always add user to general_announcement group
        await self.channel_layer.group_add(GENERAL_GROUP, self.channel_name)
        # Add bots to group and send random messages
        for bot in BOT_USERS:
            await self.channel_layer.group_send(
                GENERAL_GROUP,
                {
                    "type": "chat.message",
                    "room": GENERAL_GROUP,
                    "sender": bot["user_id"],
                    "message": random.choice(BOT_MESSAGES)
                }
            )

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

        elif action == 'leave':
            await self.handle_leave(content['data'])

    async def handle_broadcast(self, data):
        me = PROFILES.get(self.channel_name)
        if not me:
            return

        request_text = data.get("request_text", "").strip()
        max_km        = data.get("max_km", 5.0)
        threshold     = data.get("threshold", 0.0)   
        max_group     = data.get("max_group", None)

        # Use AI keyword extraction
        kws = await extract_keywords(request_text)
        print(f"[AI] Extracted keywords: {kws}")
        if not kws:
            kws = [request_text] if request_text else []

        candidates = []
        for ch_name, prof in PROFILES.items():
            if prof["user_id"] == me["user_id"]:
                continue

            dist = haversine(me, prof)
            if dist > max_km:
                continue

            # Compare extracted keywords to user interests
            desc = [s.lower() for s in prof.get('interests', [])]
            hits  = sum(1 for kw in kws if kw.lower() in desc)
            score = hits / len(kws) if kws else 0.0

            if score > 0 or threshold == 0.0:
                candidates.append((ch_name, prof, dist, score))

        candidates.sort(key=lambda tup: (-tup[3], tup[2]))

        limit = max_group or 10
        selected = candidates[:limit]

        room_id = str(uuid.uuid4())
        ROOM_MEMBERS[room_id] = [me["user_id"]] + [p["user_id"] for _, p, _, _ in selected]

        for ch_name, prof, dist, score in selected:
            await self.channel_layer.send(ch_name, {
                "type":        "invite.message",
                "from":        me["user_id"],
                "request_id":  room_id,
                "text":        request_text,
                "score":       round(score, 2),
                "distance":    round(dist, 2),
                "interests":   me.get("interests", []),
            })

        # Notify broadcaster
        await self.send_json({
            "action":         "broadcast_closed",
            "request_id":     room_id,
            "invited_count":  len(selected),
            "max_group":      max_group,
            "keywords":       kws,
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
        # Always default to general_announcement if no room specified
        room = data.get('room') or GENERAL_GROUP
        await self.channel_layer.group_send(room, {
            'type': 'chat.message',
            'room': room,
            'sender': data.get('sender'),
            'message': data.get('message')
        })

    async def chat_message(self, event):
        # Always include the room in the message
        room = event.get('room') or GENERAL_GROUP
        await self.send_json({
            'action': 'chat',
            'room': room,
            'sender': event['sender'],
            'message': event['message']
        })

    async def handle_leave(self, data):
        room_id = data['room']
        user_id = data['user_id']
        # Remove user from ROOM_MEMBERS
        members = ROOM_MEMBERS.get(room_id, [])
        if user_id in members:
            members.remove(user_id)
            # Remove from channel group
            await self.channel_layer.group_discard(room_id, self.channel_name)
            # If room is empty, delete it
            if not members:
                del ROOM_MEMBERS[room_id]
            else:
                ROOM_MEMBERS[room_id] = members
            # Notify user
            await self.send_json({
                'action': 'left_group',
                'room': room_id
            })
            # Optionally notify others in the group
            await self.channel_layer.group_send(room_id, {
                'type': 'group.message',
                'room': room_id,
                'members': members
            })

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_group_name = "chat_room"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Add user to online users
        ONLINE_USERS[self.user.username] = self.channel_name
        
        # Notify all users about the new online user
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_list_update",
                "users": list(ONLINE_USERS.keys())
            }
        )
        
        await self.accept()

    async def disconnect(self, close_code):
        # Remove user from online users
        if self.user.username in ONLINE_USERS:
            del ONLINE_USERS[self.user.username]
            
            # Notify all users about the user leaving
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_list_update",
                    "users": list(ONLINE_USERS.keys())
                }
            )
        
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message")
        action = text_data_json.get("action")
        
        if action == "broadcast":
            # Handle broadcast request
            await self.handle_broadcast(text_data_json)
        elif message:
            # Handle regular chat message
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": message,
                    "username": self.user.username
                }
            )

    async def handle_broadcast(self, data):
        request_text = data.get("request_text", "").strip()
        max_km = data.get("max_km", 5.0)
        threshold = data.get("threshold", 0.0)
        max_group = data.get("max_group", None)

        # Get user's profile from the database
        profile = await self.get_user_profile(self.user)
        
        # Find matching users
        matches = []
        for username, channel_name in ONLINE_USERS.items():
            if username == self.user.username:
                continue
                
            match_profile = await self.get_user_profile_by_username(username)
            if not match_profile:
                continue

            # Calculate match score based on interests
            score = await self.calculate_match_score(profile, match_profile)
            if score >= threshold:
                matches.append((username, channel_name, score))

        # Sort matches by score
        matches.sort(key=lambda x: x[2], reverse=True)
        
        # Limit number of matches
        matches = matches[:max_group] if max_group else matches

        # Send matches to the requesting user
        await self.send(text_data=json.dumps({
            "type": "matches",
            "matches": [{"username": m[0], "score": m[2]} for m in matches]
        }))

        # Send invites to matched users
        for username, channel_name, score in matches:
            await self.channel_layer.send(channel_name, {
                "type": "invite.message",
                "from": self.user.username,
                "request_text": request_text,
                "score": score
            })

    async def chat_message(self, event):
        message = event["message"]
        username = event["username"]

        await self.send(text_data=json.dumps({
            "type": "received" if username != self.user.username else "sent",
            "message": f"{username}: {message}"
        }))

    async def user_list_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "user_list",
            "users": event["users"]
        }))

    async def invite_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "invite",
            "from": event["from"],
            "request_text": event["request_text"],
            "score": event["score"]
        }))

    @database_sync_to_async
    def get_user_profile(self, user):
        try:
            profile = user.userprofile
            return {
                "interests": profile.interests,
                "location": profile.location
            }
        except UserProfile.DoesNotExist:
            return {
                "interests": [],
                "location": {"lat": 0, "lon": 0}
            }

    @database_sync_to_async
    def get_user_profile_by_username(self, username):
        try:
            user = User.objects.get(username=username)
            return self.get_user_profile(user)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def calculate_match_score(self, profile1, profile2):
        # Calculate match score based on shared interests
        interests1 = set(profile1.get("interests", []))
        interests2 = set(profile2.get("interests", []))
        
        if not interests1 or not interests2:
            return 0.0
            
        shared = len(interests1.intersection(interests2))
        total = len(interests1.union(interests2))
        
        return shared / total if total > 0 else 0.0