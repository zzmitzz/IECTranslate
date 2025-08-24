

from collections import defaultdict

class Rooms: 
    def __init__(self):
        self._peers = defaultdict(set)  # room_id -> set(peer_id)
        self._peer_rooms = {}  # peer_id -> room_id

    def join(self, room_id: str, peer_id: str):
        # Remove peer from previous room if any
        if peer_id in self._peer_rooms:
            old_room = self._peer_rooms[peer_id]
            if old_room in self._peers:
                self._peers[old_room].discard(peer_id)
                if not self._peers[old_room]:
                    self._peers.pop(old_room, None)
        
        # Add peer to new room
        self._peers[room_id].add(peer_id)
        self._peer_rooms[peer_id] = room_id

    def leave(self, peer_id: str):
        """Remove a peer from their current room"""
        if peer_id in self._peer_rooms:
            room_id = self._peer_rooms[peer_id]
            if room_id in self._peers:
                self._peers[room_id].discard(peer_id)
                if not self._peers[room_id]:
                    self._peers.pop(room_id, None)
            del self._peer_rooms[peer_id]

    def others(self, room_id: str, peer_id: str):
        return [p for p in self._peers[room_id] if p != peer_id]
    
    def get_peers_in_room(self, room_id: str):
        """Get all peer IDs in a specific room"""
        return self._peers.get(room_id, set())
    
    def get_peer_room(self, peer_id: str):
        """Get the room ID for a specific peer"""
        return self._peer_rooms.get(peer_id)
    
    @property
    def rooms(self):
        """Get all active rooms"""
        return self._peers


room = Rooms()