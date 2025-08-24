
import asyncio
import json
import logging
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaStreamTrack, MediaPlayer, MediaRecorder, MediaRelay
from typing import Dict, Set, Optional
from .room import Rooms
from .audio_handler import AudioStreamHandler, initialize_audio_processors


logger = logging.getLogger(__name__)

class WebRTCHandler : 
    def __init__(self):
        self.room = Rooms()
        self.connections: Dict[str, RTCPeerConnection] = {}
        self.audio_tracks: Dict[str, MediaStreamTrack] = {}
        self.audio_handler = AudioStreamHandler()
        self.media_relay = MediaRelay()  # For forwarding media between peers
        
        # Initialize default audio processors
        initialize_audio_processors(self.audio_handler)

    async def create_peer_connection(self, room_id: str, peer_id: str) -> RTCPeerConnection:
        pc = RTCPeerConnection()
        self.connections[peer_id] = pc

        # Set up audio track handling
        @pc.on("track")
        async def on_track(track):
            print(f"=== ONTRACK EVENT TRIGGERED ===")
            print(f"Received {track.kind} track from peer {peer_id}")
            print(f"Track ID: {track.id}, Track kind: {track.kind}")
            print(f"Peer connection state: {pc.connectionState}")
            print(f"ICE connection state: {pc.iceConnectionState}")
            
            if track.kind == "audio":
                try:
                    # Use media relay to create a relayed track that can be shared
                    relayed_track = self.media_relay.subscribe(track)
                    self.audio_tracks[peer_id] = relayed_track
                    
                    # Process the audio track with error handling
                    processed_track = await self.audio_handler.process_audio_track(peer_id, relayed_track)
                    
                    # Ensure we have a valid track before proceeding
                    if processed_track is not None:
                        # Handle incoming audio track
                        await self.handle_audio_track(peer_id, processed_track)
                    else:
                        logger.error(f"Audio processing failed for peer {peer_id}, using original track")
                        await self.handle_audio_track(peer_id, relayed_track)
                        
                except Exception as e:
                    logger.error(f"Error handling audio track from peer {peer_id}: {e}")
                    # Fallback to using the original track
                    try:
                        await self.handle_audio_track(peer_id, track)
                    except Exception as fallback_error:
                        logger.error(f"Fallback audio handling also failed for peer {peer_id}: {fallback_error}")
            else:
                print(f"Unsupported track type: {track.kind}")

        self.room.join(room_id, peer_id)
        return pc

    async def handle_audio_track(self, peer_id: str, track: MediaStreamTrack):
        # """Handle incoming audio track from a peer"""
        logger.info(f"Setting up audio track handling for peer {peer_id}")
        
        # Update audio statistics
        self.audio_handler.update_audio_stats(peer_id, {
            "track_active": True,
            "track_type": "audio",
            "timestamp": asyncio.get_event_loop().time()
        })
        
        # Get room information for logging
        room_id = self.room.get_peer_room(peer_id)
        room_peers = self.room.get_peers_in_room(room_id) if room_id else set()
        other_peers_count = len([p for p in room_peers if p != peer_id])
        
        logger.info(f"Peer {peer_id} in room {room_id} with {other_peers_count} other peers")
        
        # Forward the audio track to other peers in the same room
        await self.forward_audio_track_to_room(peer_id, track)
        
        logger.info(f"Audio track from peer {peer_id} is now active and processed")

    async def forward_audio_track_to_room(self, source_peer_id: str, track: MediaStreamTrack):
        """Forward audio track to all other peers in the same room"""
        try:
            # Validate input parameters
            if not track or not hasattr(track, 'kind'):
                logger.error(f"Invalid track object for peer {source_peer_id}")
                return
            
            if track.kind != "audio":
                logger.warning(f"Track is not audio type: {track.kind}")
                return
            
            # Get the room ID for this peer
            room_id = self.room.get_peer_room(source_peer_id)
            if not room_id:
                logger.warning(f"Peer {source_peer_id} not in any room")
                return
            
            # Get all other peers in the same room (excluding the source peer)
            room_peers = self.room.get_peers_in_room(room_id)
            other_peers = [peer_id for peer_id in room_peers if peer_id != source_peer_id]
            
            if not other_peers:
                logger.info(f"No other peers in room {room_id} to forward audio to")
                return
            
            logger.info(f"Forwarding audio track from {source_peer_id} to {len(other_peers)} other peers in room {room_id}")
            
            # Forward audio track to all other peers using media relay
            successful_forwards = 0
            for peer_id in other_peers:
                if peer_id in self.connections:
                    try:
                        pc = self.connections[peer_id]
                        if pc.connectionState == "connected":
                            # Create a relayed track for this peer
                            relayed_track = self.media_relay.subscribe(track)
                            # Add the relayed track to the peer's connection
                            sender = pc.addTrack(relayed_track)
                            successful_forwards += 1
                            logger.info(f"Successfully forwarded audio track from {source_peer_id} to {peer_id}")
                        else:
                            logger.warning(f"Peer {peer_id} connection not ready (state: {pc.connectionState})")
                    except Exception as e:
                        logger.error(f"Failed to forward audio track to {peer_id}: {e}")
                else:
                    logger.warning(f"Peer {peer_id} not found in connections, skipping audio forwarding")
            
            logger.info(f"Audio forwarding completed: {successful_forwards}/{len(other_peers)} peers received the track")
                        
        except Exception as e:
            logger.error(f"Error forwarding audio track: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def add_audio_track(self, peer_id: str, audio_source: Optional[str] = None):
        """Add an audio track to the peer connection"""
        if peer_id not in self.connections:
            raise ValueError(f"No connection found for peer {peer_id}")
        
        pc = self.connections[peer_id]
        
        if audio_source:
            # Create a media player from an audio file or stream
            player = MediaPlayer(audio_source)
            audio_track = player.audio
        else:
            # Create a default audio track (you might want to implement a custom audio source)
            # For now, we'll just return None as this requires more complex implementation
            logger.warning("No audio source provided, cannot create audio track")
            return None
        
        if audio_track:
            sender = pc.addTrack(audio_track)
            logger.info(f"Added audio track to peer {peer_id}")
            return sender
        
        return None

    async def start_audio_recording(self, peer_id: str, filename: str) -> bool:
        """Start recording audio from a specific peer"""
        return await self.audio_handler.start_recording(peer_id, filename)
    
    async def stop_audio_recording(self, peer_id: str) -> bool:
        """Stop recording audio from a specific peer"""
        return await self.audio_handler.stop_recording(peer_id)
    
    def get_audio_statistics(self, peer_id: str) -> Dict:
        """Get audio statistics for a specific peer"""
        return self.audio_handler.get_audio_stats(peer_id)
    
    def get_all_audio_statistics(self) -> Dict[str, Dict]:
        """Get audio statistics for all peers"""
        return self.audio_handler.audio_stats

    async def handle_offer(self, room_id: str, peer_id: str, offer: dict):
        print("handle_offer", room_id, peer_id, offer)
        pc = await self.create_peer_connection(room_id, peer_id)
        
        # Set up ICE candidate collection
        ice_candidates = []
        
        @pc.on("icecandidate")
        def on_ice_candidate(candidate):
            if candidate:
                ice_candidates.append({
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                })
        
        await pc.setRemoteDescription(
            RTCSessionDescription(
                type=offer["type"],
                sdp=offer["sdp"],
            )
        )

        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # Wait for ICE gathering to complete
        while pc.iceGatheringState != "complete":
            await asyncio.sleep(0.1)
            # Add a timeout to prevent infinite waiting
            if len(ice_candidates) > 10:  # Arbitrary limit
                break

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "ice_candidates": ice_candidates
        }
    
    async def handle_answer(self, user_id: str, answer: dict):
        """Handle WebRTC answer"""
        logger.info(f"=== HANDLE ANSWER CALLED ===")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Answer: {answer}")
        
        if user_id not in self.connections:
            logger.error(f"No connection found for user {user_id}")
            raise ValueError(f"No connection found for user {user_id}")
        
        pc = self.connections[user_id]
        logger.info(f"Found peer connection for user {user_id}")
        logger.info(f"Connection state: {pc.connectionState}")
        logger.info(f"ICE connection state: {pc.iceConnectionState}")
        
        await pc.setRemoteDescription(RTCSessionDescription(
            sdp=answer["sdp"],
            type=answer["type"]
        ))
        
        logger.info(f"Remote description set successfully for user {user_id}")
        logger.info(f"Updated connection state: {pc.connectionState}")
        logger.info(f"Updated ICE connection state: {pc.iceConnectionState}")

    async def handle_candidate(self, room_id: str, peer_id: str, candidate: dict):
        if peer_id not in self.connections:
            raise ValueError(f"No connection found for user {peer_id}")
        
        pc = self.connections[peer_id]
        
        try:
            # Parse the ICE candidate string to extract required parameters
            candidate_str = candidate["candidate"]
            
            # Parse candidate string format: "candidate:1 1 UDP 2122252543 192.168.1.1 54321 typ host"
            # Format: foundation priority protocol priority2 ip port typ type [relatedAddress] [relatedPort] [tcpType]
            parts = candidate_str.split()
            
            if len(parts) < 8:
                logger.error(f"Invalid ICE candidate format: {candidate_str}")
                return
            
            # Extract parameters from the candidate string
            foundation = parts[0]  # "candidate:1"
            priority = int(parts[1])  # First priority
            protocol = parts[2]  # "UDP"
            # parts[3] is another priority value, we'll use the first one
            ip = parts[4]  # IP address
            port = int(parts[5])  # Port
            # parts[6] is "typ"
            candidate_type = parts[7]  # Actual type (e.g., "host")
            
            # Default values for optional parameters
            related_address = None
            related_port = None
            tcp_type = None
            
            # Check for related address/port and tcp type (if more parts exist)
            for i in range(8, len(parts), 2):
                if i + 1 < len(parts):
                    if parts[i] == "raddr":
                        related_address = parts[i + 1]
                    elif parts[i] == "rport":
                        related_port = int(parts[i + 1])
                    elif parts[i] == "tcptype":
                        tcp_type = parts[i + 1]
            
            # Create RTCIceCandidate with the correct parameter format
            ice_candidate = RTCIceCandidate(
                component=1,  # Default to 1 for RTP
                foundation=foundation,
                ip=ip,
                port=port,
                priority=priority,
                protocol=protocol,
                type=candidate_type,
                relatedAddress=related_address,
                relatedPort=related_port,
                sdpMid=candidate.get("sdpMid"),
                sdpMLineIndex=candidate.get("sdpMLineIndex"),
                tcpType=tcp_type
            )
            
            await pc.addIceCandidate(ice_candidate)
            logger.info(f"Successfully added ICE candidate for peer {peer_id}")
            
        except Exception as e:
            logger.error(f"Error adding ICE candidate for peer {peer_id}: {e}")
            logger.error(f"Candidate data received: {candidate}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def remove_peer(self, peer_id: str):
        """Clean up peer connection and associated resources"""
        if peer_id in self.connections:
            pc = self.connections[peer_id]
            await pc.close()
            del self.connections[peer_id]
            
        if peer_id in self.audio_tracks:
            del self.audio_tracks[peer_id]
            
        # Stop any active recordings
        await self.audio_handler.stop_recording(peer_id)
        
        self.room.leave(peer_id)
        logger.info(f"Cleaned up resources for peer {peer_id}")

    def get_audio_track(self, peer_id: str) -> Optional[MediaStreamTrack]:
        """Get the audio track for a specific peer"""
        return self.audio_tracks.get(peer_id)

    def get_active_audio_peers(self) -> Set[str]:
        """Get all peer IDs that have active audio tracks"""
        return set(self.audio_tracks.keys())
    
    def register_custom_audio_processor(self, name: str, processor):
        """Register a custom audio processor"""
        self.audio_handler.register_audio_processor(name, processor)
        logger.info(f"Registered custom audio processor: {name}")

    def get_peers_in_room(self, room_id: str) -> Set[str]:
        """Get all peer IDs in a specific room"""
        return self.room.get_peers_in_room(room_id)

    def get_ice_connection_state(self, peer_id: str) -> Dict:
        """Get ICE connection state information for a specific peer"""
        if peer_id not in self.connections:
            return {"error": "Peer not found"}
        
        pc = self.connections[peer_id]
        return {
            "peer_id": peer_id,
            "connection_state": pc.connectionState,
            "ice_connection_state": pc.iceConnectionState,
            "ice_gathering_state": pc.iceGatheringState,
            "signaling_state": pc.signalingState
        }

    def get_audio_streaming_status(self, room_id: str = None) -> Dict:
        """Get detailed audio streaming status for debugging"""
        status = {
            "total_connections": len(self.connections),
            "total_audio_tracks": len(self.audio_tracks),
            "active_rooms": len(self.room.rooms),
            "audio_statistics": self.get_all_audio_statistics()
        }
        
        if room_id:
            room_peers = self.room.get_peers_in_room(room_id)
            status["room_info"] = {
                "room_id": room_id,
                "total_peers": len(room_peers),
                "peers": list(room_peers),
                "peers_with_audio": [peer_id for peer_id in room_peers if peer_id in self.audio_tracks],
                "peers_with_connections": [peer_id for peer_id in room_peers if peer_id in self.connections]
            }
        
        return status
