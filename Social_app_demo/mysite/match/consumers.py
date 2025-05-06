import json
import math
import uuid
import sys
import openai
from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer
from channels.db import database_sync_to_async
sys.path.append('/Users/jdxiang/Desktop/Social_app_demo/mysite/match/')
from AI_recommendation_system import extract_keywords
from .models import User, Room, RoomMember
import logging
import asyncio
from datetime import datetime
import random

logger = logging.getLogger(__name__)

# This is kept for backward compatibility during the transition to DB storage
# Will be removed once all code is migrated to use DB
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

    @database_sync_to_async
    def create_room(self, room_id, creator_id, request_text):
        """Create a new room and add the creator as a member"""
        try:
            creator = User.objects.get(user_id=creator_id)
            room = Room.objects.create(
                room_id=room_id,
                creator=creator,
                request_text=request_text,
                active=True
            )
            
            # Add creator as a member
            RoomMember.objects.create(
                room=room,
                user=creator,
                is_active=True
            )
            
            return room
        except User.DoesNotExist:
            return None
    
    @database_sync_to_async
    def add_user_to_room(self, room_id, user_id):
        """Add a user to a room"""
        try:
            room = Room.objects.get(room_id=room_id)
            user = User.objects.get(user_id=user_id)
            
            # Create the room membership if it doesn't exist
            member, created = RoomMember.objects.get_or_create(
                room=room,
                user=user,
                defaults={'is_active': True}
            )
            
            # If membership exists but was inactive, reactivate it
            if not created and not member.is_active:
                member.is_active = True
                member.save()
                
            return True
        except (Room.DoesNotExist, User.DoesNotExist):
            return False
    
    @database_sync_to_async
    def get_room_members(self, room_id):
        """Get all active members of a room"""
        try:
            room = Room.objects.get(room_id=room_id)
            member_ids = room.members.filter(is_active=True).values_list('user__user_id', flat=True)
            return list(member_ids)
        except Room.DoesNotExist:
            return []
    
    @database_sync_to_async
    def get_user_rooms(self, user_id):
        """Get all active rooms for a user"""
        try:
            user = User.objects.get(user_id=user_id)
            rooms = user.rooms.filter(is_active=True).values_list('room__room_id', flat=True)
            return list(rooms)
        except User.DoesNotExist:
            return []
            
    @database_sync_to_async
    def remove_user_from_room(self, room_id, user_id):
        """Mark a user as inactive in a room"""
        try:
            member = RoomMember.objects.get(
                room__room_id=room_id, 
                user__user_id=user_id
            )
            member.is_active = False
            member.save()
            
            # If no active members remain, mark the room as inactive
            active_count = RoomMember.objects.filter(
                room__room_id=room_id, 
                is_active=True
            ).count()
            
            if active_count == 0:
                room = Room.objects.get(room_id=room_id)
                room.active = False
                room.save()
                
            return True
        except RoomMember.DoesNotExist:
            return False

    async def receive_json(self, content):
        action = content.get('action')
        print(f"[{self.channel_name}] RECV_JSON: {content}")

        if action == 'register':
            profile = content['data']
            self.user_id = profile['user_id']
            # Store user in database
            user = await self.get_or_create_user(profile)
            
            # re-join any rooms the user belongs to
            user_rooms = await self.get_user_rooms(self.user_id)
            for room_id in user_rooms:
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

        # Generate a room ID
        room_id = str(uuid.uuid4())
        
        # Create the room in the database
        await self.create_room(room_id, self.user_id, request_text)
        
        # Add selected users to the room members list for later invitation acceptance
        invited_user_ids = [u['user_id'] for _, u, _, _ in selected]
        
        # Store this information in memory temporarily (will be replaced with DB later)
        # This helps with invitation flow
        ROOM_MEMBERS[room_id] = [self.user_id] + invited_user_ids

        # Send invites to selected users
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
        
        # Add acceptor to the room in the database
        await self.add_user_to_room(room_id, acceptor)
        
        # Add acceptor's channel to the room group
        await self.channel_layer.group_add(room_id, self.channel_name)
        
        # Find and add broadcaster's channel to the room group if online
        # This is still using the old approach as we don't store channel names in DB
        for ch_name, user_id in self.channel_layer._connection_to_user.items():
            if user_id == broadcaster:
                await self.channel_layer.group_add(room_id, ch_name)
                break
        
        # Get updated member list from database
        members = await self.get_room_members(room_id)
        
        # Broadcast the complete member list
        await self.channel_layer.group_send(room_id, {
            'type':'group.message',
            'room':room_id,
            'members':members
        })

    async def handle_leave(self, data):
        room_id = data['room']
        user_id = data['user_id']
        
        # Update database to mark user as inactive in this room
        success = await self.remove_user_from_room(room_id, user_id)
        
        if success:
            # Remove user's channel from the room group
            await self.channel_layer.group_discard(room_id, self.channel_name)
            
            # Get updated member list
            members = await self.get_room_members(room_id)
            
            # Notify other members about the change
            await self.channel_layer.group_send(room_id, {
                'type':'group.message',
                'room':room_id,
                'members':members
            })
            
            # Confirm to the user that they left
            await self.send_json({
                'action': 'left_room',
                'room': room_id
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

class ChatConsumer(AsyncWebsocketConsumer):
    # ... existing code ...
    # keep all existing code here
    pass

class NearbyConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time nearby users updates.
    This consumer allows clients to receive notifications when new users
    appear within their vicinity.
    """
    
    # Class-level storage to track connected users
    # In a production app, this should use a more scalable solution
    connected_users = {}  # Maps user_id to channel_name
    user_locations = {}   # Maps user_id to (lat, lon, max_distance) tuple
    
    async def connect(self):
        """Accept the WebSocket connection."""
        await self.accept()
        logger.info(f"NearbyConsumer: New connection established")
    
    async def disconnect(self, close_code):
        """Handle disconnection and cleanup."""
        # Find and remove this connection from our tracking
        user_id = None
        for uid, channel in self.connected_users.items():
            if channel == self.channel_name:
                user_id = uid
                break
        
        if user_id:
            # Remove user from tracking
            self.connected_users.pop(user_id, None)
            self.user_locations.pop(user_id, None)
            logger.info(f"NearbyConsumer: User {user_id} disconnected")
    
    async def receive(self, text_data):
        """
        Handle messages from WebSocket clients.
        Expects a registration message with user_id when connection starts.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'register':
                # Register a user for nearby notifications
                user_id = data.get('user_id')
                if not user_id:
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'Missing user_id in registration'
                    }))
                    return
                
                # Store this user's channel for sending notifications
                self.connected_users[user_id] = self.channel_name
                
                # Get the user's location and preferences
                user = await self.get_user(user_id)
                if user:
                    # Store location data for distance calculations
                    max_distance = data.get('max_distance', 5)  # Default 5km
                    self.user_locations[user_id] = (user.latitude, user.longitude, max_distance)
                    
                    logger.info(f"NearbyConsumer: User {user_id} registered for nearby notifications")
                    
                    # Confirm registration
                    await self.send(json.dumps({
                        'type': 'registration_success',
                        'message': 'Successfully registered for nearby notifications'
                    }))
                else:
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'User not found'
                    }))
            
            elif message_type == 'update_location':
                # Update a user's location
                user_id = data.get('user_id')
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                max_distance = data.get('max_distance', 5)
                
                if not all([user_id, latitude, longitude]):
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'Missing required fields for location update'
                    }))
                    return
                
                # Update stored location
                self.user_locations[user_id] = (float(latitude), float(longitude), float(max_distance))
                
                # Also update in the database
                await self.update_user_location(user_id, latitude, longitude)
                
                # Check for new nearby users after location update
                await self.check_nearby_users(user_id)
                
                logger.info(f"NearbyConsumer: Updated location for user {user_id}")
        
        except json.JSONDecodeError:
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"NearbyConsumer error: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Server error: {str(e)}'
            }))
    
    async def notify_new_nearby_user(self, event):
        """Send notification about a new nearby user to the client."""
        # Forward the notification to the WebSocket
        await self.send(text_data=json.dumps({
            'type': 'new_nearby_user',
            'user': event['user']
        }))
    
    @database_sync_to_async
    def get_user(self, user_id):
        """Get a user from the database."""
        try:
            return User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return None
    
    @database_sync_to_async
    def update_user_location(self, user_id, latitude, longitude):
        """Update a user's location in the database."""
        try:
            user = User.objects.get(user_id=user_id)
            user.latitude = float(latitude)
            user.longitude = float(longitude)
            user.save(update_fields=['latitude', 'longitude', 'updated_at'])
            return True
        except User.DoesNotExist:
            return False
    
    @database_sync_to_async
    def get_nearby_users(self, user_id, latitude, longitude, max_distance):
        """Get nearby users from the database."""
        try:
            return list(User.nearby_users(
                float(latitude), 
                float(longitude), 
                float(max_distance),
                exclude_user_id=user_id
            ).values('user_id', 'name', 'latitude', 'longitude', 'distance'))
        except Exception as e:
            logger.error(f"Error getting nearby users: {str(e)}")
            return []
    
    async def check_nearby_users(self, user_id):
        """Check for nearby users and send notifications if found."""
        if user_id not in self.user_locations:
            return
        
        lat, lon, max_distance = self.user_locations[user_id]
        
        # Get nearby users from database
        nearby_users = await self.get_nearby_users(user_id, lat, lon, max_distance)
        
        # Send notifications
        if user_id in self.connected_users:
            channel_name = self.connected_users[user_id]
            
            for user in nearby_users:
                # In a real app, you'd track which users were already notified
                # and only send notifications for new users
                
                # For demo purposes, randomly determine if this is a "new" nearby user
                # In a real app, you'd compare against previously seen users
                if random.random() < 0.3:  # 30% chance to notify about each user
                    await self.channel_layer.send(
                        channel_name,
                        {
                            'type': 'notify_new_nearby_user',
                            'user': {
                                'user_id': user['user_id'],
                                'name': user['name'],
                                'latitude': user['latitude'],
                                'longitude': user['longitude'],
                                'distance': user['distance']
                            }
                        }
                    )