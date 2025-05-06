import json
import math
import uuid
import sys
import openai
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
sys.path.append('/Users/jdxiang/Desktop/Social_app_demo/mysite/match/')
from AI_recommendation_system import extract_keywords
from .models import User

# persistent mapping: { room_id: [user_id, ...] }
ROOM_MEMBERS = {}

def haversine(a, b):
    """Legacy haversine function for backward compatibility"""
    R = 6371
    φ1, φ2 = math.radians(a['lat']), math.radians(b['lat'])
    Δφ = math.radians(b['lat'] - a['lat'])
    Δλ = math.radians(b['lon'] - a['lon'])
    h = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return 2 * R * math.atan2(math.sqrt(h), math.sqrt(1 - h))

class MatchConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        print(f"[{self.channel_name}] CONNECT")
        self.user_id = None
        await self.accept()

    async def disconnect(self, code):
        print(f"[{self.channel_name}] DISCONNECT")

    @database_sync_to_async
    def get_or_create_user(self, profile_data):
        user, created = User.objects.get_or_create(
            user_id=profile_data['user_id'],
            defaults={
                'name': profile_data.get('name', ''),
                'interests': profile_data.get('interests', []),
                'hometown': profile_data.get('hometown', None),
                'major': profile_data.get('major', None),
                'latitude': profile_data.get('lat', 0),
                'longitude': profile_data.get('lon', 0),
            }
        )
        
        # Update fields if user already exists
        if not created:
            user.name = profile_data.get('name', user.name)
            user.interests = profile_data.get('interests', user.interests)
            user.hometown = profile_data.get('hometown', user.hometown)
            user.major = profile_data.get('major', user.major)
            user.latitude = profile_data.get('lat', user.latitude)
            user.longitude = profile_data.get('lon', user.longitude)
            user.save()
            
        return user
    
    @database_sync_to_async
    def get_user_profile(self, user_id):
        try:
            user = User.objects.get(user_id=user_id)
            return {
                'user_id': user.user_id,
                'name': user.name,
                'interests': user.interests,
                'hometown': user.hometown,
                'major': user.major,
                'lat': user.latitude,
                'lon': user.longitude
            }
        except User.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_nearby_users(self, user_id, max_km):
        """
        Get nearby users using the new efficient spatial query method
        """
        try:
            # Get the current user
            me = User.objects.get(user_id=user_id)
            
            # Use the newly created nearby_users method
            nearby = User.nearby_users(
                lat=me.latitude,
                lon=me.longitude,
                max_distance_km=max_km,
                exclude_user_id=user_id
            )
            
            # Convert to dictionary format needed by the consumer
            nearby_users = []
            for user in nearby:
                user_dict = {
                    'user_id': user.user_id,
                    'name': user.name,
                    'interests': user.interests,
                    'hometown': user.hometown,
                    'major': user.major,
                    'lat': user.latitude,
                    'lon': user.longitude,
                    'distance': user.distance,  # The distance is now calculated in the query
                    'channel_name': getattr(user, 'channel_name', None)
                }
                nearby_users.append(user_dict)
                    
            return nearby_users
        except User.DoesNotExist:
            return []

    async def receive_json(self, content):
        action = content.get('action')
        print(f"[{self.channel_name}] RECV_JSON: {content}")

        if action == 'register':
            profile = content['data']
            self.user_id = profile['user_id']
            # Store user in database
            user = await self.get_or_create_user(profile)
            
            # re-join any rooms the user belongs to
            for room_id, members in ROOM_MEMBERS.items():
                if self.user_id in members:
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
        if not self.user_id:
            return

        me = await self.get_user_profile(self.user_id)
        if not me:
            return

        request_text = data.get("request_text", "").strip()
        max_km = data.get("max_km", 5.0)
        threshold = data.get("threshold", 0.0)   
        max_group = data.get("max_group", None)

        kws = await extract_keywords(request_text)
        print(kws)
        if not kws:
            kws = ["tennis"] if "tennis" in request_text.lower() else []

        # Get nearby users using our efficient method
        nearby_users = await self.get_nearby_users(self.user_id, max_km)
        
        candidates = []
        for user in nearby_users:
            desc = [s.lower() for s in user.get('interests', [])]
            hits = sum(1 for kw in kws if kw in desc)
            score = hits / len(kws) if kws else 0.0

            if score > 0 or threshold == 0.0:
                candidates.append((user.get('channel_name'), user, user.get('distance', 0), score))

        # Note: Users are already sorted by distance in the nearby_users function
        # For this sorting, we prioritize by score first, then distance
        candidates.sort(key=lambda tup: (-tup[3], tup[2]))

        limit = max_group or 10
        selected = candidates[:limit]

        room_id = str(uuid.uuid4())
        ROOM_MEMBERS[room_id] = [self.user_id] + [u['user_id'] for _, u, _, _ in selected]

        for ch_name, user, dist, score in selected:
            if ch_name:  # Only send if we have a channel name
                await self.channel_layer.send(ch_name, {
                    "type": "invite.message",
                    "from": self.user_id,
                    "request_id": room_id,
                    "text": request_text,
                    "score": round(score, 2),
                    "distance": round(dist, 2),
                    "interests": me.get("interests", []),
                })

        # Tell the broadcaster we're done
        await self.send_json({
            "action": "broadcast_closed",
            "request_id": room_id,
            "invited_count": len(selected),
            "max_group": max_group,
            "keywords": kws,
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
        room_id = data['request_id']
        broadcaster = data['from']
        acceptor = data['acceptor']
        # ensure persistent list exists and append if new
        members = ROOM_MEMBERS.setdefault(room_id, [])
        for uid in (broadcaster, acceptor):
            if uid not in members:
                members.append(uid)
        # add acceptor's channel
        await self.channel_layer.group_add(room_id, self.channel_name)
        
        # add broadcaster channel if online
        for ch_name, user_id in self.channel_layer._connection_to_user.items():
            if user_id == broadcaster:
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